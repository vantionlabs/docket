import { grantsFor, statements } from "@forge/domain/iam/Permission";
import { betterAuth } from "better-auth";
import { getMigrations } from "better-auth/db/migration";
import { emailOTP, magicLink, organization } from "better-auth/plugins";
import { createAccessControl } from "better-auth/plugins/access";
import { randomUUID } from "node:crypto";
import type * as Pg from "pg";
import type { EmailMessage } from "../email/Mailer.js";
import * as Templates from "../email/Templates.js";

/**
 * Everything better-auth needs, resolved before it is constructed.
 *
 * This module imports nothing from `effect` on purpose: the Effect boundary
 * lives in `Auth.ts`, and `sendEmail` arrives already bound to a runtime.
 */
export interface MakeAuthOptions {
  readonly pool: Pg.Pool;
  readonly baseURL: string;
  readonly secret: string;
  readonly trustedOrigins: ReadonlyArray<string>;
  readonly google: { readonly clientId: string; readonly clientSecret: string; } | undefined;
  /**
   * The parent domain the session cookie is scoped to, when the web app and the
   * API are on different subdomains of it — `.example.com` for `app.example.com`
   * and `api.example.com`.
   *
   * Undefined leaves better-auth's default, which is right whenever the two are
   * the same host: `localhost` in development, or a single-origin deployment.
   */
  readonly cookieDomain: string | undefined;
  readonly sendEmail: (message: EmailMessage) => Promise<void>;
}

/** What a verified session carries. Narrower than better-auth's own shape. */
export interface AuthSession {
  readonly user: {
    readonly id: string;
    readonly email: string;
    readonly emailVerified: boolean;
  };
  readonly session: {
    readonly id: string;
    readonly activeOrganizationId?: string | null | undefined;
    readonly role?: string | null | undefined;
    readonly memberId?: string | null | undefined;
  };
}

/**
 * The only surface the rest of the server sees.
 *
 * Deliberately narrow: better-auth's inferred types are not portable across a
 * `declaration: true` build — they reach into zod internals that pnpm's store
 * layout makes unnameable — and letting them escape would leak its whole type
 * surface into every consumer. `authOptions` stays unexported for that reason.
 */
export interface AuthInstance {
  readonly handler: (request: Request) => Promise<Response>;
  readonly getSession: (headers: Record<string, string>) => Promise<AuthSession | null>;
}

/**
 * better-auth's access control, generated from the domain's permission
 * declaration rather than written a second time here.
 *
 * This is what stops the two systems disagreeing: its endpoints and our RPC
 * policies now consult the same grants, and a change to `grantsFor` moves both.
 */
const accessControl = createAccessControl(statements);

const roles = {
  owner: accessControl.newRole(grantsFor.owner),
  admin: accessControl.newRole(grantsFor.admin),
  member: accessControl.newRole(grantsFor.member),
};

/** Single source of truth for the runtime instance and for schema generation. */
const authOptions = (options: MakeAuthOptions) => ({
  // The shared pool, so auth writes join application transactions and the
  // process keeps one connection pool rather than two.
  database: options.pool,
  baseURL: options.baseURL,
  secret: options.secret,
  trustedOrigins: [...options.trustedOrigins],

  /**
   * Sharing the session cookie across subdomains of one parent.
   *
   * The browser decides this, not better-auth: a cookie can only be scoped to a
   * domain the setter is under, and never to a public suffix. `app.example.com`
   * and `api.example.com` can share `.example.com`; two Railway-generated hosts
   * cannot share `.up.railway.app`, because that name is on the Public Suffix
   * List. A deployment that splits the two therefore needs its own domain.
   */
  ...(options.cookieDomain === undefined ? {} : {
    advanced: {
      crossSubDomainCookies: { enabled: true, domain: options.cookieDomain },
    },
  }),

  emailAndPassword: {
    enabled: true,
    sendResetPassword: async ({ user, url }: { user: { email: string; }; url: string; }) => {
      await options.sendEmail({ to: user.email, ...Templates.resetPassword(url) });
    },
  },

  emailVerification: {
    // Sent as part of signing up rather than waiting for the user to ask.
    sendOnSignUp: true,
    // The verification link lands them signed in, so there is no second step.
    autoSignInAfterVerification: true,
    sendVerificationEmail: async ({ user, url }: { user: { email: string; }; url: string; }) => {
      await options.sendEmail({ to: user.email, ...Templates.verifyEmail(url) });
    },
  },

  socialProviders: options.google === undefined ? {} : { google: options.google },

  databaseHooks: {
    user: {
      create: {
        // Every user gets a personal organization immediately, so there is no
        // orgless state for the rest of the system to represent or handle.
        after: async (user: { id: string; name: string; email: string; }) => {
          const organizationId = randomUUID();
          const handle = user.email.split("@")[0] ?? "user";

          await options.pool.query(
            `insert into "organization" ("id", "name", "slug", "createdAt") values ($1, $2, $3, now())`,
            [
              organizationId,
              `${user.name === "" ? handle : user.name}'s Organization`,
              `${handle}-${user.id.slice(-6)}`.toLowerCase(),
            ],
          );

          await options.pool.query(
            `insert into "member" ("id", "organizationId", "userId", "role", "createdAt") values ($1, $2, $3, 'owner', now())`,
            [randomUUID(), organizationId, user.id],
          );
        },
      },
    },
  },

  plugins: [
    organization({
      ac: accessControl,
      roles,
      // Custom per-organization roles, stored in `organizationRole` and merged
      // over the static roles above when better-auth checks a permission.
      dynamicAccessControl: { enabled: true },
    }),
    magicLink({
      sendMagicLink: async ({ email, url }) => {
        await options.sendEmail({ to: email, ...Templates.magicLink(url) });
      },
    }),
    emailOTP({
      sendVerificationOTP: async ({ email, otp }) => {
        await options.sendEmail({ to: email, ...Templates.emailOtp(otp) });
      },
    }),
  ],
});

export const makeAuth = (options: MakeAuthOptions): AuthInstance => {
  const auth = betterAuth(authOptions(options));

  return {
    handler: (request) => auth.handler(request),

    // Effect models headers as a string record; better-auth wants web Headers.
    getSession: async (headers) => {
      const session = await auth.api.getSession({ headers: new Headers(headers) });
      if (session === null) return null;

      // The organization plugin adds `activeOrganizationId` to the session row
      // at runtime but not to better-auth's types, so it is read back with SQL
      // rather than through an unsafe cast. Honouring it is what makes
      // switching organizations take effect.
      const { rows } = await options.pool.query<
        { organizationId: string; role: string; id: string; }
      >(
        `select m."organizationId", m."role", m."id"
         from "member" m
         where m."userId" = $1
           and m."organizationId" = coalesce(
             (select s."activeOrganizationId" from "session" s where s."id" = $2),
             m."organizationId"
           )
         order by m."createdAt" asc
         limit 1`,
        [session.user.id, session.session.id],
      );

      return {
        user: session.user,
        session: {
          id: session.session.id,
          activeOrganizationId: rows[0]?.organizationId ?? null,
          role: rows[0]?.role ?? null,
          memberId: rows[0]?.id ?? null,
        },
      };
    },
  };
};

/**
 * Emits the DDL better-auth needs for this exact plugin set, so the committed
 * migration is generated rather than guessed.
 */
export const compileAuthMigrations = async (options: MakeAuthOptions): Promise<string> => {
  const { compileMigrations } = await getMigrations(authOptions(options));

  return compileMigrations();
};
