"""WebSocket event listener for HA notification actions."""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import uuid4

from .engine import TZ
from .models import CigaretteEntry
from .notifications import send_notification, Actions, SUPERVISOR_TOKEN
from .state import _get_engine, _now, _build_status, entry_store

logger = logging.getLogger(__name__)


async def _ws_event_listener() -> None:
    """Connect to HA websocket and listen for notification action events.

    When the user taps QS_LOG, QS_LOG_BONUS, or QS_SKIP on a notification,
    the companion app fires a mobile_app_notification_action event.
    We subscribe to these and handle them directly.
    """
    import aiohttp

    if not SUPERVISOR_TOKEN:
        logger.warning("No SUPERVISOR_TOKEN — notification action listener disabled")
        return

    ws_url = "ws://supervisor/core/websocket"
    msg_id = 1

    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url) as ws:
                    # Wait for auth_required
                    auth_req = await ws.receive_json()
                    if auth_req.get("type") != "auth_required":
                        logger.error("WS: unexpected message: %s", auth_req)
                        await asyncio.sleep(30)
                        continue

                    # Authenticate
                    await ws.send_json({
                        "type": "auth",
                        "access_token": SUPERVISOR_TOKEN,
                    })
                    auth_result = await ws.receive_json()
                    if auth_result.get("type") != "auth_ok":
                        logger.error("WS: auth failed: %s", auth_result)
                        await asyncio.sleep(30)
                        continue

                    logger.info("WS: connected and authenticated")

                    # Subscribe to mobile_app_notification_action events
                    await ws.send_json({
                        "id": msg_id,
                        "type": "subscribe_events",
                        "event_type": "mobile_app_notification_action",
                    })
                    sub_result = await ws.receive_json()
                    if not sub_result.get("success"):
                        logger.error("WS: subscribe failed: %s", sub_result)
                        await asyncio.sleep(30)
                        continue

                    logger.info("WS: subscribed to mobile_app_notification_action events")

                    # Listen for events
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            if data.get("type") == "event":
                                event_data = data.get("event", {}).get("data", {})
                                action = event_data.get("action", "")
                                await _handle_notification_action(action)
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("WS event listener error: %s", exc)

        # Reconnect after 10 seconds
        await asyncio.sleep(10)


async def _handle_notification_action(action: str) -> None:
    """Handle a notification action event."""
    if action == "QS_LOG":
        engine = await _get_engine()
        now = _now()
        entry = CigaretteEntry(id=uuid4(), timestamp=now, is_bonus=False)
        await entry_store.add_entry(entry)
        entries = await entry_store.load()
        status = _build_status(engine, entries)
        await send_notification(
            "🚬 Logged!",
            f"Cigarette logged. {status.remaining_today} remaining today.",
            tag="logged",
        )
        logger.info("Notification action: logged cigarette")

    elif action == "QS_LOG_BONUS":
        engine = await _get_engine()
        now = _now()
        entry = CigaretteEntry(id=uuid4(), timestamp=now, is_bonus=True)
        await entry_store.add_entry(entry)
        entries = await entry_store.load()
        status = _build_status(engine, entries)
        await send_notification(
            "🎁 Bonus logged!",
            f"Bonus cigarette logged. {status.remaining_bonus} bonus remaining this week.",
            tag="logged",
        )
        logger.info("Notification action: logged bonus")

    elif action == "QS_SKIP":
        engine = await _get_engine()
        entries = await entry_store.load()
        now = _now()
        total_smoked = len(entries)
        avoided = engine.cigarettes_avoided(total_smoked, now)
        saved = engine.money_saved(total_smoked, now)

        from random import choice
        encouragements = [
            "You're stronger than the craving! 💪",
            "Every skip is a victory. Keep going! 🏆",
            "Your lungs just thanked you. 🫁",
            "Craving passed. Freedom gets easier! 🌅",
            "That's willpower in action! 🔥",
        ]
        msg = choice(encouragements)
        await send_notification(
            "💪 Craving resisted!",
            f"{msg} You've avoided {avoided} cigarettes (€{saved:.2f} saved).",
            tag="encouragement",
        )
        logger.info("Notification action: skipped")

    elif action == "QS_TEST":
        await send_notification(
            "✅ Event received!",
            "Background action handling works. Nothing was logged.",
            tag="test_result",
        )
        logger.info("Notification action: test event received")

    elif action == "QS_STAY_STRONG":
        # Intentional no-op — tapping "Stay Strong" is just an acknowledgment
        logger.info("Notification action: stay strong (dismissed)")
