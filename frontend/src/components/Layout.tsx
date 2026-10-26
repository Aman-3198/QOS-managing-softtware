import { NavLink, Outlet } from "react-router-dom";
import {
  Activity,
  Gauge,
  HardDrive,
  ListChecks,
  Network,
  Settings,
  Stethoscope,
  Wifi,
  WifiOff,
} from "lucide-react";
import { classNames } from "../lib/format";
import type { MonitorSnapshot, WsStatus } from "../types";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: Gauge },
  { to: "/devices", label: "Connected Devices", icon: ListChecks },
  { to: "/rules", label: "Bandwidth Rules", icon: HardDrive },
  { to: "/analytics", label: "Traffic Analytics", icon: Activity },
  { to: "/hotspot", label: "Hotspot Settings", icon: Network },
  { to: "/diagnostics", label: "Network Diagnostics", icon: Stethoscope },
  { to: "/settings", label: "Application Settings", icon: Settings },
];

interface LayoutProps {
  snapshot: MonitorSnapshot | null;
  wsStatus: WsStatus;
}

export default function Layout({ snapshot, wsStatus }: LayoutProps) {
  const hotspotOn = snapshot?.hotspot.state === "started";
  const internet = snapshot?.upstream.internet ?? "unknown";

  return (
    <div className="min-h-full flex">
      {/* Sidebar (desktop) */}
      <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-ink-700 bg-ink-900">
        <div className="flex items-center gap-2 px-5 py-5 border-b border-ink-700">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-accent text-white font-bold">
            Q
          </div>
          <div>
            <div className="text-sm font-semibold text-ink-200">Smart QoS</div>
            <div className="text-xs text-ink-400">Manager</div>
          </div>
        </div>
        <nav className="flex-1 px-2 py-3 space-y-0.5">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                classNames(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-ink-800 text-white"
                    : "text-ink-400 hover:text-ink-200 hover:bg-ink-800/50"
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="px-4 py-3 border-t border-ink-700 text-xs text-ink-400">
          v0.1.0 · Phase 2
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="sticky top-0 z-10 border-b border-ink-700 bg-ink-900/80 backdrop-blur px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 text-sm">
              <StatusDot on={hotspotOn} label={hotspotOn ? "Hotspot on" : "Hotspot off"} />
              <StatusDot
                on={internet === "ok"}
                warn={internet === "limited" || internet === "unknown"}
                label={`Internet: ${internet}`}
              />
              <StatusDot
                on={wsStatus === "open"}
                warn={wsStatus === "connecting"}
                label={`WS: ${wsStatus}`}
              />
            </div>
            <div className="text-xs text-ink-400">
              {snapshot?.hotspot.connected_count ?? 0} devices
            </div>
          </div>
        </header>

        {/* Mobile nav */}
        <nav className="md:hidden flex overflow-x-auto gap-1 px-2 py-2 border-b border-ink-700 bg-ink-900">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                classNames(
                  "flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-xs",
                  isActive ? "bg-ink-800 text-white" : "text-ink-400 hover:bg-ink-800/50"
                )
              }
            >
              <item.icon className="h-3.5 w-3.5" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <main className="flex-1 overflow-y-auto p-4 md:p-6 max-w-7xl w-full mx-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function StatusDot({
  on,
  warn,
  label,
}: {
  on: boolean;
  warn?: boolean;
  label: string;
}) {
  const color = on ? "bg-accent-up" : warn ? "bg-accent-down" : "bg-ink-600";
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={classNames("h-2 w-2 rounded-full", color)} />
      {label}
    </span>
  );
}

export { Wifi, WifiOff };
