import asyncio
import unittest
from unittest import mock

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from flamerite_bt.const import SUPPORTED_DEVICE_SVC_UUIDS
from flamerite_bt.scanner import scan_for_flamerite_devices


class FakeBleakScanner:
    """A simple fake BleakScanner implemented as an async context manager.

    It stores the provided detection callback on the instance so tests can invoke
    it to simulate discovered devices.
    """

    last_instance = None

    def __init__(self, detection_callback):
        self._cb = detection_callback
        FakeBleakScanner.last_instance = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestScanner(unittest.TestCase):
    def setUp(self) -> None:
        # Clear any previously created fake scanner instance.
        FakeBleakScanner.last_instance = None

    def test_finds_supported_device(self) -> None:
        with mock.patch(
            "flamerite_bt.scanner.BleakScanner", new=FakeBleakScanner
        ):

            async def run():
                # Run scan in a task so we can invoke the callback while it's waiting.
                task = asyncio.create_task(
                    scan_for_flamerite_devices(
                        scan_timeout_seconds=1, max_devices=1
                    )
                )

                # Wait for the fake scanner to be constructed inside the function.
                while FakeBleakScanner.last_instance is None:
                    await asyncio.sleep(0)

                # Simulate a BLE device with a supported advertised name.
                device = BLEDevice(
                    address="00:11:22:33:44:55", name="NITRAFlame", details={}
                )
                adv = AdvertisementData(
                    local_name="NITRAFlame",
                    manufacturer_data={},
                    service_data={},
                    service_uuids=SUPPORTED_DEVICE_SVC_UUIDS,
                    rssi=-60,
                    tx_power=None,
                    platform_data=(),
                )

                # Invoke the detection callback just like Bleak would.
                FakeBleakScanner.last_instance._cb(device, adv)

                devices = await task
                self.assertEqual(len(devices), 1)
                self.assertEqual(devices[0].address, "00:11:22:33:44:55")

            asyncio.run(run())

    def test_ignores_non_supported(self) -> None:
        with mock.patch(
            "flamerite_bt.scanner.BleakScanner", new=FakeBleakScanner
        ):

            async def run():
                # Short timeout so the test completes quickly when nothing is found.
                devices = await scan_for_flamerite_devices(
                    scan_timeout_seconds=1
                )
                self.assertEqual(devices, [])

            asyncio.run(run())

    def test_ignores_duplicates(self) -> None:
        with mock.patch(
            "flamerite_bt.scanner.BleakScanner", new=FakeBleakScanner
        ):

            async def run():
                task = asyncio.create_task(
                    scan_for_flamerite_devices(
                        scan_timeout_seconds=1, max_devices=-1
                    )
                )

                while FakeBleakScanner.last_instance is None:
                    await asyncio.sleep(0)

                # Two discovery events for the same MAC address should only
                # result in one entry.
                d1 = BLEDevice(
                    address="00:11:22:33:44:55", name="NITRAFlame", details={}
                )
                adv = AdvertisementData(
                    local_name="NITRAFlame",
                    manufacturer_data={},
                    service_data={},
                    service_uuids=SUPPORTED_DEVICE_SVC_UUIDS,
                    rssi=-60,
                    tx_power=None,
                    platform_data=(),
                )
                FakeBleakScanner.last_instance._cb(d1, adv)

                d2 = BLEDevice(
                    address="00:11:22:33:44:55", name="NITRAFlame", details={}
                )
                FakeBleakScanner.last_instance._cb(d2, adv)

                devices = await task
                self.assertEqual(len(devices), 1)

            asyncio.run(run())
