import type { ReactNode } from "react";
import { classNames } from "../lib/format";

interface StatCardProps {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon?: ReactNode;
  tone?: "default" | "up" | "down" | "warn";
}

export default function StatCard({
  label,
  value,
  sub,
  icon,
  tone = "default",
}: StatCardProps) {
  const accent =
    tone === "up"
      ? "text-accent-up"
      : tone === "down"
        ? "text-accent-down"
        : tone === "warn"
          ? "text-accent-warn"
          : "text-ink-200";
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-wide text-ink-400">{label}</span>
        {icon && <span className="text-ink-400">{icon}</span>}
      </div>
      <div className={classNames("mt-2 text-2xl font-semibold tabular-nums", accent)}>
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-ink-400">{sub}</div>}
    </div>
  );
}
