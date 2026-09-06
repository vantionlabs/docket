/** Zod schemas shared by the auth forms (TanStack Form validators). */

import { z } from "zod";

export const credentialsSchema = z.object({
  email: z.email("Enter a valid email"),
  password: z.string().min(8, "At least 8 characters"),
});

export type Credentials = z.infer<typeof credentialsSchema>;
