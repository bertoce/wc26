import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import type { Prediction } from "@/lib/predictions";

interface PredictionsTableProps {
  data: Prediction[];
}

const fmt = (p: number) => `${(p * 100).toFixed(2)}%`;

export function PredictionsTable({ data }: PredictionsTableProps) {
  const sorted = [...data].sort(
    (a, b) => b.win_probability_adjusted - a.win_probability_adjusted,
  );
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-12 text-right">#</TableHead>
          <TableHead className="w-16">Code</TableHead>
          <TableHead>Team</TableHead>
          <TableHead className="text-right">Win prob (adj.)</TableHead>
          <TableHead className="text-right hidden sm:table-cell">
            DC only
          </TableHead>
          <TableHead className="text-right hidden sm:table-cell">
            Δ priors
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((p, i) => {
          const delta = (p.win_probability_adjusted - p.win_probability_raw) * 100;
          const deltaSign = delta >= 0 ? "+" : "";
          return (
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
              <TableCell className="text-right font-mono tabular-nums">
                {fmt(p.win_probability_adjusted)}
              </TableCell>
              <TableCell className="text-right font-mono tabular-nums text-muted-foreground hidden sm:table-cell">
                {fmt(p.win_probability_raw)}
              </TableCell>
              <TableCell
                className={`text-right font-mono tabular-nums hidden sm:table-cell ${
                  delta >= 0 ? "text-emerald-400" : "text-rose-400"
                }`}
              >
                {deltaSign}
                {delta.toFixed(2)}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
