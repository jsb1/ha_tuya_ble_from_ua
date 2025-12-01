"""Config flow for Tuya BLE integration."""

from __future__ import annotations

import asyncio
import logging
import pycountry
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

from .tuya_ble import SERVICE_UUID, TuyaBLEDeviceCredentials, TuyaBLEDevice
from bleak_retry_connector import BLEAK_RETRY_EXCEPTIONS as BLEAK_EXCEPTIONS, BleakNotFoundError, get_device

from .const import (
    DOMAIN,
)
from .devices import TuyaBLECoordinator, TuyaBLEData, get_device_readable_name
from .cloud import HASSTuyaBLEDeviceManager

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
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._data: dict[str, Any] = {}
        self._manager: HASSTuyaBLEDeviceManager | None = None
        self._get_device_info_error = False

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        await self.async_set_unique_id(discovery_info.address)
#        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        if self._manager is None:
            self._manager = HASSTuyaBLEDeviceManager(self.hass, self._data)
        self.context["title_placeholders"] = {
            "name": f"({discovery_info.address})",
            "discovery_info":  discovery_info,
        }
        self._discovered_devices[discovery_info.address] = discovery_info
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, discovery_info.address.upper(), True
        ) or await get_device(discovery_info.address)

        cred = await self._manager.find_device(ble_device, discovery_info)
        if not cred:
            return await self.async_abort("device not found")

        errors: dict[str, str] = {}

        address = discovery_info.address
        discovery_info = self._discovered_devices[address]
        local_name = cred.device_name
        await self.async_set_unique_id(
            discovery_info.address, raise_on_progress=False
        )
        self._abort_if_unique_id_configured()
        self._data[CONF_ADDRESS] = discovery_info.address
        return self.async_create_entry(
            title=local_name,
            data={CONF_ADDRESS: discovery_info.address},
            options=self._data,
        )


        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ADDRESS,
                        default=def_address,
                    ): vol.In(
                        {
                            service_info.address: await get_device_readable_name(
                                service_info,
                                self._manager,
                            )
                            for service_info in self._discovered_devices.values()
                        }
                    ),
                },
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> TuyaBLEOptionsFlow:
        """Get the options flow for this handler."""
        return TuyaBLEOptionsFlow(config_entry)
