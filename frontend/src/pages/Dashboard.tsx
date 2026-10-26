import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  ArrowDown,
  ArrowUp,
  Cpu,
  Globe,
  HardDrive,
  ListChecks,
  MemoryStick,
  Power,
  PowerOff,
  Wifi,
} from "lucide-react";
import { api } from "../api/client";
import { useMonitor } from "../hooks/useMonitor";
import { classNames, formatBps, formatBytes, formatTime } from "../lib/format";
import StatCard from "../components/StatCard";
import TrafficGraph from "../components/TrafficGraph";
import type { HotspotStatus, SystemInfo } from "../types";

const WINDOWS: { label: string; seconds: number }[] = [
  { label: "30s", seconds: 30 },
  { label: "1m", seconds: 60 },
  { label: "5m", seconds: 300 },
];

export default function Dashboard() {
  const { snapshot, status, stale, history } = useMonitor();
  const [sys, setSys] = useState<SystemInfo | null>(null);
  const [windowSec, setWindowSec] = useState(60);

  useEffect(() => {
    api.systemInfo().then(setSys).catch(() => setSys(null));
  }, []);

  const agg = snapshot?.aggregate;
  const dlBytes = agg?.dl_bytes ?? 0;
  const ulBytes = agg?.ul_bytes ?? 0;
  const devices = snapshot?.hotspot.connected_count ?? 0;
  const internet = snapshot?.upstream.internet ?? "unknown";
  const latency = snapshot?.upstream.latency_ms ?? null;

  // Trim the rolling history to the selected window (points are ~1s apart).
  const graphData = useMemo(
    () => history.slice(-windowSec),
    [history, windowSec]
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-ink-200">Dashboard</h1>
        <p className="text-sm text-ink-400 mt-1">
          {sys?.hostname ?? "—"} · {sys?.os ?? "—"} · kernel {sys?.kernel ?? "—"}
        </p>
      </div>

      <HotspotToggle snapshot={snapshot} />

      {stale && status === "open" && (
        <div className="card p-3 border-accent-down/40 text-sm text-accent-down">
          Live data looks stale (no update in &gt;5s).
        </div>
      )}

      {snapshot?.warnings?.length ? (
        <ul className="card p-3 space-y-1 text-xs text-accent-down/90">
          {snapshot.warnings.map((w, i) => (
            <li key={i}>• {w}</li>
          ))}
        </ul>
      ) : null}

      {/* Main statistics cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <StatCard
          label="Total Download"
          value={formatBps(agg?.dl_bps ?? null)}
          sub={<>Total {formatBytes(dlBytes)}</>}
          tone="down"
          icon={<ArrowDown className="h-4 w-4" />}
        />
        <StatCard
          label="Total Upload"
          value={formatBps(agg?.ul_bps ?? null)}
          sub={<>Total {formatBytes(ulBytes)}</>}
          tone="up"
          icon={<ArrowUp className="h-4 w-4" />}
        />
        <StatCard
          label="Connected Devices"
          value={devices}
          sub="hotspot clients"
          icon={<ListChecks className="h-4 w-4" />}
        />
        <StatCard
          label="Downloaded Data"
          value={formatBytes(dlBytes || null)}
          sub="since session start"
          tone="down"
          icon={<HardDrive className="h-4 w-4" />}
        />
        <StatCard
          label="Uploaded Data"
          value={formatBytes(ulBytes || null)}
          sub="since session start"
          tone="up"
          icon={<HardDrive className="h-4 w-4" />}
        />
        <StatCard
          label="Internet"
          value={<span className="capitalize">{internet}</span>}
          sub={latency != null ? `${latency} ms latency` : "latency unavailable"}
          tone={internet === "ok" ? "up" : internet === "none" ? "warn" : "default"}
          icon={<Globe className="h-4 w-4" />}
        />
      </div>

      {/* Live traffic graph */}
      <div className="card p-4">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h2 className="text-sm font-medium text-ink-200">Live Traffic</h2>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-3 text-xs">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-accent-down" /> Download
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-accent-up" /> Upload
              </span>
            </div>
            <div className="flex rounded-lg bg-ink-800 p-0.5">
              {WINDOWS.map((w) => (
                <button
                  key={w.label}
                  onClick={() => setWindowSec(w.seconds)}
                  className={classNames(
                    "px-2.5 py-1 text-xs rounded-md transition-colors",
                    windowSec === w.seconds
                      ? "bg-ink-700 text-white"
                      : "text-ink-400 hover:text-ink-200"
                  )}
                >
                  {w.label}
                </button>
              ))}
            </div>
          </div>
        </div>
        <TrafficGraph data={graphData} />
        <p className="mt-2 text-xs text-ink-400">
          Real throughput on the upstream interface ({snapshot?.hotspot.upstream_interface ?? "—"}),
          measured from /proc/net/dev. Source:{" "}
          <span className="text-ink-200">{status}</span> · last update{" "}
          {formatTime(snapshot?.ts ?? null)}.
        </p>
      </div>

      {/* Hotspot status panel */}
      <div className="card p-4">
        <h2 className="text-sm font-medium text-ink-200 mb-3">Hotspot Status</h2>
        <dl className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-3 text-sm">
          <Field label="State" value={snapshot?.hotspot.state ?? "—"} />
          <Field label="SSID" value={snapshot?.hotspot.ssid ?? "—"} />
          <Field
            label="Hotspot Interface"
            value={snapshot?.hotspot.hotspot_interface ?? "—"}
          />
          <Field
            label="Upstream Interface"
            value={snapshot?.hotspot.upstream_interface ?? "—"}
          />
          <Field label="Gateway IP" value={snapshot?.hotspot.gateway_ip ?? "—"} />
          <Field label="Channel" value={snapshot?.hotspot.channel != null ? String(snapshot.hotspot.channel) : "—"} />
        </dl>
      </div>

      {/* System health */}
      <div className="card p-4">
        <h2 className="text-sm font-medium text-ink-200 mb-3">System</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <SysInfo icon={<Cpu className="h-4 w-4" />} label="CPU" value={sys?.cpu_model ?? "—"} sub={`${sys?.cpu_count ?? 0} cores`} />
          <SysInfo icon={<MemoryStick className="h-4 w-4" />} label="Memory" value={`${sys?.mem_total_mb ?? 0} MB`} />
          <SysInfo icon={<Activity className="h-4 w-4" />} label="NetworkManager" value={sys?.nm_version ?? "—"} />
          <SysInfo icon={<HardDrive className="h-4 w-4" />} label="Last update" value={formatTime(snapshot?.ts ?? null)} />
        </div>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-400">{label}</dt>
      <dd className="text-ink-200 font-medium">{value}</dd>
    </div>
  );
}

