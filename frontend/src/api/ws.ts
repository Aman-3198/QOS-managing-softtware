// WebSocket client with auto-reconnect (exponential backoff) + heartbeat.
// Single connection per dashboard; no duplicate polling loops.
import type { MonitorSnapshot } from "../types";

// Same-origin: in dev Vite proxies /ws to the backend; in prod the FastAPI app
// serves the SPA on the same origin, so /ws is same-origin too.
const WS_URL = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/monitor`;

export interface MonitorConnection {
  close: () => void;
}

export function openMonitor(
  onSnapshot: (s: MonitorSnapshot) => void,
  onStatus?: (status: "connecting" | "open" | "closed") => void
): MonitorConnection {
  let ws: WebSocket | null = null;
  let closed = false;
  let backoff = 500;
  let heartbeatTimer: number | null = null;

  const connect = () => {
    onStatus?.("connecting");
    ws = new WebSocket(WS_URL);
    ws.onopen = () => {
      backoff = 500;
      onStatus?.("open");
      heartbeatTimer = window.setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, 10000);
    };
    ws.onmessage = (ev) => {
      // Ignore "pong" replies; parse JSON snapshots.
      if (ev.data === "pong") return;
      try {
        onSnapshot(JSON.parse(ev.data) as MonitorSnapshot);
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onclose = () => {
      if (heartbeatTimer) window.clearInterval(heartbeatTimer);
      onStatus?.("closed");
      if (!closed) {
        backoff = Math.min(backoff * 2, 8000);
        window.setTimeout(connect, backoff);
      }
    };
    ws.onerror = () => ws?.close();
  };

  connect();

  return {
    close: () => {
      closed = true;
      if (heartbeatTimer) window.clearInterval(heartbeatTimer);
      ws?.close();
    },
  };
}
