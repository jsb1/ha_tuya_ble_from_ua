"""Config flow for Tuya BLE integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlowWithConfigEntry,
)
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowHandler, FlowResult

from bleak_retry_connector import BLEAK_RETRY_EXCEPTIONS as BLEAK_EXCEPTIONS, BleakNotFoundError, get_device

from .const import DOMAIN
from .tuya_ble.const import (
    CONF_DEVICE_NAME,
)

from .tuya_ble.manager import TuyaBLEDeviceManager, shared_tuya_device_manager


_LOGGER = logging.getLogger(__name__)

class TuyaBLEOptionsFlow(OptionsFlowWithConfigEntry):
    """Handle a Tuya BLE options flow."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__(config_entry)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        return await self.async_create_entry(
            "TBLE",
            user_input
        )
    

class TuyaBLEConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tuya BLE."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self._get_device_info_error = False

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        address = discovery_info.address
        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()

        manager = shared_tuya_device_manager(self.hass)
        cred = manager.find_device(discovery_info)
        if not cred:
            return await self.async_abort("device not found in tuya cloud")

        return self.async_create_entry(
            title=cred[CONF_DEVICE_NAME],
            data={CONF_ADDRESS: discovery_info.address},
            options=cred,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> TuyaBLEOptionsFlow:
        """Get the options flow for this handler."""
        return TuyaBLEOptionsFlow(config_entry)
