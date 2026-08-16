"""Services for configuring iMagi-x schedules."""
from __future__ import annotations

from datetime import time
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN

# Keep the service module compatible with older copies of const.py already
# installed in Home Assistant. The values are intentionally local constants so
# a partial update of the custom integration cannot prevent startup.
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_SCHEDULE = "schedule"
SERVICE_SET_HEATING_PRIORITY_SCHEDULE = "set_heating_priority_schedule"

_ATTR_END = "end"
_ATTR_START = "start"

_TIME_SLOT_SCHEMA = vol.Schema(
    {
        vol.Required(_ATTR_START): cv.string,
        vol.Required(_ATTR_END): cv.string,
    }
)

SERVICE_SET_HEATING_PRIORITY_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_SCHEDULE): vol.All(
            cv.ensure_list,
            vol.Length(min=1),
            [_TIME_SLOT_SCHEMA],
        ),
    }
)


def async_register_services(hass: HomeAssistant) -> None:
    """Register integration-wide services once."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_HEATING_PRIORITY_SCHEDULE):
        return

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_HEATING_PRIORITY_SCHEDULE,
        lambda call: _async_set_heating_priority_schedule(hass, call),
        schema=SERVICE_SET_HEATING_PRIORITY_SCHEDULE_SCHEMA,
    )


def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove integration-wide services when the last entry is unloaded."""
    hass.services.async_remove(DOMAIN, SERVICE_SET_HEATING_PRIORITY_SCHEDULE)


async def _async_set_heating_priority_schedule(
    hass: HomeAssistant, call: ServiceCall
) -> None:
    """Save the daily time slots in which heating may request filtration."""
    entries: dict[str, Any] = hass.data.get(DOMAIN, {})
    entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)

    if entry_id:
        coordinator = entries.get(entry_id)
        if coordinator is None:
            raise HomeAssistantError(f"Configuration iMagi-x inconnue : {entry_id}")
    elif len(entries) == 1:
        coordinator = next(iter(entries.values()))
    elif not entries:
        raise HomeAssistantError("Aucun coffret iMagi-x n'est configuré")
    else:
        raise HomeAssistantError(
            "Plusieurs coffrets iMagi-x sont configurés : indiquez config_entry_id"
        )

    heater = coordinator.data.get("state", {}).get("heater", {})
    if not isinstance(heater, dict) or not heater.get("presence"):
        raise HomeAssistantError("Aucune pompe à chaleur n'est déclarée sur ce coffret")

    planning = _slots_to_planning(call.data[ATTR_SCHEDULE])
    await coordinator.client.async_set_heater_priority_schedule(planning)
    await coordinator.async_request_refresh()


def _slots_to_planning(slots: list[dict[str, str]]) -> list[dict[str, int]]:
    """Convert user-friendly time slots to the controller's daily format."""
    # Explicitly reset the daily state at midnight. This is also the format
    # returned by the controller for a schedule which starts later in the day.
    changes: dict[int, int] = {0: 0}

    def add_change(minute: int, change: int) -> None:
        changes[minute] = changes.get(minute, 0) + change

    for slot in slots:
        start = _minutes_from_time(slot[_ATTR_START])
        end = _minutes_from_time(slot[_ATTR_END])
        if start == end:
            raise HomeAssistantError(
                "Un créneau de chauffage doit avoir des heures de début et de fin différentes"
            )

        if start < end:
            add_change(start, 1)
            add_change(end, -1)
        else:
            # A slot such as 22:00–06:00 spans midnight.
            add_change(0, 1)
            add_change(end, -1)
            add_change(start, 1)
            add_change(1440, -1)

    planning: list[dict[str, int]] = []
    active_slots = 0
    previous_value: int | None = None
    for minute in sorted(changes):
        active_slots += changes[minute]
        value = int(active_slots > 0)
        if value != previous_value:
            planning.append({"minute": minute, "value": value})
            previous_value = value

    return planning


def _minutes_from_time(value: str) -> int:
    """Parse a local time submitted by a Home Assistant service call."""
    try:
        parsed = time.fromisoformat(value)
    except ValueError as err:
        raise HomeAssistantError(
            f"Heure invalide : {value}. Utilisez le format HH:MM, par exemple 08:30"
        ) from err

    if parsed.second or parsed.microsecond:
        raise HomeAssistantError(
            f"Heure invalide : {value}. Les secondes ne sont pas prises en charge"
        )
    return parsed.hour * 60 + parsed.minute
