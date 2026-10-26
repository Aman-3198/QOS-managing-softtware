// Display formatting helpers. Decimal Mbps/MB (1 Mbps = 1,000,000 bit/s).
// "Unavailable" is shown when the backend reports a null speed — we never
// invent a value.

export function formatBps(bps: number | null | undefined): string {
  if (bps === null || bps === undefined) return "Unavailable";
  const mbps = bps / 1_000_000;
  if (mbps >= 1) return `${mbps.toFixed(mbps >= 10 ? 0 : 1)} Mbps`;
  const kbps = bps / 1000;
  return `${kbps.toFixed(0)} kbps`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const mb = bytes / (1024 * 1024);
  if (mb < 1) return `${(bytes / 1024).toFixed(0)} KB`;
  const gb = mb / 1024;
  if (gb < 1) return `${mb.toFixed(1)} MB`;
  return `${gb.toFixed(2)} GB`;
}

// Numeric Mbps for charts (decimal). Returns null for unavailable (no faking).
export function toMbps(bps: number | null | undefined): number | null {
  if (bps === null || bps === undefined) return null;
  return bps / 1_000_000;
}

export function formatTime(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleTimeString();
  } catch {
    return "—";
  }
}

export function classNames(...xs: (string | false | null | undefined)[]): string {
  return xs.filter(Boolean).join(" ");
}
