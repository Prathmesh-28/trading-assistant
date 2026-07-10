"""Telegram push + phone commands.

Commands understood (typed to your bot from the phone):
  /status                     regime, bias, pending ideas, open positions + live PnL
  /positions                  open positions only
  /bought SYMBOL [qty] [px]   confirm you took an idea -> engine starts live sell alerts
  /sold SYMBOL [px]           you exited -> engine books PnL and stops monitoring
  /skip SYMBOL                dismiss a pending idea
  /pause /resume              stop/restart new idea generation (monitoring continues)
  /help                       this list

No TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID? Alerts print to the console instead
(commands unavailable in that mode).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

import httpx

from config import Settings

log = logging.getLogger("notifier")

CommandHandler = Callable[[str, list[str]], Awaitable[str]]


class Notifier:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._enabled = settings.has_telegram
        self._base = f"https://api.telegram.org/bot{settings.telegram_token}"
        self._chat_id = settings.telegram_chat_id
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(65.0, connect=10.0))
        self._offset = 0
        self._handler: CommandHandler | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def on_command(self, handler: CommandHandler) -> None:
        self._handler = handler

    async def send(self, text: str) -> None:
        if not self._enabled:
            print(f"\n=== ALERT ===\n{text}\n=============")
            return
        for attempt in range(3):   # stop-hit alerts must not die on one blip
            try:
                resp = await self._client.post(
                    f"{self._base}/sendMessage",
                    json={"chat_id": self._chat_id, "text": text,
                          "disable_web_page_preview": True},
                )
                if resp.status_code == 200:
                    return
                log.warning("telegram send failed (try %d): %s %s",
                            attempt + 1, resp.status_code, resp.text[:200])
            except httpx.HTTPError as e:
                log.warning("telegram send error (try %d): %s", attempt + 1, e)
            await asyncio.sleep(1.5 * (attempt + 1))

    async def command_loop(self) -> None:
        """Long-poll getUpdates and dispatch /commands to the engine."""
        if not self._enabled:
            return
        while True:
            try:
                resp = await self._client.get(
                    f"{self._base}/getUpdates",
                    params={"timeout": 50, "offset": self._offset + 1,
                            "allowed_updates": '["message"]'},
                )
                data = resp.json()
                for update in data.get("result", []):
                    self._offset = max(self._offset, update["update_id"])
                    msg = update.get("message") or {}
                    text = (msg.get("text") or "").strip()
                    chat = str((msg.get("chat") or {}).get("id", ""))
                    if chat != str(self._chat_id) or not text.startswith("/"):
                        continue
                    parts = text.split()
                    cmd = parts[0].lstrip("/").lower().split("@")[0]
                    if self._handler:
                        try:
                            reply = await self._handler(cmd, parts[1:])
                        except Exception as e:  # a bad command must never kill the loop
                            log.exception("command %s failed", cmd)
                            reply = f"⚠️ {cmd} failed: {e}"
                        if reply:
                            await self.send(reply)
            except (httpx.HTTPError, ValueError) as e:
                log.warning("telegram poll error: %s", e)
                await asyncio.sleep(5)

    async def close(self) -> None:
        await self._client.aclose()
