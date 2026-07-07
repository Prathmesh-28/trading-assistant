import type { AlertLevel } from "./types";

/** Tiny client-side toast bus so any component can surface an error/success
 * without prop drilling — App merges these into the same AlertBanner used for
 * server-pushed alerts. */

type Toast = { level: AlertLevel; message: string };
type Listener = (t: Toast) => void;

const listeners = new Set<Listener>();

export function onToast(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function toast(level: AlertLevel, message: string): void {
  listeners.forEach((fn) => fn({ level, message }));
}
