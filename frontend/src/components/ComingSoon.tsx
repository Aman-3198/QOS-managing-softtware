import type { ReactNode } from "react";

interface ComingSoonProps {
  title: string;
  phase: string;
  description: string;
  icon?: ReactNode;
}

export default function ComingSoon({ title, phase, description, icon }: ComingSoonProps) {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-ink-200">{title}</h1>
      <div className="card p-8 text-center">
        <div className="mx-auto mb-3 text-ink-400">{icon}</div>
        <div className="badge bg-ink-800 text-ink-200 mb-3">{phase}</div>
        <p className="text-sm text-ink-400 max-w-md mx-auto">{description}</p>
      </div>
    </div>
  );
}
