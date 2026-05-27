import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { Prediction } from "@/lib/predictions";

interface WinnerCardProps {
  winner: Prediction;
  runnerUp: Prediction;
}

const fmt = (p: number) => `${(p * 100).toFixed(1)}%`;

export function WinnerCard({ winner, runnerUp }: WinnerCardProps) {
  return (
    <Card className="bg-card border-border">
      <CardContent className="p-8 sm:p-10">
        <div className="flex items-center gap-2 mb-2 text-muted-foreground text-xs uppercase tracking-wider">
          <Badge variant="outline" className="font-mono">
            Predicted champion
          </Badge>
          <span>·  FIFA World Cup 2026</span>
        </div>
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mt-4">
          <div>
            <h1 className="text-5xl sm:text-6xl font-semibold tracking-tight">
              {winner.name}
            </h1>
            <p className="text-muted-foreground mt-2 text-sm">
              Runner-up by probability:&nbsp;
              <span className="text-foreground font-medium">
                {runnerUp.name}
              </span>{" "}
              ({fmt(runnerUp.win_probability_adjusted)})
            </p>
          </div>
          <div className="text-right">
            <div className="text-5xl sm:text-6xl font-mono font-semibold tabular-nums">
              {fmt(winner.win_probability_adjusted)}
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              win probability
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
