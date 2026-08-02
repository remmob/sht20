"""Connection monitoring and notifications for the SHT20 Modbus integration.

The sensor has no alarm registers, but it can lose communication. This module
tracks that, notifies once the failure has lasted long enough, and reports the
recovery afterwards.

Mobile notifications can be held during a configurable quiet period; they are
sent as soon as that period ends. Persistent notifications are never held,
since they do not wake anyone up.
"""

from __future__ import annotations

import logging
from datetime import datetime, time

from homeassistant.components.persistent_notification import (
    async_create as create_persistent_notification,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change

from .const import (
    DOMAIN,
    CONF_NOTIFY_CONNECTION_ERRORS_MOBILE,
    CONF_NOTIFY_CONNECTION_ERRORS_PERSISTENT,
    CONF_NOTIFY_CONNECTION_ERRORS_SERVICES,
    CONF_CONNECTION_ERROR_NOTIFICATION_TITLE,
    CONF_CONNECTION_ERROR_DELAY,
    CONF_NOTIFY_RECOVERY,
    CONF_QUIET_HOURS_ENABLED,
    CONF_QUIET_HOURS_START,
    CONF_QUIET_HOURS_END,
    DEFAULT_NOTIFY_CONNECTION_ERRORS_MOBILE,
    DEFAULT_NOTIFY_CONNECTION_ERRORS_PERSISTENT,
    DEFAULT_NOTIFY_CONNECTION_ERRORS_SERVICES,
    DEFAULT_CONNECTION_ERROR_NOTIFICATION_TITLE,
    DEFAULT_CONNECTION_ERROR_DELAY,
    DEFAULT_NOTIFY_RECOVERY,
    DEFAULT_QUIET_HOURS_ENABLED,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_QUIET_HOURS_END,
)

_LOGGER = logging.getLogger(__name__)


def _parse_time(value, fallback: str) -> time:
    """Parse a "HH:MM" or "HH:MM:SS" string into a time object."""
    for candidate in (value, fallback):
        if isinstance(candidate, str):
            parts = candidate.split(":")
            try:
                return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
            except (ValueError, IndexError):
                _LOGGER.warning("Invalid time value: %s", candidate)
    return time(0, 0)


class ConnectionMonitor:
    """Track connection failures and send the matching notifications."""

    def __init__(self, hass: HomeAssistant, name: str, options: dict, scan_interval: int) -> None:
        self.hass = hass
        self.name = name

        self._notify_mobile = options.get(
            CONF_NOTIFY_CONNECTION_ERRORS_MOBILE, DEFAULT_NOTIFY_CONNECTION_ERRORS_MOBILE
        )
        self._notify_persistent = options.get(
            CONF_NOTIFY_CONNECTION_ERRORS_PERSISTENT, DEFAULT_NOTIFY_CONNECTION_ERRORS_PERSISTENT
        )
        services = options.get(
            CONF_NOTIFY_CONNECTION_ERRORS_SERVICES, DEFAULT_NOTIFY_CONNECTION_ERRORS_SERVICES
        )
        self._notify_services = [s.strip() for s in services.split(",") if s.strip()] if services else []
        self._title = options.get(
            CONF_CONNECTION_ERROR_NOTIFICATION_TITLE, DEFAULT_CONNECTION_ERROR_NOTIFICATION_TITLE
        )
        self._notify_recovery = options.get(CONF_NOTIFY_RECOVERY, DEFAULT_NOTIFY_RECOVERY)

        # Notify only after the failure has lasted this long
        delay = options.get(CONF_CONNECTION_ERROR_DELAY, DEFAULT_CONNECTION_ERROR_DELAY)
        self._failures_for_delay = max(1, int(delay / max(1, scan_interval)))

        self._quiet_enabled = options.get(CONF_QUIET_HOURS_ENABLED, DEFAULT_QUIET_HOURS_ENABLED)
        self._quiet_start = _parse_time(options.get(CONF_QUIET_HOURS_START), DEFAULT_QUIET_HOURS_START)
        self._quiet_end = _parse_time(options.get(CONF_QUIET_HOURS_END), DEFAULT_QUIET_HOURS_END)

        self._consecutive_failures = 0
        self._connection_lost_time: datetime | None = None
        self._notified = False
        self._held_message: str | None = None
        self._remove_quiet_end_trigger = None

    @property
    def enabled(self) -> bool:
        """Whether any notification channel is switched on."""
        return self._notify_mobile or self._notify_persistent

    def start(self) -> None:
        """Start the trigger that releases held notifications."""
        if not self.enabled or not self._quiet_enabled:
            return

        self._remove_quiet_end_trigger = async_track_time_change(
            self.hass,
            self._release_held_notification,
            hour=self._quiet_end.hour,
            minute=self._quiet_end.minute,
            second=0,
        )
        _LOGGER.debug(
            "Quiet hours active for %s between %s and %s",
            self.name,
            self._quiet_start.strftime("%H:%M"),
            self._quiet_end.strftime("%H:%M"),
        )

    def stop(self) -> None:
        """Stop the quiet hours trigger."""
        if self._remove_quiet_end_trigger is not None:
            self._remove_quiet_end_trigger()
            self._remove_quiet_end_trigger = None

    def in_quiet_hours(self, moment: datetime | None = None) -> bool:
        """Whether the given moment falls inside the quiet period."""
        if not self._quiet_enabled:
            return False

        now = (moment or datetime.now()).time()
        if self._quiet_start == self._quiet_end:
            return False
        if self._quiet_start < self._quiet_end:
            return self._quiet_start <= now < self._quiet_end
        # The period runs across midnight, for example 23:00 - 07:00
        return now >= self._quiet_start or now < self._quiet_end

    async def async_failure(self) -> None:
        """Register a failed update and notify once the delay has passed."""
        self._consecutive_failures += 1
        if self._consecutive_failures == 1:
            self._connection_lost_time = datetime.now()

        if not self.enabled or self._notified:
            return
        if self._consecutive_failures < self._failures_for_delay:
            _LOGGER.debug(
                "Connection failure %s/%s for %s",
                self._consecutive_failures,
                self._failures_for_delay,
                self.name,
            )
            return

        lost_time = (self._connection_lost_time or datetime.now()).strftime("%d-%m-%Y %H:%M:%S")
        message = f"Communicatie met {self.name} verloren sinds {lost_time}"
        self._notified = True
        await self._send(message)

    async def async_restored(self) -> None:
        """Register a successful update and report the recovery."""
        was_notified = self._notified

        self._consecutive_failures = 0
        self._connection_lost_time = None
        self._notified = False

        if not was_notified:
            return

        # Nothing was sent yet, so there is nothing to recover from either
        held = self._held_message is not None
        self._held_message = None

        if not self._notify_recovery or not self.enabled or held:
            return

        await self._send(f"Communicatie met {self.name} hersteld")

    async def _send(self, message: str) -> None:
        """Send the message over the enabled channels, respecting quiet hours."""
        if self._notify_persistent:
            create_persistent_notification(
                self.hass, message, self._title, f"{DOMAIN}_{self.name}_connection_error"
            )

        if not self._notify_mobile:
            return

        if self.in_quiet_hours():
            self._held_message = message
            _LOGGER.debug(
                "Holding mobile notification for %s until %s (quiet hours)",
                self.name,
                self._quiet_end.strftime("%H:%M"),
            )
            return

        await self._send_mobile(message)

    async def _send_mobile(self, message: str) -> None:
        for service_name in self._notify_services:
            try:
                await self.hass.services.async_call(
                    "notify", service_name, {"title": self._title, "message": message}
                )
                _LOGGER.debug("Sent mobile notification to %s", service_name)
            except Exception as err:
                _LOGGER.error("Failed to send notification to %s: %s", service_name, err)

    @callback
    def _release_held_notification(self, _now) -> None:
        """Send the notification that was held during the quiet period."""
        if self._held_message is None:
            return

        message = self._held_message
        self._held_message = None

        # Report the current situation, not the one from hours ago
        if not self._notified:
            message = f"{message} (inmiddels hersteld)"

        self.hass.async_create_task(self._send_mobile(message))
