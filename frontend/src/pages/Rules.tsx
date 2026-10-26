import { useEffect, useState } from "react";
import { HardDrive, Pause, Play, ShieldAlert, Wifi } from "lucide-react";
import { api } from "../api/client";
import { classNames } from "../lib/format";
import type { DeviceInfo, Priority } from "../types";

const PRIORITIES: Priority[] = ["low", "normal", "high", "critical"];

export default function Rules() {
  const [devices, setDevices] = useState<DeviceInfo[]>([]);
  const [helper, setHelper] = useState<string>("unknown");
  const [error, setError] = useState<string | null>(null);
  const [restarting, setRestarting] = useState(false);

  const refresh = async () => {
    try {
      const [d, h] = await Promise.all([api.devices(), api.health()]);
      setDevices(d.devices);
      setHelper(h.helper);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "load failed");
    }
  };

  const restartHelper = async () => {
    setRestarting(true);
    setError(null);
    try {
      const r = await api.restartHelper();
      if (r.ok) {
        await refresh();
        setError(null);
      } else {
        setError(r.error || "Restart failed — see terminal for details.");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "restart failed");
    } finally {
      setRestarting(false);
    }
  };

  useEffect(() => {
    refresh();
    const t = window.setInterval(refresh, 2000);
    return () => window.clearInterval(t);
  }, []);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-ink-200">Bandwidth Rules</h1>
        <p className="text-sm text-ink-400 mt-1">
          Per-device upload/download limits and priorities, enforced by Linux HTB +
          nftables through the privileged helper. Limits are verified, not simulated.
        </p>
      </div>

      <div
        className={classNames(
          "card p-3 text-sm flex items-center justify-between gap-2",
          helper === "reachable"
            ? "text-accent-up"
            : "text-accent-warn border-accent-warn/40"
        )}
      >
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4" />
          Privileged helper: <span className="font-medium">{helper}</span>
          {helper !== "reachable" && (
            <span className="text-ink-400">
              · limits cannot be applied until the helper runs
            </span>
          )}
        </div>
        <button
          onClick={restartHelper}
          disabled={restarting || helper !== "reachable"}
          className="btn-ghost text-xs px-2 py-1"
          title="Re-exec the helper with the latest code on disk"
        >
          {restarting ? "Restarting…" : "↻ Restart Helper"}
        </button>
      </div>

      {error && <div className="card p-3 text-sm text-accent-down">{error}</div>}

      {devices.length === 0 ? (
        <div className="card p-10 text-center">
          <HardDrive className="h-10 w-10 mx-auto mb-3 text-ink-400" />
          <h2 className="text-sm font-medium text-ink-200">No connected devices</h2>
          <p className="text-xs text-ink-400 mt-2 max-w-md mx-auto">
            Start a Wi-Fi hotspot and connect a client to set per-device bandwidth
            limits here. Rules persist and re-apply when devices reconnect.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {devices.map((d) => (
            <DeviceEditor key={d.id} d={d} helperOk={helper === "reachable"} onChanged={refresh} />
          ))}
        </div>
      )}

      <PoliciesPanel />

      <div className="card p-4 text-xs text-ink-400">
        <p className="font-medium text-ink-200 mb-1">To enable real shaping</p>
        <ol className="list-decimal list-inside space-y-1">
          <li>One-time: <code className="text-ink-200">sudo bash privileged-helper/setup.sh</code></li>
          <li>Start the helper: <code className="text-ink-200">sudo python3 privileged-helper/helper.py</code></li>
          <li>Start a hotspot (Phase 6) so clients have IPs to shape.</li>
        </ol>
      </div>
    </div>
  );
}

