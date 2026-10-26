import { useEffect, useRef, useState } from "react";
import { openMonitor } from "../api/ws";
import type { MonitorSnapshot, WsStatus } from "../types";

export interface TrafficPoint {
  t: number; // epoch ms
  dl: number | null; // bps (download) — null = unavailable, never faked
  ul: number | null; // bps (upload)
}

export interface MonitorState {
  snapshot: MonitorSnapshot | null;
  status: WsStatus;
  stale: boolean;
  history: TrafficPoint[];
}

const STALE_MS = 5000;
const MAX_POINTS = 600; // ~10 min at 1 Hz; longer windows read from DB in Phase 8

export function useMonitor(): MonitorState {
  const [snapshot, setSnapshot] = useState<MonitorSnapshot | null>(null);
  const [status, setStatus] = useState<WsStatus>("connecting");
  const [stale, setStale] = useState(false);
  const [history, setHistory] = useState<TrafficPoint[]>([]);
  const lastTs = useRef<number>(0);

  useEffect(() => {
    const conn = openMonitor((s) => {
      setSnapshot(s);
      setHistory((prev) => {
        const point: TrafficPoint = {
          t: new Date(s.ts).getTime(),
          dl: s.aggregate.dl_bps,
          ul: s.aggregate.ul_bps,
        };
        const next = [...prev, point];
        return next.length > MAX_POINTS ? next.slice(next.length - MAX_POINTS) : next;
      });
    }, setStatus);
    const timer = window.setInterval(() => {
      setStale(Date.now() - lastTs.current > STALE_MS);
    }, 2000);
    return () => {
      conn.close();
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (snapshot) lastTs.current = Date.now();
    setStale(false);
  }, [snapshot]);

  return { snapshot, status, stale, history };
}
