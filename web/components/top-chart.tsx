"use client";

import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import type { Prediction } from "@/lib/predictions";

interface TopChartProps {
  data: Prediction[];
}

export function TopChart({ data }: TopChartProps) {
  const chartData = data.map((p) => ({
    name: p.name,
    tla: p.tla,
    adjusted: +(p.win_probability_adjusted * 100).toFixed(2),
    raw: +(p.win_probability_raw * 100).toFixed(2),
  }));

  return (
    <ResponsiveContainer width="100%" height={Math.max(360, chartData.length * 32)}>
      <BarChart
        data={chartData}
        layout="vertical"
        margin={{ top: 4, right: 32, left: 0, bottom: 4 }}
      >
        <XAxis
          type="number"
          domain={[0, "dataMax"]}
          tickFormatter={(v) => `${v}%`}
          stroke="var(--color-muted-foreground)"
          fontSize={12}
        />
        <YAxis
          type="category"
          dataKey="tla"
          width={56}
          stroke="var(--color-muted-foreground)"
          fontSize={12}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          cursor={{ fill: "var(--color-muted)", opacity: 0.2 }}
          contentStyle={{
            background: "var(--color-card)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            color: "var(--color-foreground)",
            fontSize: 12,
          }}
          formatter={(value, name) => {
            const v = typeof value === "number" ? value : Number(value);
            return [
              `${v.toFixed(1)}%`,
              name === "adjusted" ? "Adjusted" : "DC only",
            ];
          }}
          labelFormatter={(label, payload) => {
            const first = payload?.[0] as { payload?: { name?: string } } | undefined;
            return first?.payload?.name ?? String(label);
          }}
        />
        <Bar dataKey="adjusted" radius={[0, 4, 4, 0]}>
          {chartData.map((entry, idx) => (
            <Cell
              key={entry.tla}
              fill={idx === 0 ? "var(--color-chart-accent)" : "var(--color-chart-muted)"}
              fillOpacity={idx === 0 ? 1 : 0.6}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
