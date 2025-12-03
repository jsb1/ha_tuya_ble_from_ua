"""The Tuya BLE integration."""
from __future__ import annotations

from dataclasses import dataclass
import logging

from bleak_retry_connector import BLEAK_RETRY_EXCEPTIONS as BLEAK_EXCEPTIONS, get_device

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.match import ADDRESS, BluetoothCallbackMatcher
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady

from .tuya_ble.ble import TuyaBLEDevice, TuyaBLEDeviceCredentials
from .tuya_ble.manager import shared_tuya_device_manager, TuyaBLEDeviceManager, TuyaBLECoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class TuyaBLEData:
    """Data for the Tuya BLE integration."""
    title: str
    coordinator: TuyaBLECoordinator

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tuya BLE from a config entry."""
    address: str = entry.data[CONF_ADDRESS]

    coordinator = TuyaBLECoordinator(hass, entry, address, entry.options)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = TuyaBLEData(
        entry.title,
        coordinator,
    )

    await hass.config_entries.async_forward_entry_setups(entry, [])
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    async def _async_stop(event: Event) -> None:
        """Close the connection."""
        await coordinator._async_stop()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
    )
    entry.async_on_unload(
        coordinator.async_start()
    )

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    data: TuyaBLEData = hass.data[DOMAIN][entry.entry_id]
    if entry.title != data.title:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
#    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
    data: TuyaBLEData = hass.data[DOMAIN].pop(entry.entry_id)
    await data.device.stop()

    return True
