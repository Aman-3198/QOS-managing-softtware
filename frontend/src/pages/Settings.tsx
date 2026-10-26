import { useEffect, useState } from "react";
import { Lock, LogOut, Save } from "lucide-react";
import { api } from "../api/client";

export default function Settings() {
  const [s, setS] = useState<Record<string, string>>({});
  const [auth, setAuth] = useState<{ authenticated: boolean; has_password: boolean }>({ authenticated: false, has_password: false });
  const [pw, setPw] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const [settings, me] = await Promise.all([api.settings(), api.authMe()]);
      setS(settings); setAuth(me);
    } catch { /* ignore */ }
  };
  useEffect(() => { refresh(); }, []);

  const save = async (k: string, v: string) => {
    try { const updated = await api.patchSettings({ [k]: v }); setS(updated); setMsg("Saved."); }
    catch (e) { setMsg(e instanceof Error ? e.message : "failed"); }
  };
  const setPassword = async () => {
    try { await api.setPassword(pw); setPw(""); setMsg("Password set. Auth now enabled."); refresh(); }
    catch (e) { setMsg(e instanceof Error ? e.message : "failed"); }
  };
  const logout = async () => { await api.logout(); setMsg("Logged out."); refresh(); };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-ink-200">Application Settings</h1>

      <div className="card p-4 space-y-3">
        <h2 className="text-sm font-medium text-ink-200">Display & history</h2>
        <Row label="Speed unit"><select className="sqm-input" value={s.speed_unit || "Mbps"} onChange={(e) => save("speed_unit", e.target.value)}><option>Mbps</option><option>Kbps</option></select></Row>
        <Row label="History retention (days)"><input type="number" className="sqm-input" value={s.history_retention_days || "30"} onChange={(e) => save("history_retention_days", e.target.value)} /></Row>
        <Row label="Dashboard bind (restart required)"><select className="sqm-input" value={s.dashboard_bind || "127.0.0.1"} onChange={(e) => save("dashboard_bind", e.target.value)}><option value="127.0.0.1">127.0.0.1 (local only)</option><option value="0.0.0.0">0.0.0.0 (all — needs auth)</option></select></Row>
        {msg && <div className="text-xs text-accent-up">{msg}</div>}
      </div>

      <div className="card p-4 space-y-3">
        <h2 className="text-sm font-medium text-ink-200 flex items-center gap-2"><Lock className="h-4 w-4" /> Security</h2>
        <p className="text-xs text-ink-400">
          Auth is {auth.has_password ? <span className="text-accent-up">enabled</span> : <span className="text-accent-warn">disabled (dev open)</span>}.
          {auth.has_password ? "" : " Set a password to require login. Until then the dashboard is open on localhost."}
        </p>
        {!auth.has_password ? (
          <Row label="Set dashboard password (min 8)">
            <div className="flex gap-2">
              <input type="password" className="sqm-input" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="new password" />
              <button onClick={setPassword} disabled={pw.length < 8} className="btn-primary"><Save className="h-4 w-4" /> Set</button>
            </div>
          </Row>
        ) : auth.authenticated ? (
          <button onClick={logout} className="btn-ghost"><LogOut className="h-4 w-4" /> Log out</button>
        ) : (
          <p className="text-xs text-ink-400">A password is set. Log in to manage settings.</p>
        )}
      </div>

      <div className="card p-4 text-xs text-ink-400">
        <p className="font-medium text-ink-200 mb-1">Privileged helper</p>
        To enable hotspot + shaping: <code className="text-ink-200">sudo bash privileged-helper/setup.sh</code> then <code className="text-ink-200">sudo python3 privileged-helper/helper.py</code>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="grid grid-cols-1 md:grid-cols-3 gap-2 items-center"><div className="text-sm text-ink-200 md:col-span-1">{label}</div><div className="md:col-span-2">{children}</div></div>;
}
