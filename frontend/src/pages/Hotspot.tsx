import { useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  Eye,
  EyeOff,
  Power,
  PowerOff,
  ShieldAlert,
  Wifi,
} from "lucide-react";
import { api } from "../api/client";
import { classNames } from "../lib/format";
import type { HotspotStatus, InterfaceInfo } from "../types";

// ---------------------------------------------------------------------------
// QR code generator — pure JS, no library needed.
// Encodes a Wi-Fi QR string using a lightweight QR rendering via a canvas.
// We use the Google Charts API (public, free) because we have internet.
// ---------------------------------------------------------------------------
function WifiQR({ ssid, password, security = "WPA" }: { ssid: string; password: string; security?: string }) {
  const data = `WIFI:T:${security};S:${encodeURIComponent(ssid)};P:${encodeURIComponent(password)};;`;
  const url  = `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(data)}&bgcolor=1f2937&color=e5e7eb&margin=2`;
  return (
    <div className="flex flex-col items-center gap-2">
      <img
        src={url}
        alt="Wi-Fi QR code"
        width={180}
        height={180}
        className="rounded-lg border border-ink-700"
        onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
      />
      <p className="text-xs text-ink-400">Scan to join</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function Hotspot() {
  const [status, setStatus]   = useState<HotspotStatus | null>(null);
  const [ifs, setIfs]         = useState<InterfaceInfo[]>([]);
  const [helper, setHelper]   = useState<string>("unknown");
  const [busy, setBusy]       = useState(false);
  const [msg, setMsg]         = useState<string | null>(null);
  const [msgType, setMsgType] = useState<"error" | "warn" | "ok">("error");
  const [showPw, setShowPw]   = useState(false);

  // Remember the password in session only (never persisted).
  const sessionPw = useRef<string>("");

  const [form, setForm] = useState({
    ssid: "SmartQoS",
    password: "",
    hotspot_interface: "",
    upstream_interface: "",
    band: "bg",
    channel: "",
  });

  const refresh = async () => {
    try {
      const [s, i, h] = await Promise.all([
        api.hotspotStatus(), api.interfaces(), api.health(),
      ]);
      setStatus(s);
      setIfs(i.interfaces);
      setHelper(h.helper);
      setForm((f) => {
        // Auto-pick the best interfaces:
        // hotspot  = first AP-capable wifi
        // upstream = prefer ethernet (non-wifi), else any other upstream candidate
        const apIf = i.interfaces.find((x) => x.hotspot_candidate);
        const ethIf = i.interfaces.find(
          (x) => x.upstream_candidate && x.type === "ethernet" && x.link
        );
        const anyUp = i.interfaces.find(
          (x) => x.upstream_candidate && x.name !== apIf?.name
        );
        return {
          ...f,
          hotspot_interface: f.hotspot_interface || apIf?.name || "",
          upstream_interface:
            f.upstream_interface ||
            ethIf?.name ||
            anyUp?.name ||
            s.upstream_interface ||
            "",
        };
      });
    } catch { /* ignore */ }
  };

  useEffect(() => {
    refresh();
    const t = window.setInterval(refresh, 3000);
    return () => window.clearInterval(t);
  }, []);

  const apIfaces = ifs.filter((i) => i.hotspot_candidate);
  const upIfaces = ifs.filter((i) => i.upstream_candidate);
  const chosenAp = ifs.find((i) => i.name === form.hotspot_interface);

  const err = (m: string) => { setMsg(m); setMsgType("error"); };
  const ok  = (m: string) => { setMsg(m); setMsgType("ok"); };
  const warn = (m: string) => { setMsg(m); setMsgType("warn"); };

  const start = async () => {
    if (!form.ssid.trim())              { err("SSID is required."); return; }
    if (!form.password)                 { err("Password is required (min 8 characters)."); return; }
    if (form.password.length < 8)       { err("Password must be at least 8 characters."); return; }
    if (!form.hotspot_interface)        { err("Select a hotspot interface."); return; }
    if (!form.upstream_interface)       { err("Select an upstream interface."); return; }

    setBusy(true); setMsg(null);
    try {
      sessionPw.current = form.password;          // keep in memory for QR display
      const res = await api.startHotspot({
        ssid: form.ssid.trim(),
        password: form.password,
        hotspot_interface: form.hotspot_interface,
        upstream_interface: form.upstream_interface,
        band: form.band || undefined,
        channel: form.channel ? Number(form.channel) : null,
      });
      if (res.warnings?.length) {
        warn(`Started with warnings: ${res.warnings.join(" ")}`);
      } else {
        ok("Hotspot started!");
      }
      refresh();
    } catch (e) {
      err(e instanceof Error ? e.message : "start failed");
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    if (!window.confirm("Stop the hotspot? Connected clients will lose internet.")) return;
    setBusy(true); setMsg(null);
    try {
      await api.stopHotspot();
      ok("Hotspot stopped.");
      refresh();
    } catch (e) {
      err(e instanceof Error ? e.message : "stop failed");
    } finally {
      setBusy(false);
    }
  };

  const running = status?.state === "started";
  const displaySsid = status?.ssid || form.ssid;
  const displayPw   = sessionPw.current;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-ink-200">Hotspot Settings</h1>

      {/* Helper status */}
      {helper !== "reachable" && (
        <div className="card p-3 text-sm text-accent-warn border-accent-warn/40 flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 shrink-0" />
          Privileged helper not running. Go to Dashboard → click{" "}
          <strong className="text-ink-200">Grant Permission &amp; Start</strong> first.
        </div>
      )}

      {/* Current status card */}
      <div className="card p-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Wifi className={classNames("h-4 w-4", running ? "text-accent-up" : "text-ink-400")} />
            <span className="text-sm font-medium text-ink-200">Status</span>
            <span className={classNames(
              "badge uppercase text-[10px]",
              running ? "bg-accent-up/20 text-accent-up" : "bg-ink-800 text-ink-400"
            )}>
              {status?.state ?? "—"}
            </span>
          </div>
          {running && (
            <button onClick={stop} disabled={busy} className="btn-ghost">
              <PowerOff className="h-4 w-4" /> {busy ? "Stopping…" : "Stop Hotspot"}
            </button>
          )}
        </div>

        {running && (
          <dl className="mt-3 grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-2 text-sm">
            <F label="SSID"       value={status?.ssid ?? "—"} />
            <F label="Hotspot if" value={status?.hotspot_interface ?? "—"} />
            <F label="Upstream"   value={status?.upstream_interface ?? "—"} />
            <F label="Gateway IP" value={status?.gateway_ip ?? "—"} />
            <F label="Channel"    value={status?.channel != null ? String(status.channel) : "—"} />
            <F label="Clients"    value={`${status?.connected_count ?? 0}`} />
          </dl>
        )}
      </div>

      {/* QR code + password — shown when running and we remember the password */}
      {running && displayPw && (
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-3">
            <CheckCircle2 className="h-4 w-4 text-accent-up" />
            <h2 className="text-sm font-medium text-ink-200">Connect to <span className="text-accent">{displaySsid}</span></h2>
          </div>
          <div className="flex flex-col md:flex-row gap-6 items-center">
            <WifiQR ssid={displaySsid} password={displayPw} />
            <div className="space-y-3 flex-1">
              <div>
                <div className="text-xs text-ink-400 mb-1">Network name (SSID)</div>
                <div className="card px-3 py-2 text-ink-200 font-mono text-sm">{displaySsid}</div>
              </div>
              <div>
                <div className="text-xs text-ink-400 mb-1">Password</div>
                <div className="flex items-center gap-2">
                  <div className="card flex-1 px-3 py-2 font-mono text-sm text-ink-200">
                    {showPw ? displayPw : "•".repeat(displayPw.length)}
                  </div>
                  <button
                    onClick={() => setShowPw((v) => !v)}
                    className="btn-ghost px-2 py-2"
                    title={showPw ? "Hide password" : "Show password"}
                  >
                    {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>
              <p className="text-xs text-ink-400">
                Scan the QR code with your phone camera to join instantly.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Configure form — shown when not running */}
      {!running && (
        <div className="card p-4 space-y-4">
          <h2 className="text-sm font-medium text-ink-200">Configure &amp; start</h2>

          {/* Step guide */}
          <ol className="text-xs text-ink-400 space-y-1 list-decimal list-inside">
            <li>Choose a name (SSID) for your hotspot network.</li>
            <li><span className="text-ink-200 font-medium">Create a Wi-Fi password</span> — phones will use this to join. Min 8 characters, you choose it.</li>
            <li>Confirm the interfaces are correct (auto-filled below).</li>
            <li>Click <span className="text-ink-200 font-medium">Start Hotspot</span>.</li>
          </ol>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

            {/* SSID */}
            <L label="① Network name (SSID) — visible to phones">
              <input
                className="sqm-input"
                value={form.ssid}
                onChange={(e) => setForm({ ...form, ssid: e.target.value })}
                placeholder="e.g. SmartQoS"
              />
            </L>

            {/* Password — most important field, styled prominently */}
            <L label="② Wi-Fi password — you create this now (min 8 chars)">
              <div className="flex gap-2">
                <input
                  type={showPw ? "text" : "password"}
                  className={classNames(
                    "sqm-input flex-1 text-base",
                    form.password.length === 0
                      ? "border-accent-warn/60 focus:border-accent-warn"
                      : form.password.length < 8
                        ? "border-accent-warn/60"
                        : "border-accent-up/50"
                  )}
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  placeholder="Type any password, e.g. myhotspot123"
                  autoComplete="new-password"
                />
                <button type="button" onClick={() => setShowPw((v) => !v)} className="btn-ghost px-2">
                  {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              <p className={classNames(
                "text-xs mt-1",
                form.password.length === 0 ? "text-accent-warn" :
                form.password.length < 8   ? "text-accent-warn" : "text-accent-up"
              )}>
                {form.password.length === 0
                  ? "⚠ Enter a password — this is NOT your system password, make up a new one."
                  : form.password.length < 8
                    ? `⚠ ${8 - form.password.length} more character(s) needed.`
                    : `✓ Password OK (${form.password.length} chars)`}
              </p>
            </L>

            {/* Hotspot interface */}
            <L label="③ Hotspot interface (your Wi-Fi card, for the hotspot)">
              <select
                className="sqm-input"
                value={form.hotspot_interface}
                onChange={(e) => setForm({ ...form, hotspot_interface: e.target.value })}
              >
                <option value="">— select —</option>
                {apIfaces.map((i) => (
                  <option key={i.name} value={i.name}>
                    {i.name}{i.wifi?.current_mode === "managed" ? " (currently on Wi-Fi)" : " (AP-capable)"}
                  </option>
                ))}
              </select>
            </L>

            {/* Upstream interface */}
            <L label="④ Upstream interface (your internet source)">
              <select
                className="sqm-input"
                value={form.upstream_interface}
                onChange={(e) => setForm({ ...form, upstream_interface: e.target.value })}
              >
                <option value="">— select —</option>
                {upIfaces.map((i) => (
                  <option key={i.name} value={i.name}>
                    {i.name} ({i.type}){i.is_default_route ? " ← internet" : ""}
                    {i.type === "ethernet" && i.link ? " (cable connected ✓)" : ""}
                  </option>
                ))}
              </select>
              <p className="text-xs text-ink-400 mt-1">
                {form.upstream_interface
                  ? ifs.find(x => x.name === form.upstream_interface)?.type === "ethernet"
                    ? "✓ Ethernet — best choice for a stable hotspot."
                    : "Using Wi-Fi as upstream. Ethernet is more stable."
                  : "Select where your internet comes from."}
              </p>
            </L>
          </div>

          {/* Preview QR before starting */}
          {form.ssid && form.password.length >= 8 && (
            <div className="border border-ink-700 rounded-xl p-4 bg-ink-800/40">
              <p className="text-xs text-ink-400 mb-3">Preview — this QR will let phones join once started:</p>
              <div className="flex flex-col sm:flex-row items-center gap-4">
                <WifiQR ssid={form.ssid} password={form.password} />
                <div className="text-sm space-y-1">
                  <div><span className="text-ink-400">SSID:</span> <span className="text-ink-200 font-medium">{form.ssid}</span></div>
                  <div><span className="text-ink-400">Password:</span> <span className="text-ink-200 font-mono">{showPw ? form.password : "•".repeat(form.password.length)}</span></div>
                </div>
              </div>
            </div>
          )}

          {/* Same-adapter warning */}
          {chosenAp?.wifi?.current_mode === "managed" &&
           form.upstream_interface === form.hotspot_interface && (
            <div className="text-xs text-accent-warn bg-accent-warn/10 rounded-lg p-3">
              ⚠ <strong>{form.hotspot_interface}</strong> is currently your internet Wi-Fi.
              Starting a hotspot on it will disconnect your Wi-Fi.
              Change upstream to <strong>eno1 (Ethernet)</strong> if a cable is plugged in.
            </div>
          )}

          {/* Error / status message */}
          {msg && (
            <div className={classNames(
              "text-sm rounded-lg p-3",
              msgType === "error" ? "bg-accent-down/10 text-accent-down" :
              msgType === "warn"  ? "bg-accent-warn/10 text-accent-warn" :
                                    "bg-accent-up/10 text-accent-up"
            )}>
              {msg}
            </div>
          )}

          <button
            onClick={start}
            disabled={busy || helper !== "reachable"}
            className="btn-primary px-8"
          >
            <Power className="h-4 w-4" />
            {busy ? "Starting…" : "Start Hotspot"}
          </button>

          {helper !== "reachable" && (
            <p className="text-xs text-ink-400">
              Helper not running → go to Dashboard → click{" "}
              <strong className="text-ink-200">Grant Permission &amp; Start</strong>.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function F({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-400">{label}</dt>
      <dd className="text-ink-200 font-medium">{value}</dd>
    </div>
  );
}

function L({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs text-ink-400 block mb-1">{label}</label>
      {children}
    </div>
  );
}
