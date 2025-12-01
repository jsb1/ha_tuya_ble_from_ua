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
    DOMAIN,
    TUYA_API_DEVICES_URL,
    TUYA_API_FACTORY_INFO_URL,
    TUYA_FACTORY_INFO_MAC,
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
                credentials.get(CONF_UUID, ""),
                credentials.get(CONF_LOCAL_KEY, ""),
                credentials.get(CONF_DEVICE_ID, ""),
                credentials.get(CONF_CATEGORY, ""),
                credentials.get(CONF_PRODUCT_ID, ""),
                credentials.get(CONF_DEVICE_NAME, ""),
                credentials.get(CONF_PRODUCT_MODEL, ""),
                credentials.get(CONF_PRODUCT_NAME, ""),
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
                dev.uuid, 
                dev.local_key, 
                dev.id, 
                dev.category, 
                dev. product_id,
                dev.name, 
                dev.product_id, 
                dev.product_name
            ) for dev in self._cache.values()
        ]

    def build_cache(self):
        manager: Manager
        tuyaconfigentries = self._hass.config_entries.async_loaded_entries(EXT_DOMAIN)
        for entry in tuyaconfigentries:
            manager = entry.runtime_data.manager
            self._cache = self._cache | manager.device_map

    async def find_device(self, ble_device, discovery_info):
        for cred in await self.get_devices_credentials():
            try_device = TuyaBLEDevice(cred, ble_device, discovery_info)
            if await try_device.initialize():
                self._mac_mapping[discovery_info.address] = cred
                return cred
        return None

    @property
    def data(self) -> dict[str, Any]:
        return self._data
