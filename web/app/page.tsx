import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { WinnerCard } from "@/components/winner-card";
import { TopChart } from "@/components/top-chart";
import { PredictionsTable } from "@/components/predictions-table";
import { predictions, topN } from "@/lib/predictions";

export default function Home() {
  const all = predictions.predictions;
  const top12 = topN(12);
  const winner = top12[0];
  const runnerUp = top12[1];
  const meta = predictions.metadata;
  const generatedAt = new Date(meta.generated_at);

  return (
    <main className="mx-auto w-full max-w-5xl px-4 sm:px-6 py-10 sm:py-14 space-y-8">
      {/* Header */}
      <header className="space-y-1">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-muted-foreground">
          wc26 · model v{meta.model_version}
        </p>
        <h2 className="text-lg font-medium text-muted-foreground">
          Dixon-Coles + historical-pattern model · 20,000 Monte Carlo tournaments
        </h2>
      </header>

      {/* Hero */}
      <WinnerCard winner={winner} runnerUp={runnerUp} />

      {/* Metadata strip */}
      <Card className="bg-card/50 border-border">
        <CardContent className="p-4 grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          <Stat label="Simulations" value={meta.n_sims.toLocaleString()} />
          <Stat label="Teams" value={meta.n_teams.toString()} />
          <Stat label="Group fixtures" value={meta.n_group_fixtures.toString()} />
          <Stat
            label="DC fit matches"
            value={meta.dc_fit_matches.toLocaleString()}
          />
          <Stat
            label="Home advantage γ"
            value={meta.dc_home_advantage.toFixed(3)}
            mono
          />
          <Stat label="Dixon-Coles ρ" value={meta.dc_rho.toFixed(3)} mono />
          <Stat label="Host continent" value={meta.host_continent} />
          <Stat
            label="Generated"
            value={generatedAt.toISOString().slice(0, 16).replace("T", " ")}
            mono
          />
        </CardContent>
      </Card>

      {/* Top 12 chart */}
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="text-base font-medium">
            Top 12 — adjusted win probability
          </CardTitle>
        </CardHeader>
        <CardContent>
          <TopChart data={top12} />
        </CardContent>
      </Card>

      {/* Full table */}
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="text-base font-medium">
            All {all.length} qualified teams
          </CardTitle>
        </CardHeader>
        <CardContent className="px-0 sm:px-6 pb-0 sm:pb-6">
          <PredictionsTable data={all} />
        </CardContent>
      </Card>

      {/* Footer */}
      <footer className="text-xs text-muted-foreground leading-relaxed space-y-1 pb-8">
        <p>
          Per-match model: Dixon-Coles Poisson fit on{" "}
          {meta.dc_fit_matches.toLocaleString()} competitive matches since 2018
          (martj42/international_results). Pattern priors blend confederation,
          host-continent, title pedigree, and squad market value.
        </p>
        <p>
          Caveats: simplified knockout bracket pairing; no injury data; pattern
          priors hand-calibrated; squad market values are estimates. Run with
          seed {meta.seed}.
        </p>
      </footer>
    </main>
  );
}

function Stat({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <div className="text-muted-foreground text-xs uppercase tracking-wider">
        {label}
      </div>
      <div
        className={`mt-1 ${mono ? "font-mono" : ""} tabular-nums text-foreground`}
      >
        {value}
      </div>
    </div>
  );
}
