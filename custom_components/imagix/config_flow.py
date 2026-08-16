"""Config flow for iMagi-x integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .adaptive_filtration.config import (
    CONF_ADAPTIVE_ENABLED,
    CONF_DEBT_LIMIT,
    CONF_HIGH_FLOW,
    CONF_HIGH_RPM,
    CONF_LOW_FLOW,
    CONF_LOW_RPM,
    CONF_MAX_EFH,
    CONF_MEDIUM_FLOW,
    CONF_MEDIUM_RPM,
    CONF_MIN_EFH,
    CONF_MINIMUM_RUN,
    CONF_REFERENCE_VOLUME,
    CONF_SOLAR_SHARE,
    CONF_STRATEGY,
    AdaptiveFiltrationConfig,
)
from .adaptive_filtration.models import Strategy
from .api import ImagixApiClient, ImagixConnectionError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_IP_ADDRESS): cv.string,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.
    
    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    session = async_get_clientsession(hass)
    client = ImagixApiClient(data[CONF_IP_ADDRESS], session)
    
    if not await client.test_connection():
        raise ImagixConnectionError("Cannot connect to iMagi-x controller")
    
    # Return info that you want to store in the config entry.
    return {"title": f"iMagi-x ({data[CONF_IP_ADDRESS]})"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for iMagi-x."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the adaptive filtration options flow."""
        return ImagixOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except ImagixConnectionError:
                _LOGGER.exception("Cannot connect to iMagi-x")
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class ImagixOptionsFlow(config_entries.OptionsFlow):
    """Configure adaptive filtration without changing connection data."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Show and save adaptive filtration settings."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        defaults = AdaptiveFiltrationConfig()
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ADAPTIVE_ENABLED,
                    default=options.get(CONF_ADAPTIVE_ENABLED, defaults.enabled),
                ): cv.boolean,
                vol.Optional(
                    CONF_STRATEGY,
                    default=options.get(CONF_STRATEGY, defaults.strategy.value),
                ): vol.In([strategy.value for strategy in Strategy]),
                vol.Optional(
                    CONF_REFERENCE_VOLUME,
                    default=options.get(
                        CONF_REFERENCE_VOLUME,
                        defaults.reference_volume_m3,
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=1, max=1000)),
                vol.Optional(
                    CONF_LOW_FLOW,
                    default=options.get(CONF_LOW_FLOW, defaults.low_flow_m3h),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=100)),
                vol.Optional(
                    CONF_MEDIUM_FLOW,
                    default=options.get(CONF_MEDIUM_FLOW, defaults.medium_flow_m3h),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=100)),
                vol.Optional(
                    CONF_HIGH_FLOW,
                    default=options.get(CONF_HIGH_FLOW, defaults.high_flow_m3h),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=100)),
                vol.Optional(
                    CONF_LOW_RPM,
                    default=options.get(CONF_LOW_RPM, defaults.low_rpm),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10000)),
                vol.Optional(
                    CONF_MEDIUM_RPM,
                    default=options.get(CONF_MEDIUM_RPM, defaults.medium_rpm),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10000)),
                vol.Optional(
                    CONF_HIGH_RPM,
                    default=options.get(CONF_HIGH_RPM, defaults.high_rpm),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10000)),
                vol.Optional(
                    CONF_MIN_EFH,
                    default=options.get(CONF_MIN_EFH, defaults.min_efh),
                ): vol.All(vol.Coerce(float), vol.Range(min=0, max=24)),
                vol.Optional(
                    CONF_MAX_EFH,
                    default=options.get(CONF_MAX_EFH, defaults.max_efh),
                ): vol.All(vol.Coerce(float), vol.Range(min=0, max=24)),
                vol.Optional(
                    CONF_MINIMUM_RUN,
                    default=options.get(
                        CONF_MINIMUM_RUN,
                        defaults.minimum_run_minutes,
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=180)),
                vol.Optional(
                    CONF_SOLAR_SHARE,
                    default=options.get(
                        CONF_SOLAR_SHARE,
                        defaults.solar_share_target,
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=0, max=1)),
                vol.Optional(
                    CONF_DEBT_LIMIT,
                    default=options.get(
                        CONF_DEBT_LIMIT,
                        defaults.debt_carry_limit_efh,
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=0, max=12)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
