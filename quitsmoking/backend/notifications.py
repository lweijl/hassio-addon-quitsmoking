"""Home Assistant notification helper via Supervisor API.

Supports actionable notifications with buttons that can:
- Open the addon UI (URI action)
- Trigger API endpoints (URI action to ingress path)
- Fire HA events (standard action key)

Notification targets are configurable:
- NOTIFY_SERVICES: comma-separated list of services (e.g., "mobile_app_iphone,mobile_app_pixel")
- NOTIFY_SERVICE: single legacy service (fallback if NOTIFY_SERVICES is empty)
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

# Build the list of notify services to target
_NOTIFY_SERVICES_RAW = os.environ.get("NOTIFY_SERVICES", "")
_NOTIFY_SERVICE_RAW = os.environ.get("NOTIFY_SERVICE", "")


def _parse_notify_services() -> list[str]:
    """Parse configured notify services into a list of service names (without 'notify.' prefix)."""
    services: list[str] = []

    # Primary: list from NOTIFY_SERVICES (comma-separated)
    if _NOTIFY_SERVICES_RAW.strip():
        for svc in _NOTIFY_SERVICES_RAW.split(","):
            svc = svc.strip().removeprefix("notify.")
            if svc:
                services.append(svc)

    # Fallback: single legacy NOTIFY_SERVICE
    if not services and _NOTIFY_SERVICE_RAW.strip():
        svc = _NOTIFY_SERVICE_RAW.strip().removeprefix("notify.")
        if svc:
            services.append(svc)

    # Ultimate fallback: broadcast to all
    if not services:
        services.append("notify")

    return services


NOTIFY_SERVICES = _parse_notify_services()


def _addon_uri(path: str = "") -> str:
    """Build a URI that opens the addon's ingress UI inside the HA companion app.

    The HA frontend route for an addon's ingress panel is:
    /hassio/addon/<slug>/ingress
    This is what the sidebar and "OPEN WEB UI" button use.
    """
    slug = os.environ.get("ADDON_SLUG", "472f365d_quitsmoking")
    return f"/hassio/addon/{slug}/ingress{path}"


# ---------------------------------------------------------------------------
# Notification action presets
# ---------------------------------------------------------------------------

class Actions:
    """Pre-built action sets for different notification scenarios.

    All URI actions use /hassio/ingress/local_quitsmoking which opens
    inside the HA companion app (not Safari).

    For actions that need to trigger API calls (log, skip), we open
    the addon UI with a query parameter that the frontend handles.
    """

    @staticmethod
    def log_cigarette() -> dict:
        """Action button that opens addon and auto-logs a cigarette."""
        return {
            "action": "URI",
            "title": "🚬 Log it",
            "uri": _addon_uri("/?action=log"),
        }

    @staticmethod
    def log_bonus() -> dict:
        """Action button that opens addon and auto-logs a bonus."""
        return {
            "action": "URI",
            "title": "🎁 Use Bonus",
            "uri": _addon_uri("/?action=log_bonus"),
        }

    @staticmethod
    def skip() -> dict:
        """Action button that opens addon and records a skip."""
        return {
            "action": "URI",
            "title": "💪 Skip it",
            "uri": _addon_uri("/?action=skip"),
        }

    @staticmethod
    def open_app() -> dict:
        """Action button that opens the addon UI in the companion app."""
        return {
            "action": "URI",
            "title": "📱 Open",
            "uri": _addon_uri("/"),
        }

    @staticmethod
    def open_progress() -> dict:
        """Action button that opens the progress tab."""
        return {
            "action": "URI",
            "title": "📊 Progress",
            "uri": _addon_uri("/"),
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
        # Allow replacing previous notification with same tag
        notification_data["notification_id"] = tag
    # Tapping the notification body opens the addon
    if "url" not in notification_data:
        notification_data["url"] = _addon_uri("/")
    if notification_data:
        payload["data"] = notification_data

    any_success = False

    try:
        async with aiohttp.ClientSession() as session:
            for service in NOTIFY_SERVICES:
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