function DeviceEditor({ d, helperOk, onChanged }: { d: DeviceInfo; helperOk: boolean; onChanged: () => void }) {
  const [dl, setDl] = useState(d.dl_limit_mbps?.toString() ?? "");
  const [ul, setUl] = useState(d.ul_limit_mbps?.toString() ?? "");
  const [priority, setPriority] = useState<Priority>(d.priority);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    setDl(d.dl_limit_mbps?.toString() ?? "");
    setUl(d.ul_limit_mbps?.toString() ?? "");
    setPriority(d.priority);
  }, [d.dl_limit_mbps, d.ul_limit_mbps, d.priority]);

  const numOrNull = (v: string) => (v.trim() === "" ? null : Number(v));

  const apply = async () => {
    setBusy(true); setMsg(null);
    try {
      await api.setDeviceQos(d.id, numOrNull(dl), numOrNull(ul), priority, true);
      setMsg("applied");
      onChanged();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "failed");
    } finally {
      setBusy(false);
    }
  };

  const togglePause = async () => {
    setBusy(true); setMsg(null);
    try {
      if (d.paused) await api.resumeDevice(d.id); else await api.pauseDevice(d.id);
      onChanged();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "failed");
    } finally {
      setBusy(false);
    }
  };

  const name = d.label ?? d.hostname ?? (d.mac ? d.mac.slice(-5).toUpperCase() : d.id.slice(0, 8));

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Wifi className="h-4 w-4 text-ink-400" />
          <span className="text-ink-200 font-medium">{name}</span>
          <span className="text-xs text-ink-400 font-mono">{d.ip ?? "—"}</span>
          {d.paused && <span className="badge bg-accent-warn/20 text-accent-warn">paused</span>}
        </div>
        <button
          onClick={togglePause}
          disabled={busy || !helperOk}
          className={classNames("btn", d.paused ? "btn-primary" : "btn-ghost")}
          title={d.paused ? "Resume internet" : "Pause internet"}
        >
          {d.paused ? <><Play className="h-3.5 w-3.5" /> Resume</> : <><Pause className="h-3.5 w-3.5" /> Pause</>}
        </button>
      </div>

      <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3 items-end">
        <LabeledInput label="Download limit (Mbps)" value={dl} onChange={setDl} placeholder="unlimited" />
        <LabeledInput label="Upload limit (Mbps)" value={ul} onChange={setUl} placeholder="unlimited" />
        <div>
          <label className="text-xs text-ink-400">Priority</label>
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value as Priority)}
            className="mt-1 w-full rounded-lg bg-ink-800 border border-ink-700 px-2 py-2 text-sm text-ink-200"
          >
            {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <button onClick={apply} disabled={busy || !helperOk} className="btn-primary">
          {busy ? "Applying…" : "Apply"}
        </button>
      </div>

      {msg && (
        <div className={classNames("mt-2 text-xs", msg === "applied" ? "text-accent-up" : "text-accent-down")}>
          {msg === "applied" ? "Rule applied and verified by the helper." : `Error: ${msg}`}
        </div>
      )}
    </div>
  );
}

function LabeledInput({ label, value, onChange, placeholder }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string;
}) {
  return (
    <div>
      <label className="text-xs text-ink-400">{label}</label>
      <input
        type="number"
        step="0.1"
        min="0"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-lg bg-ink-800 border border-ink-700 px-2 py-2 text-sm text-ink-200 placeholder-ink-600"
      />
    </div>
  );
}

function PoliciesPanel() {
  const [policies, setPolicies] = useState<{ name: string; description: string; builtin: boolean }[]>([]);
  const [diff, setDiff] = useState<{ device_id: string; changes?: Record<string, unknown>; removed?: boolean }[] | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = async () => { try { setPolicies((await api.policies()).policies); } catch { /* ignore */ } };
  useEffect(() => { load(); }, []);

  const preview = async (name: string) => {
    try { const r = await api.previewPolicy(name); setDiff(r.diff); setActive(name); } catch (e) { setMsg(e instanceof Error ? e.message : "preview failed"); }
  };
  const apply = async (name: string) => {
    try { await api.applyPolicy(name); setMsg(`Applied "${name}".`); setDiff(null); } catch (e) { setMsg(e instanceof Error ? e.message : "apply failed"); }
  };
  const revert = async () => {
    try { await api.revertPolicy(); setMsg("Reverted to previous configuration."); setDiff(null); } catch (e) { setMsg(e instanceof Error ? e.message : "revert failed"); }
  };

  return (
    <div className="card p-4">
      <h2 className="text-sm font-medium text-ink-200 mb-1">Smart QoS Policies</h2>
      <p className="text-xs text-ink-400 mb-3">Scheduling/ceiling preferences over your configured rules. No app identification is claimed.</p>
      <div className="flex flex-wrap gap-2">
        {policies.map((p) => (
          <div key={p.name} className="rounded-lg border border-ink-700 p-3 w-56">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-ink-200 capitalize">{p.name}</span>
              {p.builtin && <span className="badge bg-ink-800 text-ink-400">builtin</span>}
            </div>
            <p className="text-xs text-ink-400 mt-1 h-12 overflow-hidden">{p.description}</p>
            <div className="mt-2 flex gap-1">
              <button onClick={() => preview(p.name)} className="btn-ghost px-2 py-1 text-xs">Preview</button>
              <button onClick={() => apply(p.name)} className="btn-primary px-2 py-1 text-xs">Apply</button>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-2">
        <button onClick={revert} className="btn-ghost">Revert last policy</button>
        {active && <span className="text-xs text-ink-400">Previewing: <span className="text-ink-200">{active}</span></span>}
      </div>
      {diff !== null && (
        <div className="mt-2 text-xs">
          {diff.length === 0 ? <span className="text-ink-400">No changes.</span> : (
            <ul className="text-ink-200 space-y-0.5">
              {diff.map((d) => (
                <li key={d.device_id}>{d.removed ? `remove ${d.device_id.slice(0, 8)}` : `${d.device_id.slice(0, 8)}: ${JSON.stringify(d.changes)}`}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {msg && <div className="mt-2 text-xs text-accent-up">{msg}</div>}
    </div>
  );
}
