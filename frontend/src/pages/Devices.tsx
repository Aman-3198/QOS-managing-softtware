import { useCallback, useEffect, useState } from "react";
import {
  ListChecks,
  Pencil,
  RefreshCw,
  Wifi,
} from "lucide-react";
import { api } from "../api/client";
import { classNames, formatBps, formatBytes } from "../lib/format";
import type { DeviceInfo } from "../types";

export default function Devices() {
  const [devices, setDevices] = useState<DeviceInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const d = await api.devices();
      setDevices(d.devices);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load devices");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = window.setInterval(refresh, 2000);
    return () => window.clearInterval(t);
  }, [refresh]);

  const onRename = async (d: DeviceInfo) => {
    const next = window.prompt("Device label", d.label ?? d.hostname ?? "");
    if (next === null) return; // cancelled
    setRenaming(d.id);
    try {
      await api.patchDevice(d.id, next.trim() === "" ? null : next.trim());
      await refresh();
    } catch (e) {
      window.alert(e instanceof Error ? e.message : "rename failed");
    } finally {
      setRenaming(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-ink-200">Connected Devices</h1>
          <p className="text-sm text-ink-400 mt-1">
            {devices.length} hotspot client{devices.length === 1 ? "" : "s"} ·
            discovered from AP stations + neighbor table
          </p>
        </div>
        <button onClick={refresh} className="btn-ghost" disabled={loading}>
          <RefreshCw className={classNames("h-4 w-4", loading && "animate-spin")} />
        </button>
      </div>

      {error && (
        <div className="card p-3 border-accent-down/40 text-sm text-accent-down">
          {error}
        </div>
      )}

      {loading && devices.length === 0 ? (
        <div className="card p-8 text-center text-sm text-ink-400">
          Discovering devices…
        </div>
      ) : devices.length === 0 ? (
        <EmptyState />
      ) : (
        <>
          {/* Desktop table */}
          <div className="hidden md:block card overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-ink-800/50 text-ink-400 text-xs uppercase">
                <tr>
                  <th className="text-left font-medium px-4 py-2">Device</th>
                  <th className="text-left font-medium px-4 py-2">IP</th>
                  <th className="text-left font-medium px-4 py-2">MAC</th>
                  <th className="text-right font-medium px-4 py-2">Down</th>
                  <th className="text-right font-medium px-4 py-2">Up</th>
                  <th className="text-right font-medium px-4 py-2">Downloaded</th>
                  <th className="text-left font-medium px-4 py-2">Signal</th>
                  <th className="text-left font-medium px-4 py-2">Limit</th>
                  <th className="px-4 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-800">
                {devices.map((d) => (
                  <DeviceRow key={d.id} d={d} renaming={renaming === d.id} onRename={() => onRename(d)} />
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="md:hidden space-y-3">
            {devices.map((d) => (
              <DeviceCard key={d.id} d={d} renaming={renaming === d.id} onRename={() => onRename(d)} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="card p-10 text-center">
      <ListChecks className="h-10 w-10 mx-auto mb-3 text-ink-400" />
      <h2 className="text-sm font-medium text-ink-200">No devices connected</h2>
      <p className="text-xs text-ink-400 mt-2 max-w-md mx-auto">
        Start a Wi-Fi hotspot in Hotspot Settings and connect a phone or laptop to
        it. Connected clients appear here automatically — never fabricated.
      </p>
    </div>
  );
}

function displayName(d: DeviceInfo): string {
  return d.label ?? d.hostname ?? (d.mac ? d.mac.slice(-5).toUpperCase() : d.id.slice(0, 8));
}

function limitLabel(d: DeviceInfo): string {
  const has = (v: number | null) => v !== null && v !== undefined;
  if (!has(d.dl_limit_mbps) && !has(d.ul_limit_mbps)) return "—";
  const parts: string[] = [];
  if (has(d.dl_limit_mbps)) parts.push(`↓${d.dl_limit_mbps}M`);
  if (has(d.ul_limit_mbps)) parts.push(`↑${d.ul_limit_mbps}M`);
  return parts.join(" ");
}

function DeviceRow({ d, renaming, onRename }: { d: DeviceInfo; renaming: boolean; onRename: () => void }) {
  return (
    <tr className="hover:bg-ink-800/30">
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <Wifi className="h-4 w-4 text-ink-400" />
          <div>
            <div className="text-ink-200 font-medium">{displayName(d)}</div>
            <div className="text-xs text-ink-400">
              {d.sources.join(", ")} · {d.connected_time_s != null ? `${d.connected_time_s}s` : "—"}
            </div>
          </div>
        </div>
      </td>
      <td className="px-4 py-3 font-mono text-xs text-ink-200">{d.ip ?? "—"}</td>
      <td className="px-4 py-3 font-mono text-xs text-ink-400">{d.mac ?? "—"}</td>
      <td className="px-4 py-3 text-right tabular-nums text-accent-down">{formatBps(d.dl_bps)}</td>
      <td className="px-4 py-3 text-right tabular-nums text-accent-up">{formatBps(d.ul_bps)}</td>
      <td className="px-4 py-3 text-right tabular-nums text-ink-200">{formatBytes(d.dl_bytes)}</td>
      <td className="px-4 py-3 text-ink-400">{d.signal_dbm != null ? `${d.signal_dbm} dBm` : "—"}</td>
      <td className="px-4 py-3 text-ink-400">{limitLabel(d)}</td>
      <td className="px-4 py-3 text-right">
        <button onClick={onRename} disabled={renaming} className="btn-ghost px-2 py-1" title="Rename">
          <Pencil className="h-3.5 w-3.5" />
        </button>
      </td>
    </tr>
  );
}

function DeviceCard({ d, renaming, onRename }: { d: DeviceInfo; renaming: boolean; onRename: () => void }) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Wifi className="h-4 w-4 text-ink-400" />
          <span className="text-ink-200 font-medium">{displayName(d)}</span>
        </div>
        <button onClick={onRename} disabled={renaming} className="btn-ghost px-2 py-1">
          <Pencil className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-y-2 text-xs">
        <Field label="IP" value={d.ip ?? "—"} mono />
        <Field label="MAC" value={d.mac ?? "—"} mono />
        <Field label="Down" value={formatBps(d.dl_bps)} />
        <Field label="Up" value={formatBps(d.ul_bps)} />
        <Field label="Downloaded" value={formatBytes(d.dl_bytes)} />
        <Field label="Signal" value={d.signal_dbm != null ? `${d.signal_dbm} dBm` : "—"} />
      </div>
      <div className="mt-2 text-xs text-ink-400">
        {d.sources.join(", ")} · limit {limitLabel(d)}
      </div>
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-ink-400">{label}</div>
      <div className={classNames("text-ink-200", mono && "font-mono")}>{value}</div>
    </div>
  );
}
