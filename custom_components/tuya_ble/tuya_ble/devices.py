"""The Tuya BLE integration."""
from __future__ import annotations
from dataclasses import dataclass

import logging

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)
from .manager import TuyaBLEDeviceManager
from .ble import TuyaBLEDevice

from .const import (
    SET_DISCONNECTED_DELAY,
)

_LOGGER = logging.getLogger(__name__)

