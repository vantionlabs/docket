import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/** Shared shell for the sign-in / sign-up pages. */
export function AuthCard({
  title,
  footerPrompt,
  footerHref,
  footerLink,
  children,
}: {
  title: string;
  footerPrompt: string;
  footerHref: string;
  footerLink: string;
  children: React.ReactNode;
}) {
  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-xl">{title}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          {children}
          <p className="text-muted-foreground text-sm">
            {footerPrompt}{" "}
            <Link href={footerHref} className="text-foreground font-medium underline">
              {footerLink}
            </Link>
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
