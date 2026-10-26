import { useEffect, useState } from "react";
import { Activity, Download } from "lucide-react";
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../api/client";
import { formatBytes, toMbps } from "../lib/format";
import type { HistoryPoint } from "../types";

const RANGES = ["5m", "1h", "24h", "7d"];

export default function Analytics() {
  const [range, setRange] = useState("1h");
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [summary, setSummary] = useState<{ total_dl_bytes: number; total_ul_bytes: number; peak_dl_bps: number; peak_ul_bps: number; per_device: { id: string; dl_bytes: number; ul_bytes: number; peak_dl_bps: number }[] } | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [h, s] = await Promise.all([api.analyticsHistory(range), api.analyticsSummary(range)]);
        if (active) { setHistory(h.samples); setSummary(s); }
      } catch { /* ignore */ }
    })();
    return () => { active = false; };
  }, [range]);

  const data = history.map((p) => ({ ts: new Date(p.ts).getTime(), dl: toMbps(p.dl_bps), ul: toMbps(p.ul_bps) }));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-xl font-semibold text-ink-200">Traffic Analytics</h1>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg bg-ink-800 p-0.5">
            {RANGES.map((r) => (
              <button key={r} onClick={() => setRange(r)}
                className={`px-3 py-1 text-xs rounded-md ${range === r ? "bg-ink-700 text-white" : "text-ink-400 hover:text-ink-200"}`}>{r}</button>
            ))}
          </div>
          <a href={`/api/analytics/export?range=${range}`} className="btn-ghost"><Download className="h-4 w-4" /> Export CSV</a>
        </div>
      </div>

      {summary && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Card label="Total Downloaded" value={formatBytes(summary.total_dl_bytes)} tone="down" />
          <Card label="Total Uploaded" value={formatBytes(summary.total_ul_bytes)} tone="up" />
          <Card label="Peak Download" value={`${(summary.peak_dl_bps / 1e6).toFixed(2)} Mbps`} tone="down" />
          <Card label="Peak Upload" value={`${(summary.peak_ul_bps / 1e6).toFixed(2)} Mbps`} tone="up" />
        </div>
      )}

      <div className="card p-4">
        <h2 className="text-sm font-medium text-ink-200 mb-3">Throughput over time</h2>
        {data.length < 2 ? (
          <div className="h-56 grid place-items-center text-sm text-ink-400">No history yet for this window.</div>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="dl" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#f59e0b" stopOpacity={0.4} /><stop offset="95%" stopColor="#f59e0b" stopOpacity={0} /></linearGradient>
                <linearGradient id="ul" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#22c55e" stopOpacity={0.4} /><stop offset="95%" stopColor="#22c55e" stopOpacity={0} /></linearGradient>
              </defs>
              <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
              <XAxis dataKey="ts" tickFormatter={(v) => new Date(v).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} stroke="#6b7280" fontSize={11} minTickGap={48} />
              <YAxis stroke="#6b7280" fontSize={11} width={52} tickFormatter={(v) => `${Number(v).toFixed(0)}M`} />
              <Tooltip labelFormatter={(v) => new Date(v as number).toLocaleString()} formatter={(v, n) => [`${Number(v).toFixed(2)} Mbps`, n === "dl" ? "Download" : "Upload"]} contentStyle={{ background: "#111827", border: "1px solid #1f2937", borderRadius: 8, color: "#e5e7eb" }} />
              <Area type="monotone" dataKey="dl" name="dl" stroke="#f59e0b" fill="url(#dl)" strokeWidth={2} connectNulls={false} isAnimationActive={false} />
              <Area type="monotone" dataKey="ul" name="ul" stroke="#22c55e" fill="url(#ul)" strokeWidth={2} connectNulls={false} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="card p-4">
        <h2 className="text-sm font-medium text-ink-200 mb-3">Per-device usage</h2>
        {!summary?.per_device?.length ? (
          <div className="text-sm text-ink-400">No per-device data yet (connect clients to a hotspot).</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-ink-400 text-xs uppercase"><tr><th className="text-left font-medium pb-2">Device</th><th className="text-right font-medium pb-2">Downloaded</th><th className="text-right font-medium pb-2">Uploaded</th><th className="text-right font-medium pb-2">Peak DL</th></tr></thead>
            <tbody className="divide-y divide-ink-800">
              {summary.per_device.map((d) => (
                <tr key={d.id}><td className="py-2 font-mono text-xs text-ink-200">{d.id.slice(0, 8)}</td><td className="py-2 text-right text-accent-down">{formatBytes(d.dl_bytes)}</td><td className="py-2 text-right text-accent-up">{formatBytes(d.ul_bytes)}</td><td className="py-2 text-right text-ink-200">{(d.peak_dl_bps / 1e6).toFixed(2)} Mbps</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <p className="text-xs text-ink-400 flex items-center gap-1"><Activity className="h-3 w-3" /> History is downsampled SQLite buckets; no secrets are stored or exported.</p>
    </div>
  );
}

function Card({ label, value, tone }: { label: string; value: string; tone: "up" | "down" }) {
  return (
    <div className="card p-4">
      <div className="text-xs uppercase text-ink-400">{label}</div>
      <div className={`mt-2 text-2xl font-semibold tabular-nums ${tone === "down" ? "text-accent-down" : "text-accent-up"}`}>{value}</div>
    </div>
  );
}
