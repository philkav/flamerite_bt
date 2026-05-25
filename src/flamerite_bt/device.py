"""Device wrapper for the Flamerite Fireplace device."""

import asyncio
import logging
from collections.abc import Awaitable

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakError
from bleak_retry_connector import BleakClient  # type: ignore
from bleak_retry_connector import establish_connection

from .const import (
    ARCTECH_FOTH_PROFILE,
    DEVICE_RESPONSE_TIMEOUT_SECONDS,
    NITRAFLAME_PROFILE,
    SUPPORTED_DEVICE_NAMES,
    SUPPORTED_DEVICE_SVC_UUIDS,
    Color,
    Command,
    CommandProfile,
    DeviceAttribute,
    HeatMode,
)
from .state import State

_LOGGER = logging.getLogger(__name__)


class Device:
    """A wrapper class to interact with Flamerite Bluetooth devices."""

    _ble_device: BLEDevice
    _command_profile: CommandProfile
    _connection: BleakClient
    _connection_lock = asyncio.Lock()
    _is_connected: bool
    _mac: str
    _model_number: str
    _srial_number: str
    _manufacturer: str
    _name: str

    _state_lock = asyncio.Lock()
    _state: State
    _state_updated: asyncio.Event = asyncio.Event()

    def __init__(self, ble_device: BLEDevice) -> None:
        self._ble_device = ble_device
        self._command_profile = NITRAFLAME_PROFILE
        self._is_connected = False
        self._mac = ble_device.address
        self._name = ble_device.name or ""
        self._state = State(accepts_short_ack_state=False)

    @staticmethod
    def is_supported_device(advertisment_data: AdvertisementData) -> bool:
        """Returns True if the device class supports the device identified by
        advertisement data."""
        device_name = (advertisment_data.local_name or "").strip()
        if device_name not in SUPPORTED_DEVICE_NAMES:
            return False
        for svc_uuid in SUPPORTED_DEVICE_SVC_UUIDS:
            if svc_uuid in advertisment_data.service_uuids:
                return True
        return False

    def _detect_command_profile(self) -> CommandProfile:
        """Detect the command profile for the connected device."""
        manufacturer = self._manufacturer.strip().upper()
        model_number = self._model_number.strip().upper()

        if manufacturer == "ARCTECH" and model_number in {"FOTH", "F0TH"}:
            return ARCTECH_FOTH_PROFILE

        return NITRAFLAME_PROFILE

    def disconnected_callback(self, client):  # pylint: disable=unused-argument
        """Handle disconnection events."""

        self._is_connected = False
        _LOGGER.warning("Disconnected from %s", self._mac)

    async def connect(self, retry_attempts=4) -> None:
        """Connect to the device."""

        if self._is_connected or self._connection_lock.locked():
            return

        async with self._connection_lock:
            try:
                _LOGGER.debug("Connecting to %s", self._mac)

                self._connection = await establish_connection(
                    client_class=BleakClient,
                    device=self._ble_device,
                    name=self._mac,
                    disconnected_callback=self.disconnected_callback,
                    max_attempts=retry_attempts,
                    use_services_cache=True,
                )

                self._is_connected = True

                self._model_number = await self._read_attr(
                    DeviceAttribute.MODEL_NUMBER
                )
                self._serial_number = await self._read_attr(
                    DeviceAttribute.SERIAL_NUMBER
                )
                self._manufacturer = await self._read_attr(
                    DeviceAttribute.MANUFACTURER
                )
                self._fw_revision = await self._read_attr(
                    DeviceAttribute.FW_REVISION
                )
                self._hw_revision = await self._read_attr(
                    DeviceAttribute.HW_REVISION
                )
                self._command_profile = self._detect_command_profile()
                self._state.accepts_short_ack_state = (
                    self._command_profile.accepts_short_ack_state
                )

                _LOGGER.info(
                    (
                        "Connected to device %s (Model: %s, Serial: %s, "
                        "Manufacturer: %s, FW rev: %s, HW rev: %s"
                    ),
                    self._mac,
                    self._model_number,
                    self._serial_number,
                    self._manufacturer,
                    self._fw_revision,
                    self._hw_revision,
                )

                # To interface with the device we first write a command and wait for an
                # asynchronous notification to be received on DEVICE_READ_ATTR_UUID.
                await self._connection.start_notify(
                    DeviceAttribute.CMD_RESPONSE.value, self._on_notify
                )
            except BleakError as ex:
                _LOGGER.error("Failed to connect to %s: %s", self._mac, ex)
                self._is_connected = False

    async def disconnect(self) -> None:
        """Disconnect the device."""
        if not self._is_connected:
            return

        await self._connection.disconnect()
        self._is_connected = False
        _LOGGER.debug("Disconnected from %s", self._mac)

    def update_ble_device(self, ble_device: BLEDevice) -> None:
        """Update the underlying BLE device reference."""
        self._ble_device = ble_device

    async def query_state(self) -> None:
        """Query the device state."""
        if not self._is_connected:
            await self.connect(retry_attempts=1)

        async with self._state_lock:
            self._state_updated.clear()
            await self._send_cmd(Command.QUERY_STATE.value)
            try:
                await asyncio.wait_for(
                    self._state_updated.wait(),
                    timeout=DEVICE_RESPONSE_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                _LOGGER.error(
                    "Timeout waiting for state response from %s", self._mac
                )
                pass

    def _on_notify(
        self, char: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Notification handler which updates the device state."""
        if self._state.update_from_bytes(data):
            self._state_updated.set()

    async def _read_attr(self, attr: DeviceAttribute) -> str:
        """Read a device attribute."""
        raw = await self._connection.read_gatt_char(attr.value)
        return raw.decode("utf-8", errors="ignore").strip("\x00")

    async def _send_cmd(self, cmd_bytes: bytes) -> None:
        """Send a command to the device."""
        await self._connection.write_gatt_char(
            DeviceAttribute.CMD_REQUEST.value, cmd_bytes, response=True
        )

    @property
    def is_connected(self) -> bool:
        """Return true if the device is connected."""
        return self._is_connected

    @property
    def name(self) -> str:
        """Return the advertised name of the connected device."""
        return self._name

    @property
    def mac(self) -> str:
        """Return the MAC address of the connected device."""
        return self._mac

    @property
    def model_number(self) -> str:
        """Return the model number of the connected device."""
        return self._model_number

    @property
    def serial_number(self) -> str:
        """Return the serial number of the connected device."""
        return self._serial_number

    @property
    def manufacturer(self) -> str:
        """Return the manufacturer of the connected device."""
        return self._manufacturer

    @property
    def firmware_revision(self) -> str:
        """Return the firmware revision of the connected device."""
        return self._fw_revision

    @property
    def hardware_revision(self) -> str:
        """Return the hardware revision of the connected device."""
        return self._hw_revision

    @property
    def is_powered_on(self) -> bool:
        """Return true if the device is powered on."""
        return self._state.is_powered_on

    async def set_powered_on(self, value: bool) -> None:
        """Set the device power state."""
        if not self._is_connected:
            await self.connect(retry_attempts=1)

        async with self._state_lock:
            profile = self._command_profile

            if profile.power_on is not None and profile.power_off is not None:
                self._state.is_powered_on = value
                await self._send_cmd(
                    profile.power_on if value else profile.power_off
                )
                return

            old_value = self._state.is_powered_on
            self._state.is_powered_on = value

            if old_value == value:
                return

            if profile.power_toggle is None:
                raise RuntimeError(
                    "Device profile does not define a power command"
                )

            await self._send_cmd(profile.power_toggle)

    @property
    def heat_mode(self) -> HeatMode:
        """Return the current heat mode."""
        return self._state.heat_mode

    def _change_heatmode_cmds(
        self, old_mode: HeatMode, new_mode: HeatMode
    ) -> list[Awaitable[None]]:
        """Construct the appropriate commands to transition between heat modes."""
        # Heat selection works in sequential steps as follows:
        # To go from off to low -> send SET_HEAT_LOW cmd (step up)
        # To go from low -> off -> send SET_HEAT_LOW cmd (step down)
        # To go from low -> high -> send SET_HEAT_HIGH cmd (step up)
        # To go from high -> low -> send SET_HEAT_HIGH cmd (step down)
        cmds: list[Awaitable[None]] = list()
        if old_mode == HeatMode.OFF:
            if new_mode == HeatMode.LOW:
                cmds.extend([self._send_cmd(Command.SET_HEAT_LOW.value)])
            elif new_mode == HeatMode.HIGH:
                cmds.extend(
                    [
                        self._send_cmd(Command.SET_HEAT_LOW.value),
                        self._send_cmd(Command.SET_HEAT_HIGH.value),
                    ]
                )
        elif old_mode == HeatMode.LOW:
            if new_mode == HeatMode.OFF:
                cmds.extend([self._send_cmd(Command.SET_HEAT_LOW.value)])
            elif new_mode == HeatMode.HIGH:
                cmds.extend([self._send_cmd(Command.SET_HEAT_HIGH.value)])
        elif old_mode == HeatMode.HIGH:
            if new_mode == HeatMode.LOW:
                cmds.extend([self._send_cmd(Command.SET_HEAT_HIGH.value)])
            elif new_mode == HeatMode.OFF:
                cmds.extend(
                    [
                        self._send_cmd(Command.SET_HEAT_HIGH.value),
                        self._send_cmd(Command.SET_HEAT_LOW.value),
                    ]
                )
        return cmds

    async def _set_heat_mode_with_explicit_commands(
        self, mode: HeatMode
    ) -> None:
        """Set heat mode using explicit heat on/off and level toggle commands."""
        old_value = self._state.heat_mode

        # Only send commands if the heat mode has changed.
        if old_value == mode:
            return

        profile = self._command_profile

        if mode == HeatMode.OFF:
            self._state.heat_mode = HeatMode.OFF
            await self._send_cmd(profile.heat_off)
            return

        if old_value == HeatMode.OFF:
            self._state.heat_mode = HeatMode.LOW
            await self._send_cmd(profile.heat_on)

        if mode == HeatMode.HIGH and self._state.heat_mode != HeatMode.HIGH:
            self._state.heat_mode = HeatMode.HIGH
            await self._send_cmd(profile.heat_toggle_level)
            return

        if mode == HeatMode.LOW and self._state.heat_mode == HeatMode.HIGH:
            self._state.heat_mode = HeatMode.LOW
            await self._send_cmd(profile.heat_toggle_level)

    @property
    def _has_explicit_heat_commands(self) -> bool:
        """Return true if the current profile has explicit heat commands."""
        profile = self._command_profile
        return (
            profile.heat_on is not None
            and profile.heat_off is not None
            and profile.heat_toggle_level is not None
        )

    async def set_heat_mode(self, mode: HeatMode) -> None:
        """Set the heat mode."""
        if not self._is_connected:
            await self.connect(retry_attempts=1)

        async with self._state_lock:
            if not self.is_powered_on and mode != HeatMode.OFF:
                # Cannot set heat mode if the device is powered off.
                _LOGGER.warning(
                    "Cannot set heat mode when device is powered off"
                )
                return

            if self._has_explicit_heat_commands:
                await self._set_heat_mode_with_explicit_commands(mode)
                return

            old_value = self._state.heat_mode
            self._state.heat_mode = mode

            # Only send commands if the heat mode has changed.
            if old_value == mode:
                return

            for cmd in self._change_heatmode_cmds(old_value, mode):
                await cmd

    @property
    def thermostat(self) -> int:
        """Return the current thermostat temperature."""
        return self._state.thermostat

    async def set_thermostat(self, temperature: int) -> None:
        """Set the thermostat temperature."""
        if not self._is_connected:
            await self.connect(retry_attempts=1)

        async with self._state_lock:
            old_value = self._state.thermostat
            self._state.set_thermostat(temperature)

            # Only send commands if the thermostat value has changed.
            if old_value == self._state.thermostat:
                return

            await self._send_cmd(
                Command.SET_THERMOSTAT.value + bytes([self._state.thermostat])
            )

    @property
    def flame_color(self) -> Color:
        """Return the current flame color."""
        return self._state.flame_color

    async def set_flame_color(self, color: Color) -> None:
        """Set the flame color."""
        if not self._is_connected:
            await self.connect(retry_attempts=1)

        async with self._state_lock:
            old_value = self._state.flame_color
            self._state.flame_color = color

            # Only send commands if the color has changed.
            if old_value == color:
                return

            await self._send_cmd(
                Command.SET_FLAME_COLOR.value
                + bytes([self._state.flame_color.value])
            )

    @property
    def fuel_color(self) -> Color:
        """Return the current fuel color."""
        return self._state.fuel_color

    async def set_fuel_color(self, color: Color) -> None:
        """Set the fuel color."""
        if not self._is_connected:
            await self.connect(retry_attempts=1)

        async with self._state_lock:
            old_value = self._state.fuel_color
            self._state.fuel_color = color

            # Only send commands if the color has changed.
            if old_value == color:
                return

            await self._send_cmd(
                Command.SET_FUEL_COLOR.value
                + bytes([self._state.fuel_color.value])
            )

    @property
    def flame_brightness(self) -> int:
        """Return the current flame brightness level."""
        return self._state.flame_brightness

    async def set_flame_brightness(self, brightness: int) -> None:
        """Set the flame brightness level."""
        if not self._is_connected:
            await self.connect(retry_attempts=1)

        async with self._state_lock:
            old_value = self._state.flame_brightness
            self._state.set_flame_brightness(brightness)

            # Only send commands if the brightness level has changed.
            if old_value == brightness:
                return

            while self._state.flame_brightness < old_value:
                await self._send_cmd(Command.FLAME_BRIGHTNESS_DEC.value)
                old_value -= 1

            while self._state.flame_brightness > old_value:
                await self._send_cmd(Command.FLAME_BRIGHTNESS_INC.value)
                old_value += 1

    @property
    def fuel_brightness(self) -> int:
        """Return the current fuel brightness level."""
        return self._state.fuel_brightness

    async def set_fuel_brightness(self, brightness: int) -> None:
        """Set the fuel brightness level."""
        if not self._is_connected:
            await self.connect(retry_attempts=1)

        async with self._state_lock:
            old_value = self._state.fuel_brightness
            self._state.set_fuel_brightness(brightness)

            # Only send commands if the brightness level has changed.
            if old_value == brightness:
                return

            while self._state.fuel_brightness < old_value:
                await self._send_cmd(Command.FUEL_BRIGHTNESS_DEC.value)
                old_value -= 1

            while self._state.fuel_brightness > old_value:
                await self._send_cmd(Command.FUEL_BRIGHTNESS_INC.value)
                old_value += 1
