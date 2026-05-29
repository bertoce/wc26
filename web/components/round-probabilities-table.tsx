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

/** Round columns to render — everything except `win`, which gets special
 * handling below so it shows the prior-adjusted number (the published headline)
 * instead of the raw simulator output. The R32→Final columns ARE the raw
 * simulator output (priors only affect the final outcome, not per-round survival). */
const RAW_ROUND_COLUMNS = ROUND_ORDER.filter((r) => r !== "win");

export function RoundProbabilitiesTable() {
  // Sort by the published (adjusted) cup probability so the table's row order
  // matches the chart + winner card above. Without this, teams in weak groups
  // floated up because they had higher P(reach_r32) than actual favourites.
  const sorted: Prediction[] = [...predictions.predictions].sort(
    (a, b) => b.win_probability_adjusted - a.win_probability_adjusted,
  );
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-12 text-right">#</TableHead>
          <TableHead className="w-16">Code</TableHead>
          <TableHead>Team</TableHead>
          {RAW_ROUND_COLUMNS.map((r) => (
            <TableHead key={r} className="text-right font-mono text-xs">
              {ROUND_LABEL[r]}
            </TableHead>
          ))}
          <TableHead
            className="text-right font-mono text-xs"
            title="Adjusted win probability — matches the headline + chart. Pattern priors (confederation, host-continent, pedigree, market value) are applied here only, not to earlier rounds."
          >
            Win<span className="text-muted-foreground">*</span>
          </TableHead>
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
            {RAW_ROUND_COLUMNS.map((r) => {
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
            <TableCell
              className={`text-right font-mono tabular-nums ${cellTone(p.win_probability_adjusted)}`}
            >
              {fmt(p.win_probability_adjusted)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
