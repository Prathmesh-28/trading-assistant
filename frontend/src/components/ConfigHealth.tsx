import { useEffect, useState } from "react";
import { api } from "../api";

/** Surfaces boot-time config warnings (default password, missing creds…) so a
 * misconfigured deploy is visible in the UI, not just the server logs. */
export function ConfigHealth() {
  const [warnings, setWarnings] = useState<string[]>([]);

  useEffect(() => {
    api.configHealth().then((r) => setWarnings(r.warnings)).catch(() => {});
  }, []);

  if (warnings.length === 0) {
    return <p className="cfg-ok good">✓ Config looks healthy — no warnings at boot.</p>;
  }
  return (
    <div className="cfg-warns">
      {warnings.map((w) => (
        <p className="cfg-warn" key={w}>⚠ {w}</p>
      ))}
    </div>
  );
}
