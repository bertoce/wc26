import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import {
  predictions,
  ROUND_LABEL,
  ROUND_ORDER,
  type Prediction,
} from "@/lib/predictions";

const fmt = (p: number | undefined) =>
  p === undefined ? "—" : `${(p * 100).toFixed(1)}%`;

/** Color a probability cell on a green→muted scale. */
function cellTone(p: number | undefined): string {
  if (p === undefined) return "text-muted-foreground";
  if (p >= 0.5) return "text-emerald-400 font-medium";
  if (p >= 0.25) return "text-emerald-400/70";
  if (p >= 0.05) return "text-foreground";
  return "text-muted-foreground";
}

export function RoundProbabilitiesTable() {
  // Sort by P(reach_r32) descending so the most likely advancers lead
  const sorted: Prediction[] = [...predictions.predictions].sort((a, b) => {
    const pa = a.round_probability?.reach_r32 ?? 0;
    const pb = b.round_probability?.reach_r32 ?? 0;
    return pb - pa;
  });
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-12 text-right">#</TableHead>
          <TableHead className="w-16">Code</TableHead>
          <TableHead>Team</TableHead>
          {ROUND_ORDER.map((r) => (
            <TableHead key={r} className="text-right font-mono text-xs">
              {ROUND_LABEL[r]}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((p, i) => (
          <TableRow key={p.tla}>
            <TableCell className="text-right text-muted-foreground tabular-nums">
              {i + 1}
            </TableCell>
            <TableCell>
              <Badge variant="outline" className="font-mono text-xs">
                {p.tla}
              </Badge>
            </TableCell>
            <TableCell className="font-medium">{p.name}</TableCell>
            {ROUND_ORDER.map((r) => {
              const val = p.round_probability?.[r];
              return (
                <TableCell
                  key={r}
                  className={`text-right font-mono tabular-nums ${cellTone(val)}`}
                >
                  {fmt(val)}
                </TableCell>
              );
            })}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
