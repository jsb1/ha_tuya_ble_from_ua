from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass
import logging
import sys
import traceback
from typing import Any

from bluetooth_data_tools import monotonic_time_coarse

from homeassistant.components.bluetooth.active_update_coordinator import ActiveBluetoothDataUpdateCoordinator, BluetoothServiceInfoBleak
from homeassistant.components.bluetooth.api import async_ble_device_from_address
from homeassistant.components.bluetooth.manager import BaseHaScanner
from homeassistant.config_entries import ConfigEntry
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

def get_short_address(address: str) -> str:
    results = address.replace("-", ":").upper().split(":")
    return f"{results[-3]}{results[-2]}{results[-1]}"[-6:]

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


    def find_device(self, discovery_info):

        self.build_cache()
        for credentials in self._cache.values():
            device_info = TuyaBLEDeviceCredentials(**credentials)
            try_device = TuyaBLEDevice(device_info, discovery_info)
            if try_device.initialize():
                self._mac_mapping[discovery_info.address] = credentials
                return credentials
        return None
    
    def create_device(self, address: str, data: dict[str, Any]):
        if CONF_LOCAL_KEY not in data:
            return None
        device_info = TuyaBLEDeviceCredentials(**data)
        return TuyaBLEDevice(device_info)

def shared_tuya_device_manager(hass: HomeAssistant) -> TuyaBLEDeviceManager:
    domain_key: str = '_tuya_ble_hack' # TODO
    if domain_key not in hass.data:
        hass.data[domain_key] = {}
    key: str = "TuyaBLEDeviceManager_instance"
    if key in hass.data[domain_key]:
        return hass.data[domain_key][key]
    manager: TuyaBLEDeviceManager = TuyaBLEDeviceManager(hass)
    hass.data[domain_key][key] = manager
    return manager

class TuyaBLECoordinator(ActiveBluetoothDataUpdateCoordinator[bool]):
    """Data coordinator for receiving Tuya BLE updates."""
   
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, address: str, options: dict[str, Any]) -> None:
        """Initialise the coordinator."""
        manager = shared_tuya_device_manager(hass)
        self._entry = entry
        self._device = manager.create_device(address, options)
        self._connected: bool = False
        self._device.register_connected_callback(self._async_handle_connect)
        self._device.register_callback(self._async_handle_update)
        self._device.register_disconnected_callback(self._async_handle_disconnect)
        self._min_poll_interval = 60
        self._next_poll = monotonic_time_coarse()
        self._max_connect_time = 10

        def _needs_poll(
            service_info: BluetoothServiceInfoBleak, last_poll: float | None
        ) -> bool:
            return (
                True
                #monotonic_time_coarse() >= self._next_poll
            )

        async def _async_poll(service_info: BluetoothServiceInfoBleak):
            #if hass.state != CoreState.running:
            #    return False
            if  monotonic_time_coarse() < self._next_poll:
                print("skip poll")
                return False
            print("poll")
            scanner = bluetooth.async_scanner_by_source(hass, address)

            if service_info.connectable:
                connectable_device = service_info.device
            elif device := async_ble_device_from_address(hass, service_info.device.address, True):
                connectable_device = device
            else:
                raise RuntimeError(f"No connectable device found for {service_info.device.address}")
            self._device.set_device_and_advertisement_data(connectable_device, service_info.advertisement)

            entry.async_create_task(hass, self._device._execute_timed_disconnect(15))
            await self._device.update()
            #entry.async_create_task(hass, self._device.update())
            #entry.async_create_task(hass, self._device.update_dp(2))
            self._next_poll += self._min_poll_interval
            print("poll done")
            return True

        super().__init__(
            hass,
            _LOGGER,
            address = address,
            needs_poll_method=_needs_poll,
            poll_method=_async_poll,
            mode=bluetooth.BluetoothScanningMode.ACTIVE,
            connectable=True,
        )

    @callback
    def _async_handle_connect(self) -> None:
        self._connect_stop_at = monotonic_time_coarse()+self._max_connect_time
        self._connected = True
        self._next_poll = monotonic_time_coarse() + self._min_poll_interval

    @callback
    def _async_handle_update(self, updates: list[Any]) -> None:
        print(updates)
        pass

    @callback
    def _set_disconnected(self, _: None) -> None:
        """Invoke the idle timeout callback, called when the alarm fires."""

    @callback
    def _async_handle_disconnect(self) -> None:
        """Trigger the callbacks for disconnected."""
        self._connected = False
        print("disconnect")


