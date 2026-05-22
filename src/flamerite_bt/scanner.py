"""Simple scanner for locating Flamerite devices."""

import asyncio
import logging
from typing import Callable

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from .device import Device

_LOGGER = logging.getLogger(__name__)

DeviceCallbackType = Callable[[BLEDevice], None]


async def scan_for_flamerite_devices(
    scan_timeout_seconds=60,
    max_devices=-1,
) -> list[BLEDevice]:
    """Scan for Flamerite devices and invoke the callback for each found device."""

    device_list: list[BLEDevice] = []
    _LOGGER.debug("Scanning for Flamerite devices")

    scan_done = asyncio.Event()

    def _detection_callback(
        ble_device: BLEDevice,
        ble_advertisement_data: AdvertisementData,
    ) -> None:
        if not Device.is_supported_device(ble_advertisement_data):
            return

        already_seen = [
            d for d in device_list if d.address == ble_device.address
        ]
        if len(already_seen) > 0:
            return

        _LOGGER.debug("Found Flamerite device: %s", ble_device)
        device_list.append(ble_device)

        # If we've reached the threshold, signal to stop scanning early.
        if max_devices != -1 and len(device_list) == max_devices:
            scan_done.set()

    # Scan for compatible devices up to scan_timeout_seconds seconds or until the
    # required number of devices is found.
    async with BleakScanner(_detection_callback):
        try:
            await asyncio.wait_for(
                scan_done.wait(), timeout=scan_timeout_seconds
            )
        except asyncio.TimeoutError:
            # Timeout elapsed; proceed with whatever devices were found.
            pass

    _LOGGER.debug("Scan complete, found %d Flamerite devices", len(device_list))
    return device_list
