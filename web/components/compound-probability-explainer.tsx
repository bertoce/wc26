import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { predictions, ROUND_ORDER, ROUND_LABEL, type RoundKey } from "@/lib/predictions";

const fmt = (p: number) => `${(p * 100).toFixed(1)}%`;
const fmtPP = (p: number) => `${(p * 100).toFixed(1)}pp`;

const ROUND_FULL: Record<RoundKey, string> = {
  reach_r32: "Round of 32",
  reach_r16: "Round of 16",
  reach_qf: "Quarter-final",
  reach_sf: "Semi-final",
  reach_final: "Final",
  win: "Champion",
};

/** Top team by raw win probability (the chain ends at the raw number — priors
 * are applied after the simulator and don't decompose per round). */
function chainFor(round_probability: Partial<Record<RoundKey, number>>) {
  return ROUND_ORDER.map((r) => ({
    key: r,
    label: ROUND_LABEL[r],
    full: ROUND_FULL[r],
    p: round_probability[r] ?? 0,
  }));
}

export function CompoundProbabilityExplainer() {
  // Use the team with the highest raw win prob for the cleanest illustration
  const top = [...predictions.predictions].sort(
    (a, b) => b.win_probability_raw - a.win_probability_raw,
  )[0];
  if (!top?.round_probability) return null;

  const chain = chainFor(top.round_probability);
  const priorDelta =
    (top.win_probability_adjusted - top.win_probability_raw) * 100;
  const priorSign = priorDelta >= 0 ? "+" : "";

  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-base font-medium">
          Why a {fmt(top.win_probability_raw)} cup probability isn&apos;t a big number
        </CardTitle>
        <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
          A team&apos;s chance of winning is the product of surviving every round.
          Every step drops some probability — even {top.name}, the model&apos;s
          favourite, only has to lose once. The chain below shows how their{" "}
          {fmt(top.round_probability.reach_r32 ?? 0)} chance of escaping the
          group stage shrinks at each cut.
        </p>
      </CardHeader>
      <CardContent>
        {/* Stepped chain */}
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
          {chain.map((step, i) => {
            const prev = i > 0 ? chain[i - 1].p : 1;
            const drop = prev - step.p;
            const dropPct = prev > 0 ? drop / prev : 0;
            return (
              <div
                key={step.key}
                className="rounded-md border border-border bg-background/30 p-3 space-y-1"
              >
                <div className="flex items-baseline justify-between gap-1">
                  <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-mono">
                    {step.label}
                  </span>
                  {i > 0 && (
                    <span
                      className="text-[10px] text-rose-400/80 font-mono tabular-nums"
                      title={`Lost ${fmtPP(drop)} of probability (${(dropPct * 100).toFixed(0)}% of remaining) at this round`}
                    >
                      −{fmtPP(drop)}
                    </span>
                  )}
                </div>
                <div className="text-xl sm:text-2xl font-mono tabular-nums font-semibold">
                  {fmt(step.p)}
                </div>
                <div className="text-[10px] text-muted-foreground leading-tight">
                  reach {step.full.toLowerCase()}
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer math */}
        <div className="mt-4 pt-3 border-t border-border space-y-1.5 text-xs text-muted-foreground">
          <div>
            <span className="text-foreground font-mono">{fmt(top.round_probability.reach_r32 ?? 0)}</span>{" "}
            ×{" "}
            <span className="text-foreground font-mono">
              {((top.round_probability.reach_r16 ?? 0) /
                (top.round_probability.reach_r32 || 1) *
                100
              ).toFixed(0)}
              %
            </span>{" "}
            ×{" "}
            <span className="text-foreground font-mono">
              {((top.round_probability.reach_qf ?? 0) /
                (top.round_probability.reach_r16 || 1) *
                100
              ).toFixed(0)}
              %
            </span>{" "}
            ×{" "}
            <span className="text-foreground font-mono">
              {((top.round_probability.reach_sf ?? 0) /
                (top.round_probability.reach_qf || 1) *
                100
              ).toFixed(0)}
              %
            </span>{" "}
            ×{" "}
            <span className="text-foreground font-mono">
              {((top.round_probability.reach_final ?? 0) /
                (top.round_probability.reach_sf || 1) *
                100
              ).toFixed(0)}
              %
            </span>{" "}
            ×{" "}
            <span className="text-foreground font-mono">
              {((top.round_probability.win ?? 0) /
                (top.round_probability.reach_final || 1) *
                100
              ).toFixed(0)}
              %
            </span>{" "}
            ≈{" "}
            <span className="text-foreground font-mono font-medium">
              {fmt(top.win_probability_raw)}
            </span>
            <span className="ml-2 text-[11px]">
              (P at each round &divide; P at previous = conditional advance rate)
            </span>
          </div>
          <div>
            Pattern priors then nudge the published number to{" "}
            <span className="text-foreground font-mono font-medium">
              {fmt(top.win_probability_adjusted)}
            </span>{" "}
            <span
              className={priorDelta >= 0 ? "text-emerald-400" : "text-rose-400"}
            >
              ({priorSign}
              {priorDelta.toFixed(1)}pp from confederation + pedigree + market value)
            </span>
            .
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
