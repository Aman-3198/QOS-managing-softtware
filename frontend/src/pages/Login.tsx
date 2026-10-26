import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Lock } from "lucide-react";
import { api } from "../api/client";

export default function Login() {
  const [pw, setPw] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const nav = useNavigate();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    try { await api.login(pw); nav("/"); } catch (e2) { setErr(e2 instanceof Error ? e2.message : "login failed"); }
  };

  return (
    <div className="min-h-full grid place-items-center p-4">
      <form onSubmit={submit} className="card p-6 w-full max-w-sm space-y-4">
        <div className="flex items-center gap-2">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-accent text-white font-bold">Q</div>
          <div><div className="text-sm font-semibold text-ink-200">Smart QoS Manager</div><div className="text-xs text-ink-400">Sign in</div></div>
        </div>
        <div>
          <label className="text-xs text-ink-400">Password</label>
          <div className="relative mt-1">
            <Lock className="h-4 w-4 text-ink-400 absolute left-3 top-3" />
            <input type="password" autoFocus className="sqm-input pl-9" value={pw} onChange={(e) => setPw(e.target.value)} />
          </div>
        </div>
        {err && <div className="text-xs text-accent-down">{err}</div>}
        <button type="submit" className="btn-primary w-full" disabled={pw.length < 1}>Sign in</button>
      </form>
    </div>
  );
}
