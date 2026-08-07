"""Home Assistant notification helper via Supervisor API.

Supports actionable notifications with buttons that can:
- Open the addon UI (URI action)
- Trigger API endpoints (URI action to ingress path)
- Fire HA events (standard action key)

Notification targets are configurable via in-app settings (stored in SQLite DB).
Falls back to NOTIFY_SERVICES/NOTIFY_SERVICE env vars for backward compatibility.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
SUPERVISOR_API = "http://supervisor/core/api"
INGRESS_PATH = os.environ.get("INGRESS_PATH", "")


async def get_notify_services() -> list[str]:
    """Get notification services — reads from DB, falls back to env var."""
    from .state import notify_service_store

    services = await notify_service_store.get_services()
    if services:
        return [s.removeprefix("notify.") for s in services]

    # Fallback to env var (backward compat during transition)
    raw = os.environ.get("NOTIFY_SERVICES", "")
    if raw.strip():
        return [s.strip().removeprefix("notify.") for s in raw.split(",") if s.strip()]

    raw_single = os.environ.get("NOTIFY_SERVICE", "")
    if raw_single.strip():
        return [raw_single.strip().removeprefix("notify.")]

    return ["notify"]  # broadcast fallback


def _addon_uri(path: str = "") -> str:
    """Build a URI that opens the addon's ingress UI inside the HA companion app.

    The sidebar panel path is /<slug> which the companion app navigates to correctly.
    Note: HA uses underscore in panel paths, not hyphen.
    """
    slug = os.environ.get("ADDON_SLUG", "") or "472f365d_quitsmoking"
    # HA panel paths use underscore, HOSTNAME uses hyphen — normalize
    slug = slug.replace("-", "_")
    return f"/{slug}{path}"


# ---------------------------------------------------------------------------
# Notification action presets
# ---------------------------------------------------------------------------

class Actions:
    """Pre-built action sets for different notification scenarios.

    - Open/Progress: URI actions that open the addon panel in the companion app.
    - Log/Skip/Bonus: Non-URI actions that fire HA events. The addon listens
      for these via websocket and handles them in the background (no app opening).
    """

    @staticmethod
    def log_cigarette() -> dict:
        """Action button that logs a cigarette in the background."""
        return {
            "action": "QS_LOG",
            "title": "🚬 Log it",
        }

    @staticmethod
    def log_bonus() -> dict:
        """Action button that logs a bonus cigarette in the background."""
        return {
            "action": "QS_LOG_BONUS",
            "title": "🎁 Use Bonus",
        }

    @staticmethod
    def skip() -> dict:
        """Action button that records a skip in the background."""
        return {
            "action": "QS_SKIP",
            "title": "💪 Skip it",
        }

    @staticmethod
    def open_app() -> dict:
        """Action button that opens the addon UI in the companion app."""
        return {
            "action": "URI",
            "title": "📱 Open",
            "uri": _addon_uri(""),
        }

    @staticmethod
    def open_progress() -> dict:
        """Action button that opens the progress tab."""
        return {
            "action": "URI",
            "title": "📊 Progress",
            "uri": _addon_uri(""),
        }

    @staticmethod
    def stay_strong() -> dict:
        """Dismiss/encouragement action."""
        return {
            "action": "QS_STAY_STRONG",
            "title": "💪 Stay Strong",
        }


# ---------------------------------------------------------------------------
# Notification sender
# ---------------------------------------------------------------------------

async def send_notification(
    title: str,
    message: str,
    actions: Optional[list[dict]] = None,
    data: Optional[dict] = None,
    tag: Optional[str] = None,
) -> bool:
    """Send a notification to all configured services via Home Assistant's Supervisor API.

    Args:
        title: Notification title
        message: Notification body
        actions: List of action button dicts (action, title, uri)
        data: Additional notification data (images, urgency, etc.)
        tag: Notification tag for replacing/clearing

    Returns True if at least one service succeeded, False if all failed.
    """
    if not SUPERVISOR_TOKEN:
        logger.warning("SUPERVISOR_TOKEN not set — skipping notification")
        return False

    headers = {
        "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
        "Content-Type": "application/json",
    }

    payload: dict = {
        "title": title,
        "message": message,
    }

    # Build the data dict for HA companion app
    notification_data: dict = {}
    if data:
        notification_data.update(data)
    if actions:
        notification_data["actions"] = actions
    if tag:
        notification_data["tag"] = tag
    # Note: do NOT set "url" in data — on iOS it can override action URI behavior.
    # The action buttons handle navigation via their own "uri" key.
    if notification_data:
        payload["data"] = notification_data

    any_success = False

    try:
        async with aiohttp.ClientSession() as session:
            services = await get_notify_services()
            for service in services:
                url = f"{SUPERVISOR_API}/services/notify/{service}"
                try:
                    async with session.post(
                        url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        if resp.status < 300:
                            logger.info(
                                "Notification sent to %s: %s (actions: %s)",
                                service, title, bool(actions),
                            )
                            any_success = True
                        else:
                            body = await resp.text()
                            logger.error(
                                "Notification to %s failed (%d): %s",
                                service, resp.status, body,
                            )
                except Exception as exc:
                    logger.error("Notification to %s error: %s", service, exc)
    except Exception as exc:
        logger.error("Notification session error: %s", exc)
        return False

    return any_success
