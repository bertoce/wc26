/** Three-segment stacked bar showing P(home win) / P(draw) / P(away win). */
export function MatchProbabilityBar({
  pHome,
  pDraw,
  pAway,
}: {
  pHome: number;
  pDraw: number;
  pAway: number;
}) {
  const home = Math.max(0, Math.min(1, pHome)) * 100;
  const draw = Math.max(0, Math.min(1, pDraw)) * 100;
  const away = Math.max(0, Math.min(1, pAway)) * 100;
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted">
      <div
        className="bg-emerald-500/80"
        style={{ width: `${home}%` }}
        title={`Home win ${home.toFixed(1)}%`}
      />
      <div
        className="bg-muted-foreground/40"
        style={{ width: `${draw}%` }}
        title={`Draw ${draw.toFixed(1)}%`}
      />
      <div
        className="bg-rose-500/80"
        style={{ width: `${away}%` }}
        title={`Away win ${away.toFixed(1)}%`}
      />
    </div>
  );
}
