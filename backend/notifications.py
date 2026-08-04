"""Home Assistant notification helper via Supervisor API."""

from __future__ import annotations

import logging
import os

import aiohttp

logger = logging.getLogger(__name__)

SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
NOTIFY_SERVICE = os.environ.get("NOTIFY_SERVICE", "notify")
SUPERVISOR_API = "http://supervisor/core/api"


async def send_notification(title: str, message: str) -> bool:
    """Send a notification via Home Assistant's Supervisor API.

    Returns True on success, False on failure (non-fatal).
    """
    if not SUPERVISOR_TOKEN:
        logger.warning("SUPERVISOR_TOKEN not set — skipping notification")
        return False

    url = f"{SUPERVISOR_API}/services/notify/{NOTIFY_SERVICE}"
    headers = {
        "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "title": title,
        "message": message,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status < 300:
                    logger.info("Notification sent: %s", title)
                    return True
                else:
                    body = await resp.text()
                    logger.error(
                        "Notification failed (%d): %s", resp.status, body
                    )
                    return False
    except Exception as exc:
        logger.error("Notification error: %s", exc)
        return False
