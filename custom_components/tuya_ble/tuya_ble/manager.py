from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import logging
import sys
import traceback
from typing import Any

from homeassistant.components.bluetooth.active_update_coordinator import ActiveBluetoothDataUpdateCoordinator, BluetoothServiceInfoBleak
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .ble import TuyaBLEDevice
from .ble import TuyaBLEDeviceCredentials
from bleak_retry_connector import get_device
from homeassistant.components import bluetooth
from homeassistant.const import CONF_ADDRESS, CONF_DEVICE_ID
from homeassistant.components.tuya.const import DOMAIN as EXT_DOMAIN;
from tuya_sharing.device import CustomerDevice
from tuya_sharing.manager import Manager

from homeassistant.core import CALLBACK_TYPE, CoreState, HomeAssistant, callback

from .const import (
    CONF_PRODUCT_MODEL,
    CONF_UUID,
    CONF_LOCAL_KEY,
    CONF_CATEGORY,
    CONF_PRODUCT_ID,
    CONF_DEVICE_NAME,
    CONF_PRODUCT_NAME,
    CONF_LOCAL_STRATEGY,
    SET_DISCONNECTED_DELAY,
)

_LOGGER = logging.getLogger(__name__)

def customerDevice_to_dict(dev: CustomerDevice):
    return {
        CONF_UUID: dev.uuid,
        CONF_LOCAL_KEY: dev.local_key,
        CONF_DEVICE_ID: dev.id,
        CONF_CATEGORY: dev.category,
        CONF_PRODUCT_ID: dev.product_id,
        CONF_DEVICE_NAME: dev.name,
        CONF_PRODUCT_MODEL: dev.product_id,
        CONF_PRODUCT_NAME: dev.product_name,
        CONF_LOCAL_STRATEGY: dev.local_strategy,
    }

class TuyaBLEDeviceManager:
    """Cloud connected manager of the Tuya BLE devices credentials."""

    def __init__(self, hass: HomeAssistant) -> None:
        assert hass is not None
        self._hass = hass
        self._cache = {}
        self._mac_mapping = {}
        self._search_in_progress = set()
        self._search_failed = {}

    async def get_device_credentials(
        self,
        address: str,
        force_update: bool = False,
        save_data: bool = False,
    ) -> TuyaBLEDeviceCredentials | None:

        credentials=None
        if credentials:
            result = TuyaBLEDeviceCredentials(
                credentials
            )
            _LOGGER.debug("Retrieved: %s", result)
            item = None
            if save_data:
                if item:
                    self._data.update(item.login)
                self._data.update(credentials)

        return credentials

    async def get_devices_credentials(
        self,
    ) -> TuyaBLEDeviceCredentials | None:
        """Get credentials of the Tuya BLE device."""
        result: list[TuyaBLEDeviceCredentials] | None = None
        dev: CustomerDevice

        self.build_cache()
        return [
            TuyaBLEDeviceCredentials(
                credentials.get(CONF_UUID, ""),
                credentials.get(CONF_LOCAL_KEY, ""),
                credentials.get(CONF_DEVICE_ID, ""),
                credentials.get(CONF_CATEGORY, ""),
                credentials.get(CONF_PRODUCT_ID, ""),
                credentials.get(CONF_DEVICE_NAME, ""),
                credentials.get(CONF_PRODUCT_MODEL, ""),
                credentials.get(CONF_PRODUCT_NAME, ""),
            ) for credentials in self._cache.values()
        ]

    def build_cache(self):
        manager: Manager
        tuyaconfigentries = self._hass.config_entries.async_loaded_entries(EXT_DOMAIN)
        for entry in tuyaconfigentries:
            manager = entry.runtime_data.manager
            for device in manager.device_map.values():
                self._cache[device.id]=customerDevice_to_dict(device)


    async def find_device(self, discovery_info):

        self.build_cache()
        ble_device = bluetooth.async_ble_device_from_address(
            self._hass, discovery_info.address.upper(), True
        ) or await get_device(discovery_info.address)

        for credentials in self._cache.values():
            device_info = TuyaBLEDeviceCredentials(**credentials)
            try_device = TuyaBLEDevice(device_info, ble_device, discovery_info)
            if await try_device.initialize():
                self._mac_mapping[discovery_info.address] = credentials
                return credentials
        return None
    
    async def create_device(self, address: str, data: dict[str, Any]):
        ble_device = bluetooth.async_ble_device_from_address(
            self._hass, address.upper(), True
        ) or await get_device(address)

        device_info = TuyaBLEDeviceCredentials(**data)
        return TuyaBLEDevice(device_info, ble_device)

class TuyaBLECoordinator(ActiveBluetoothDataUpdateCoordinator[None]):
    """Data coordinator for receiving Tuya BLE updates."""

    def __init__(self, hass: HomeAssistant, device: TuyaBLEDevice, address: str) -> None:
        """Initialise the coordinator."""
        self._device = device
        self._disconnected: bool = True
        self._unsub_disconnect: CALLBACK_TYPE | None = None
        device.register_connected_callback(self._async_handle_connect)
        device.register_callback(self._async_handle_update)
        device.register_disconnected_callback(self._async_handle_disconnect)

        def _needs_poll(
            service_info: BluetoothServiceInfoBleak, last_poll: float | None
        ) -> bool:
            return (
                hass.state == CoreState.running
            )

        async def _async_poll(service_info: BluetoothServiceInfoBleak):
            value=service_info

        super().__init__(
            hass,
            _LOGGER,
            address = address,
            needs_poll_method=_needs_poll,
            poll_method=_async_poll,
            mode=bluetooth.BluetoothScanningMode.PASSIVE,
            connectable=True,
        )

    @property
    def connected(self) -> bool:
        return not self._disconnected

    @callback
    def _async_handle_connect(self) -> None:
        if self._unsub_disconnect is not None:
            self._unsub_disconnect()
        if self._disconnected:
            self._disconnected = False
            self.async_update_listeners()

    @callback
    def _async_handle_update(self, updates: list[Any]) -> None:
        """Just trigger the callbacks."""
        self._async_handle_connect()
        self.async_set_updated_data(None)

    @callback
    def _set_disconnected(self, _: None) -> None:
        """Invoke the idle timeout callback, called when the alarm fires."""
        self._disconnected = True
        self._unsub_disconnect = None
        self.async_update_listeners()

    @callback
    def _async_handle_disconnect(self) -> None:
        """Trigger the callbacks for disconnected."""
        if self._unsub_disconnect is None:
            delay: float = SET_DISCONNECTED_DELAY
            self._unsub_disconnect = async_call_later(
                self.hass, delay, self._set_disconnected
            )



def get_short_address(address: str) -> str:
    results = address.replace("-", ":").upper().split(":")
    return f"{results[-3]}{results[-2]}{results[-1]}"[-6:]


