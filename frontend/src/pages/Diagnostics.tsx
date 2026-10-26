import { useEffect, useState } from "react";
import { CheckCircle2, Download, AlertTriangle, HelpCircle, XCircle } from "lucide-react";
import { api } from "../api/client";
import { classNames } from "../lib/format";

type Check = { id: string; name: string; status: string; detail: string; suggestion: string };

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  pass: CheckCircle2, warning: AlertTriangle, fail: XCircle, unknown: HelpCircle,
};
const COLORS: Record<string, string> = {
  pass: "text-accent-up", warning: "text-accent-warn", fail: "text-accent-down", unknown: "text-ink-400",
};

export default function Diagnostics() {
  const [checks, setChecks] = useState<Check[]>([]);
  const [loading, setLoading] = useState(true);

  const run = async () => {
    try { setChecks((await api.diagnostics()).checks); } finally { setLoading(false); }
  };
  useEffect(() => { run(); }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink-200">Network Diagnostics</h1>
        <div className="flex gap-2">
          <button onClick={run} className="btn-ghost">Re-run</button>
          <a href="/api/diagnostics/export" className="btn-ghost"><Download className="h-4 w-4" /> Export</a>
        </div>
      </div>
      {loading ? (
        <div className="card p-8 text-center text-sm text-ink-400">Running checks…</div>
      ) : (
        <div className="space-y-2">
          {checks.map((c) => {
            const Icon = ICONS[c.status] || HelpCircle;
            return (
              <div key={c.id} className="card p-3 flex items-start gap-3">
                <Icon className={classNames("h-5 w-5 mt-0.5 shrink-0", COLORS[c.status] || "text-ink-400")} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-ink-200">{c.name}</span>
                    <span className={classNames("badge uppercase text-[10px]", c.status === "pass" ? "bg-accent-up/20 text-accent-up" : c.status === "warning" ? "bg-accent-warn/20 text-accent-warn" : c.status === "fail" ? "bg-accent-down/20 text-accent-down" : "bg-ink-800 text-ink-400")}>{c.status}</span>
                  </div>
                  <div className="text-xs text-ink-400 mt-0.5">{c.detail}</div>
                  {c.suggestion && <div className="text-xs text-ink-200 mt-1">→ {c.suggestion}</div>}
                </div>
              </div>
            );
          })}
        </div>
      )}
      <p className="text-xs text-ink-400">Privileged checks (nft ruleset) report “unknown” when run unprivileged; the helper can read them. Exports omit all secrets.</p>
    </div>
  );
}
