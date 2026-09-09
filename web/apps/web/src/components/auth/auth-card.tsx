import { Button } from "@/components/ui/button.js";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card.js";
import { Link } from "@tanstack/react-router";
import * as React from "react";

/**
 * Shared chrome for the auth pages — a single centred card, no decoration, per
 * knowledge/rules/dashboard-ui.md.
 */
export const AuthCard = (props: {
  readonly title: string;
  readonly description: string;
  readonly children: React.ReactNode;
  readonly footer?: React.ReactNode;
}) => (
  <Card className="w-full max-w-sm">
    <CardHeader>
      <CardTitle className="text-base">{props.title}</CardTitle>
      <CardDescription>{props.description}</CardDescription>
    </CardHeader>
    <CardContent className="flex flex-col gap-4">
      {props.children}
      {props.footer !== undefined && (
        <div className="text-sm text-muted-foreground">{props.footer}</div>
      )}
    </CardContent>
  </Card>
);

/** Navigation between auth pages uses real links, never buttons. */
export const AuthLink = (props: { readonly to: string; readonly children: React.ReactNode; }) => (
  <Link to={props.to} className="text-foreground underline underline-offset-4">
    {props.children}
  </Link>
);

export const GoogleButton = (props: { readonly onClick: () => void; }) => (
  <Button type="button" variant="outline" className="w-full" onClick={props.onClick}>
    Continue with Google
  </Button>
);
