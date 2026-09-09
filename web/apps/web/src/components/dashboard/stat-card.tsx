import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card.js";

/** One number, named. No sparkline, no delta — nothing to compare against yet. */
export const StatCard = (props: { readonly label: string; readonly value: number; }) => (
  <Card>
    <CardHeader className="pb-2">
      <CardTitle className="text-xs font-normal text-muted-foreground">{props.label}</CardTitle>
    </CardHeader>
    <CardContent>
      <p className="font-mono text-2xl">{props.value}</p>
    </CardContent>
  </Card>
);
