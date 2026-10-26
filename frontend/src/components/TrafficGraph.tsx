import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TrafficPoint } from "../hooks/useMonitor";
import { toMbps } from "../lib/format";

interface TrafficGraphProps {
  data: TrafficPoint[]; // last `windowSeconds` worth of points
}

function fmtTime(ms: number): string {
  return new Date(ms).toLocaleTimeString([], {
    hour12: false,
    minute: "2-digit",
    second: "2-digit",
  });
}

function fmtMbps(v: number | null): string {
  if (v === null) return "Unavailable";
  if (v >= 1) return `${v.toFixed(2)} Mbps`;
  return `${(v * 1000).toFixed(0)} kbps`;
}

export default function TrafficGraph({ data }: TrafficGraphProps) {
  const chartData = data.map((p) => ({
    t: p.t,
    dl: toMbps(p.dl),
    ul: toMbps(p.ul),
  }));

  if (chartData.length < 2) {
    return (
      <div className="h-[220px] grid place-items-center text-sm text-ink-400">
        Collecting live samples…
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
        <XAxis
          dataKey="t"
          tickFormatter={fmtTime}
          stroke="#6b7280"
          fontSize={11}
          minTickGap={48}
        />
        <YAxis
          stroke="#6b7280"
          fontSize={11}
          width={52}
          tickFormatter={(v) => `${Number(v).toFixed(v % 1 ? 1 : 0)}M`}
        />
        <Tooltip
          labelFormatter={fmtTime}
          formatter={(value, name) => [
            fmtMbps(value as number | null),
            name === "dl" ? "Download" : "Upload",
          ]}
          contentStyle={{
            background: "#111827",
            border: "1px solid #1f2937",
            borderRadius: 8,
            color: "#e5e7eb",
          }}
          labelStyle={{ color: "#9ca3af" }}
        />
        <Line
          type="monotone"
          dataKey="dl"
          name="dl"
          stroke="#f59e0b"
          dot={false}
          strokeWidth={2}
          connectNulls={false}
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="ul"
          name="ul"
          stroke="#22c55e"
          dot={false}
          strokeWidth={2}
          connectNulls={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
