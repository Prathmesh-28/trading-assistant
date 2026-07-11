import { useEffect, useState } from "react";
import { api } from "../api";
import { toast } from "../toast";

/** Telegram delivery health + the mute kill switch (engine keeps running,
 * phone goes quiet). */
export function TelegramPanel() {
  const [st, setSt] = useState<{ configured: boolean; muted: boolean; last_sent_at: string | null; last_error: string | null } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => api.telegramStatus().then(setSt).catch(() => {});
  useEffect(() => { load(); }, []);

  const toggleMute = async () => {
    if (!st) return;
    setBusy(true);
    try {
      await api.patchSettings({ alerts_muted: !st.muted });
      toast("success", st.muted ? "Phone alerts back on." : "Phone alerts muted — dashboard still updates.");
      load();
    } catch {
      toast("danger", "Could not change alert settings.");
    } finally {
      setBusy(false);
    }
  };

  if (!st) return <p className="text-muted empty-note">Checking Telegram…</p>;

  return (
    <div className="telegram-panel">
      <div className="tg-row">
        <span>Connection</span>
        <strong className={st.configured ? "good" : "critical"}>
          {st.configured ? "● configured" : "○ not set up"}
        </strong>
      </div>
      <div className="tg-row">
        <span>Last message sent</span>
        <strong className="mono">{st.last_sent_at ?? "none this session"}</strong>
      </div>
      {st.last_error && (
        <div className="tg-row">
          <span>Last error</span>
          <strong className="critical">{st.last_error}</strong>
        </div>
      )}
      <button className={`btn-big ${st.muted ? "btn-buy" : "btn-ignore"}`} disabled={busy} onClick={toggleMute}>
        {st.muted ? "🔔 Unmute phone alerts" : "🔕 Mute all phone alerts"}
      </button>
      {!st.configured && (
        <p className="more-foot">
          Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in Render to get ideas on your phone.
        </p>
      )}
    </div>
  );
}
