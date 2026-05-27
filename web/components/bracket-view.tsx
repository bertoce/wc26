import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { MatchProbabilityBar } from "@/components/match-probability-bar";
import {
  predictions,
  ROUND_FULL_NAMES,
  type KnockoutMatch,
  type KnockoutRound,
} from "@/lib/predictions";

const fmtPct = (p: number) => `${(p * 100).toFixed(1)}%`;
const fmtXG = (x: number) => x.toFixed(2);

/** Number of grid columns per round — chosen so cards are roughly square at common widths. */
const ROUND_COLS: Record<KnockoutRound["round"], string> = {
  R32: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4",
  R16: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4",
  QF: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4",
  SF: "grid-cols-1 sm:grid-cols-2",
  F: "grid-cols-1",
};

function MatchCard({
  m,
  round,
  matchNumber,
}: {
  m: KnockoutMatch;
  round: KnockoutRound["round"];
  matchNumber: number;
}) {
  const homeAdvances = m.p_home_win > m.p_away_win;
  const advancerName = homeAdvances ? m.home_top_name : m.away_top_name;
  const advancerProb = homeAdvances ? m.p_home_win : m.p_away_win;

  return (
    <Card className="bg-card border-border">
      <CardContent className="p-3 space-y-2.5">
        <div className="flex items-center justify-between text-[10px] text-muted-foreground uppercase tracking-wider font-mono">
          <span>{round} · #{matchNumber}</span>
          <span title="Probability this exact matchup occurs">
            matchup {fmtPct(m.p_matchup_top)}
          </span>
        </div>

        {/* Teams */}
        <div className="space-y-1.5">
          <TeamRow
            tla={m.home_top}
            name={m.home_top_name}
            marginal={m.p_home_top}
            highlighted={homeAdvances}
          />
          <TeamRow
            tla={m.away_top}
            name={m.away_top_name}
            marginal={m.p_away_top}
            highlighted={!homeAdvances}
          />
        </div>

        {/* W/D/L bar */}
        <div className="space-y-1">
          <MatchProbabilityBar
            pHome={m.p_home_win}
            pDraw={m.p_draw}
            pAway={m.p_away_win}
          />
          <div className="grid grid-cols-3 text-[10px] font-mono tabular-nums text-muted-foreground">
            <span className="text-emerald-400/80">H {fmtPct(m.p_home_win)}</span>
            <span className="text-center">D {fmtPct(m.p_draw)}</span>
            <span className="text-rose-400/80 text-right">{fmtPct(m.p_away_win)} A</span>
          </div>
        </div>

        {/* Most-likely advancer + xG */}
        <div className="flex items-baseline justify-between text-[11px] pt-1 border-t border-border">
          <span className="text-muted-foreground">
            advance: <span className="text-foreground font-medium">{advancerName}</span>{" "}
            <span className="font-mono">{fmtPct(advancerProb)}</span>
          </span>
          <span className="font-mono text-muted-foreground">
            xG {fmtXG(m.expected_home_goals)}–{fmtXG(m.expected_away_goals)}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

function TeamRow({
  tla,
  name,
  marginal,
  highlighted,
}: {
  tla: string;
  name: string;
  marginal: number;
  highlighted: boolean;
}) {
  return (
    <div
      className={`flex items-center justify-between gap-2 ${
        highlighted ? "text-foreground font-medium" : "text-muted-foreground"
      }`}
    >
      <div className="flex items-center gap-2 min-w-0">
        <Badge
          variant="outline"
          className={`font-mono text-[10px] ${highlighted ? "border-emerald-500/50" : ""}`}
        >
          {tla}
        </Badge>
        <span className="truncate text-sm">{name}</span>
      </div>
      <span
        className="font-mono text-[10px] tabular-nums shrink-0"
        title="Marginal probability this team reaches this slot"
      >
        {fmtPct(marginal)}
      </span>
    </div>
  );
}

export function BracketView() {
  const bracket = predictions.knockout_bracket;
  return (
    <div className="space-y-6">
      {bracket.map((round) => (
        <div key={round.round} className="space-y-2">
          <div className="flex items-baseline justify-between px-1">
            <h4 className="text-sm font-mono uppercase tracking-wider text-muted-foreground">
              {ROUND_FULL_NAMES[round.round]}
            </h4>
            <span className="text-xs text-muted-foreground">
              {round.n_matches} {round.n_matches === 1 ? "match" : "matches"}
            </span>
          </div>
          <div className={`grid gap-3 ${ROUND_COLS[round.round]}`}>
            {round.matches.map((m) => (
              <MatchCard
                key={`${round.round}-${m.match_idx}`}
                m={m}
                round={round.round}
                matchNumber={m.match_idx + 1}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
