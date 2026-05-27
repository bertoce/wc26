import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { MatchProbabilityBar } from "@/components/match-probability-bar";
import type { GroupMatch } from "@/lib/predictions";
import { matchesByGroup } from "@/lib/predictions";

const fmtPct = (p: number) => `${(p * 100).toFixed(1)}%`;
const fmtXG = (x: number) => x.toFixed(2);

function fmtDate(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  return (
    d.toLocaleDateString("en-US", { month: "short", day: "numeric" }) +
    " · " +
    d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
  );
}

function MatchRow({ m }: { m: GroupMatch }) {
  // Highlight the most-likely outcome among H/D/A
  const outcomes = [
    { key: "H", p: m.p_home_win },
    { key: "D", p: m.p_draw },
    { key: "A", p: m.p_away_win },
  ];
  const mostLikely = outcomes.reduce((acc, o) => (o.p > acc.p ? o : acc));
  return (
    <div className="space-y-2 py-3 border-b border-border last:border-0">
      <div className="flex items-baseline justify-between gap-3 text-xs text-muted-foreground">
        <span className="font-mono">{fmtDate(m.utc_date)}</span>
        <span className="font-mono">
          xG {fmtXG(m.expected_home_goals)}–{fmtXG(m.expected_away_goals)}
        </span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Badge variant="outline" className="font-mono text-[10px]">
            {m.home}
          </Badge>
          <span className="truncate text-sm">{m.home_name}</span>
        </div>
        <div className="text-xs text-muted-foreground font-mono shrink-0">
          vs
        </div>
        <div className="flex items-center gap-2 min-w-0 justify-end">
          <span className="truncate text-sm text-right">{m.away_name}</span>
          <Badge variant="outline" className="font-mono text-[10px]">
            {m.away}
          </Badge>
        </div>
      </div>
      <MatchProbabilityBar
        pHome={m.p_home_win}
        pDraw={m.p_draw}
        pAway={m.p_away_win}
      />
      <div className="grid grid-cols-3 text-xs font-mono tabular-nums">
        <span
          className={
            mostLikely.key === "H"
              ? "text-emerald-400 font-medium"
              : "text-muted-foreground"
          }
        >
          H {fmtPct(m.p_home_win)}
        </span>
        <span
          className={`text-center ${
            mostLikely.key === "D"
              ? "text-foreground font-medium"
              : "text-muted-foreground"
          }`}
        >
          D {fmtPct(m.p_draw)}
        </span>
        <span
          className={`text-right ${
            mostLikely.key === "A"
              ? "text-rose-400 font-medium"
              : "text-muted-foreground"
          }`}
        >
          {fmtPct(m.p_away_win)} A
        </span>
      </div>
    </div>
  );
}

export function GroupMatchesSection() {
  const grouped = matchesByGroup();
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {[...grouped.entries()].map(([group, matches]) => (
        <Card key={group} className="bg-card border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-mono uppercase tracking-wider text-muted-foreground">
              Group {group}
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {matches.map((m) => (
              <MatchRow key={`${m.home}-${m.away}-${m.utc_date}`} m={m} />
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
