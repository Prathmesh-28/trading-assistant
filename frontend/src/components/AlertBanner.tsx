import type { AlertEvent } from "../types";

const ICON: Record<AlertEvent["level"], string> = {
  info: "ℹ",
  success: "✓",
  warning: "⚠",
  danger: "✕",
};

export function AlertBanner({ alerts, onDismiss }: { alerts: AlertEvent[]; onDismiss: (id: number) => void }) {
  if (!alerts.length) return null;
  return (
    <div className="alert-stack">
      {alerts.map((a) => (
        <div key={a.id} className={`alert alert-${a.level}`} onClick={() => onDismiss(a.id)}>
          <span className="alert-icon" aria-hidden>
            {ICON[a.level]}
          </span>
          <span className="alert-msg">{a.message}</span>
        </div>
      ))}
    </div>
  );
}
