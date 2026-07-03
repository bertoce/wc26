import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { KnockoutR32Match } from "@/lib/predictions";
import { knockoutR32 } from "@/lib/predictions";

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

const TIER_LABEL: Record<KnockoutR32Match["tier"], string> = {
  strong: "strong call",
  lean: "lean",
  tossup: "toss-up",
};
const TIER_CLASS: Record<KnockoutR32Match["tier"], string> = {
  strong: "border-emerald-500/40 text-emerald-300",
  lean: "border-amber-500/40 text-amber-300",
  tossup: "border-muted-foreground/40 text-muted-foreground",
};

/** How a finished tie was settled, in short form. */
function resultLine(m: KnockoutR32Match): string {
  const h = m.actual_home_goals ?? 0;
  const a = m.actual_away_goals ?? 0;
  if (m.resolution === "PENALTY_SHOOTOUT") {
    return `${h}–${a} · ${m.pens_home}–${m.pens_away} pens`;
  }
  if (m.resolution === "EXTRA_TIME") {
    return `${h}–${a} · a.e.t.`;
  }
  return `${h}–${a}`;
}

/** Four-segment bar: home-win / home-adv-in-ET / away-adv-in-ET / away-win.
 * The two greens are "home side advances", the two reds "away side advances";
 * the lighter middle segments are the extra-time/penalty paths. */
function OutcomeBar({ m }: { m: KnockoutR32Match }) {
  const seg = (p: number) => Math.max(0, Math.min(1, p)) * 100;
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted">
      <div className="bg-emerald-500/80" style={{ width: `${seg(m.p_home_win_reg)}%` }}
        title={`${m.home_name} win in 90' ${fmtPct(m.p_home_win_reg)}`} />
      <div className="bg-emerald-500/30" style={{ width: `${seg(m.p_draw_home_adv)}%` }}
        title={`Draw, ${m.home_name} advance (ET/pens) ${fmtPct(m.p_draw_home_adv)}`} />
      <div className="bg-rose-500/30" style={{ width: `${seg(m.p_draw_away_adv)}%` }}
        title={`Draw, ${m.away_name} advance (ET/pens) ${fmtPct(m.p_draw_away_adv)}`} />
      <div className="bg-rose-500/80" style={{ width: `${seg(m.p_away_win_reg)}%` }}
        title={`${m.away_name} win in 90' ${fmtPct(m.p_away_win_reg)}`} />
    </div>
  );
}

function R32Row({ m }: { m: KnockoutR32Match }) {
  const finished = m.status === "FINISHED";
  const homeAdvances = m.actual_advancer === "H";
  return (
    <div className="space-y-2 py-3 border-b border-border last:border-0">
      <div className="flex items-baseline justify-between gap-3 text-xs text-muted-foreground">
        {finished ? (
          <span className="flex items-center gap-2">
            <Badge className="bg-foreground text-background font-mono text-[10px] px-1.5">
              {resultLine(m)}
            </Badge>
            <span
              className={`font-mono text-[10px] ${
                m.prediction_hit ? "text-emerald-400" : "text-rose-400"
              }`}
              title={
                m.prediction_hit
                  ? "The model's favoured team advanced"
                  : "The model's favoured team did NOT advance"
              }
            >
              {m.prediction_hit ? "✓ advancer" : "✗ upset"}
            </span>
          </span>
        ) : (
          <span className="font-mono">{fmtDate(m.utc_date)}</span>
        )}
        <span className="font-mono">
          {m.host_home ? "host · " : ""}xG {fmtXG(m.expected_home_goals)}–{fmtXG(m.expected_away_goals)}
        </span>
      </div>

      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Badge variant="outline" className="font-mono text-[10px]">{m.home}</Badge>
          <span
            className={`truncate text-sm ${finished && homeAdvances ? "font-semibold" : finished ? "text-muted-foreground" : ""}`}
          >
            {m.home_name}
          </span>
        </div>
        <div className="text-xs text-muted-foreground font-mono shrink-0">vs</div>
        <div className="flex items-center gap-2 min-w-0 justify-end">
          <span
            className={`truncate text-sm text-right ${finished && !homeAdvances ? "font-semibold" : finished ? "text-muted-foreground" : ""}`}
          >
            {m.away_name}
          </span>
          <Badge variant="outline" className="font-mono text-[10px]">{m.away}</Badge>
        </div>
      </div>

      <OutcomeBar m={m} />

      <div className="flex items-center justify-between text-xs font-mono tabular-nums">
        <span className="text-emerald-400">{fmtPct(m.p_home_advances)} adv</span>
        <span
          className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${TIER_CLASS[m.tier]}`}
          title="Confidence tier on the advance call"
        >
          {TIER_LABEL[m.tier]}
        </span>
        <span className="text-rose-400">adv {fmtPct(m.p_away_advances)}</span>
      </div>
    </div>
  );
}

/** "Advancer correctly predicted N of M decided ties" summary. */
function R32AccuracySummary({ matches }: { matches: KnockoutR32Match[] }) {
  const decided = matches.filter((m) => m.status === "FINISHED");
  if (decided.length === 0) return null;
  const hits = decided.filter((m) => m.prediction_hit).length;
  return (
    <div className="rounded-md border border-border bg-card/50 px-4 py-3 text-sm">
      <span className="font-medium">
        Advancer scoreboard: {hits}/{decided.length}
      </span>{" "}
      <span className="text-muted-foreground">
        decided R32 ties where the model&apos;s favoured team advanced. These
        predictions are inherently pre-match — the model&apos;s ratings only
        ever ingest group-stage results, never knockout ones, so an R32
        forecast is identical before and after the tie is played.
      </span>
    </div>
  );
}

export function R32MatchesSection() {
  const matches = knockoutR32();
  if (matches.length === 0) return null;
  return (
    <div className="space-y-4">
      <R32AccuracySummary matches={matches} />
      <div className="grid gap-4 sm:grid-cols-2">
        {matches.map((m) => (
          <Card key={`${m.home}-${m.away}`} className="bg-card border-border">
            <CardContent className="pt-4">
              <R32Row m={m} />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
