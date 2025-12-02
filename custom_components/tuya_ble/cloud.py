"""The Tuya BLE integration."""
from __future__ import annotations

import logging

from dataclasses import dataclass
import json
from typing import Any, Iterable

from tuya_sharing.device import CustomerDevice
from tuya_sharing.manager import Manager

from homeassistant.components.tuya.const import DOMAIN as EXT_DOMAIN;
from homeassistant.const import CONF_ADDRESS, CONF_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .tuya_ble import (
    TuyaBLEDevice,
    TuyaBLEDeviceCredentials,
)

from .const import (
    CONF_PRODUCT_MODEL,
    CONF_UUID,
    CONF_LOCAL_KEY,
    CONF_CATEGORY,
    CONF_PRODUCT_ID,
    CONF_DEVICE_NAME,
    CONF_PRODUCT_NAME,
    CONF_LOCAL_STRATEGY,
)

_LOGGER = logging.getLogger(__name__)


CONF_TUYA_DEVICE_KEYS = [
    CONF_UUID,
    CONF_LOCAL_KEY,
    CONF_DEVICE_ID,
    CONF_CATEGORY,
    CONF_PRODUCT_ID,
    CONF_DEVICE_NAME,
    CONF_PRODUCT_NAME,
    CONF_PRODUCT_MODEL,
]

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

class HASSTuyaBLEDeviceManager:
    """Cloud connected manager of the Tuya BLE devices credentials."""

    def __init__(self, hass: HomeAssistant, data: dict[str, Any]) -> None:
        assert hass is not None
        self._hass = hass
        self._data = data
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


    async def find_device(self, ble_device, discovery_info):
        self.build_cache()
        for credentials in self._cache.values():
            device_info = TuyaBLEDeviceCredentials(**credentials)
            try_device = TuyaBLEDevice(device_info, ble_device, discovery_info)
            if await try_device.initialize():
                self._mac_mapping[discovery_info.address] = credentials
                return credentials
        return None

    @property
    def data(self) -> dict[str, Any]:
        return self._data