function SysInfo({
  icon,
  label,
  value,
  sub,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="flex items-start gap-2">
      <span className="text-ink-400 mt-0.5">{icon}</span>
      <div>
        <div className="text-xs text-ink-400">{label}</div>
        <div className="text-ink-200 truncate">{value}</div>
        {sub && <div className="text-xs text-ink-400">{sub}</div>}
      </div>
    </div>
  );
}

function HotspotToggle({ snapshot }: { snapshot: import("../types").MonitorSnapshot | null }) {
  const nav = useNavigate();
  const [status, setStatus] = useState<HotspotStatus | null>(null);
  const [helper, setHelper] = useState<string>("unknown");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const running = (status?.state ?? snapshot?.hotspot.state) === "started";
  const ssid = status?.ssid ?? snapshot?.hotspot.ssid;
  const hsIface = status?.hotspot_interface ?? snapshot?.hotspot.hotspot_interface;
  const upIface = status?.upstream_interface ?? snapshot?.hotspot.upstream_interface;

  const refresh = async () => {
    try {
      const [s, h] = await Promise.all([api.hotspotStatus(), api.health()]);
      setStatus(s); setHelper(h.helper);
    } catch { /* ignore */ }
  };
  useEffect(() => {
    refresh();
    const t = window.setInterval(refresh, 3000);
    return () => window.clearInterval(t);
  }, []);

  const stop = async () => {
    if (!window.confirm("Stop the hotspot? Connected clients will lose internet.")) return;
    setBusy(true); setMsg(null);
    try { await api.stopHotspot(); setMsg("Hotspot stopping…"); refresh(); }
    catch (e) { setMsg(e instanceof Error ? e.message : "stop failed"); }
    finally { setBusy(false); }
  };

  const start = async () => {
    const ok = await ensureFreshHelper();
    if (!ok) { setBusy(false); return; }
    if (!ssid || !hsIface || !upIface) { setBusy(false); nav("/hotspot"); return; }
    const password = window.prompt(
      `Start hotspot "${ssid}" on ${hsIface} (upstream ${upIface})?\nEnter the WPA2 password (min 8 chars):`, ""
    );
    if (password === null) { setBusy(false); return; }
    if (password.length < 8) { setMsg("Password must be at least 8 characters."); setBusy(false); return; }
    try {
      const res = await api.startHotspot({ ssid: ssid!, password, hotspot_interface: hsIface!, upstream_interface: upIface! });
      setMsg(res.warnings?.length ? `Starting… ${res.warnings.join(" ")}` : "Hotspot starting…");
      refresh();
    } catch (e) { setMsg(e instanceof Error ? e.message : "start failed"); }
    finally { setBusy(false); }
  };

  const waitForHelper = async (timeoutS: number) => {
    const deadline = Date.now() + timeoutS * 1000;
    while (Date.now() < deadline) {
      try { const h = await api.health(); if (h.helper === "reachable") return true; } catch { /* keep polling */ }
      await new Promise((r) => setTimeout(r, 1000));
    }
    return false;
  };

  // Auto-restart the helper (re-exec with latest code) if it's reachable but stale.
  const ensureFreshHelper = async (): Promise<boolean> => {
    if (helper !== "reachable") {
      // Not running — open terminal for the user to type sudo password.
      setBusy(true);
      try {
        const g = await api.grantHotspot();
        if (!g.already) {
          setMsg("Terminal opened — type your sudo password. Waiting for helper…");
          const up = await waitForHelper(40);
          if (!up) {
            setMsg("Helper didn't start. Try: sudo pkill -f helper.py && sudo python3 -B privileged-helper/helper.py --user aman");
            return false;
          }
        }
        setHelper("reachable");
        return true;
      } catch (e) {
        setMsg(e instanceof Error ? e.message : "could not start helper");
        return false;
      } finally {
        setBusy(false);
      }
    }
    // Helper is reachable — send it a restart (re-exec with latest code on disk).
    try {
      setMsg("Restarting helper with latest code…");
      await api.restartHelper();
      setMsg(null);
      return true;
    } catch {
      // restart failed or timed out — helper may still work, continue anyway
      setMsg(null);
      return true;
    }
  };

  return (
    <div className="card p-3 flex flex-col gap-2">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2 text-sm">
          <Wifi className={classNames("h-4 w-4", running ? "text-accent-up" : "text-ink-400")} />
          <span className="text-ink-200 font-medium">Hotspot</span>
          <span className={classNames(
            "badge uppercase text-[10px]",
            running ? "bg-accent-up/20 text-accent-up" : "bg-ink-800 text-ink-400"
          )}>
            {status?.state ?? snapshot?.hotspot.state ?? "—"}
          </span>
          {ssid && <span className="text-xs text-ink-400 font-mono">{ssid}</span>}
          {running && (
            <span className="text-xs text-ink-400">
              · {status?.connected_count ?? snapshot?.hotspot.connected_count ?? 0} clients
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {running ? (
            <button onClick={stop} disabled={busy} className="btn-ghost">
              <PowerOff className="h-4 w-4" /> {busy ? "Stopping…" : "Stop Hotspot"}
            </button>
          ) : (
            <button
              onClick={start}
              disabled={busy}
              className="btn-primary"
            >
              <Power className="h-4 w-4" />
              {busy
                ? "Please wait…"
                : helper !== "reachable"
                  ? "Grant Permission & Start"
                  : ssid && hsIface && upIface
                    ? "Start Hotspot"
                    : "Configure Hotspot"}
            </button>
          )}
        </div>
      </div>

      {/* Status / instruction line */}
      {msg ? (
        <p className="text-xs text-accent-warn">{msg}</p>
      ) : !running && helper !== "reachable" ? (
        <p className="text-xs text-ink-400">
          Click <span className="text-ink-200 font-medium">Grant Permission &amp; Start</span> — a terminal
          will open asking for your <code className="text-ink-200">sudo</code> password to start the
          privileged helper. The dashboard continues automatically once it's up.
        </p>
      ) : null}
    </div>
  );
}
