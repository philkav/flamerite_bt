import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, call, patch

from attr import dataclass
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClient  # type: ignore
from bleak_retry_connector import establish_connection

from flamerite_bt.const import (
    ARCTECH_PROFILE,
    NITRAFLAME_PROFILE,
    THERMOSTAT_MAX,
    THERMOSTAT_MIN,
    Color,
    Command,
    DeviceAttribute,
    HeatMode,
)
from flamerite_bt.device import Device


class TestDevice(unittest.TestCase):
    def test_connect(self) -> None:
        ble_device = self._ble_device_mock()
        device = Device(ble_device)
        self.assertFalse(device.is_connected)
        self.assertEqual(device.mac, "00:11:22:33:44:55")
        self.assertEqual(device.name, "Flamerite Test Device")

        client_stub = self._bleak_client_stub()
        connect_stub = AsyncMock(
            spec=establish_connection, return_value=client_stub
        )
        with patch(
            "flamerite_bt.device.establish_connection", new=connect_stub
        ):

            async def run_connect():
                await device.connect()
                self.assertTrue(device.is_connected)
                self.assertEqual(device.model_number, "Test Model")
                self.assertEqual(device.serial_number, "Test Serial")
                self.assertEqual(device.manufacturer, "Test Manufacturer")
                self.assertEqual(device.firmware_revision, "Test FW Revision")
                self.assertEqual(device.hardware_revision, "Test HW Revision")
                await device.disconnect()
                self.assertFalse(device.is_connected)

            asyncio.run(run_connect())

    def test_query_state(self) -> None:
        ble_device = self._ble_device_mock()
        device = Device(ble_device)

        client_stub = self._bleak_client_stub()
        client_stub.write_gatt_char = AsyncMock()
        connect_stub = AsyncMock(
            spec=establish_connection, return_value=client_stub
        )
        with patch(
            "flamerite_bt.device.establish_connection", new=connect_stub
        ):

            async def run_query_state():
                # Calling query state without an active connection should automatically
                # trigger a connection.
                query_state_complete = device.query_state()

                # Simulate a notification being received after a short delay.
                device._on_notify(
                    Mock(spec=BleakGATTCharacteristic),
                    bytearray(
                        [0x20, 0x07, 0x0C, 0xA1, 0x00, 0x09, 0x09, 0x00, 0x18]
                    ),
                )

                # Wait for the query_state call to complete.
                await query_state_complete

                # Check updated device state.
                self.assertTrue(device.is_powered_on)
                self.assertEqual(device.heat_mode, HeatMode.LOW)
                self.assertEqual(device.thermostat, 16)
                self.assertEqual(device.flame_brightness, 1)
                self.assertEqual(device.fuel_brightness, 10)
                self.assertEqual(device.flame_color, Color.ORANGE_1)
                self.assertEqual(device.fuel_color, Color.CYCLE_ORANGE_ONLY)

    def test_set_powered_on(self) -> None:
        @dataclass
        class Spec:
            descr: str
            is_powered_on: bool
            new_powered_on: bool
            exp_commands: list[bytes]

        specs = [
            Spec(
                descr=(
                    "Send no commands when the requested power state is the same as "
                    "the current state"
                ),
                is_powered_on=True,
                new_powered_on=True,
                exp_commands=[],
            ),
            Spec(
                descr="OFF -> ON",
                is_powered_on=False,
                new_powered_on=True,
                exp_commands=[Command.POWER_TOGGLE.value],
            ),
            Spec(
                descr="ON -> OFF",
                is_powered_on=True,
                new_powered_on=False,
                exp_commands=[Command.POWER_TOGGLE.value],
            ),
        ]
        for spec in specs:
            with self.subTest(spec.descr):
                ble_device = self._ble_device_mock()
                device = Device(ble_device)

                client_stub = self._bleak_client_stub()
                client_stub.write_gatt_char = AsyncMock()
                connect_stub = AsyncMock(
                    spec=establish_connection, return_value=client_stub
                )
                with patch(
                    "flamerite_bt.device.establish_connection", new=connect_stub
                ):

                    async def run_set_powered_on():
                        if spec.is_powered_on:
                            device._state.is_powered_on = True
                        await device.set_powered_on(spec.new_powered_on)
                        self.assertEqual(
                            device.is_powered_on, spec.new_powered_on
                        )

                    asyncio.run(run_set_powered_on())
                    client_stub.write_gatt_char.assert_has_awaits(
                        [
                            call(
                                DeviceAttribute.CMD_REQUEST.value,
                                cmd,
                                response=True,
                            )
                            for cmd in spec.exp_commands
                        ],
                    )

    def test_set_powered_on_arctech_profile(self) -> None:
        """ARCTECH devices use explicit power on/off commands."""

        @dataclass
        class Spec:
            descr: str
            is_powered_on: bool
            new_powered_on: bool
            exp_commands: list[bytes]

        specs = [
            Spec(
                descr="OFF -> ON",
                is_powered_on=False,
                new_powered_on=True,
                exp_commands=[bytes.fromhex("a101ff")],
            ),
            Spec(
                descr="ON -> OFF",
                is_powered_on=True,
                new_powered_on=False,
                exp_commands=[bytes.fromhex("a10100")],
            ),
            Spec(
                descr="Send ON command even when already ON",
                is_powered_on=True,
                new_powered_on=True,
                exp_commands=[bytes.fromhex("a101ff")],
            ),
            Spec(
                descr="Send OFF command even when already OFF",
                is_powered_on=False,
                new_powered_on=False,
                exp_commands=[bytes.fromhex("a10100")],
            ),
        ]

        for spec in specs:
            with self.subTest(spec.descr):
                ble_device = self._ble_device_mock()
                device = Device(ble_device)
                device._command_profile = ARCTECH_PROFILE

                client_stub = self._bleak_client_stub()
                client_stub.write_gatt_char = AsyncMock()

                device._connection = client_stub
                device._is_connected = True

                async def run_set_powered_on():
                    device._state.is_powered_on = spec.is_powered_on
                    await device.set_powered_on(spec.new_powered_on)
                    self.assertEqual(device.is_powered_on, spec.new_powered_on)

                asyncio.run(run_set_powered_on())

                client_stub.write_gatt_char.assert_has_awaits(
                    [
                        call(
                            DeviceAttribute.CMD_REQUEST.value,
                            cmd,
                            response=True,
                        )
                        for cmd in spec.exp_commands
                    ],
                )

    def test_set_heat_mode_arctech_profile_uses_current_thermostat(
        self,
    ) -> None:
        """ARCTECH heat on sends the current thermostat after enabling heat."""
        ble_device = self._ble_device_mock()
        device = Device(ble_device)
        device._command_profile = ARCTECH_PROFILE
        device._state.is_powered_on = True
        device._state.heat_mode = HeatMode.OFF
        device._state.thermostat = THERMOSTAT_MAX

        client_stub = self._bleak_client_stub()
        client_stub.write_gatt_char = AsyncMock()

        device._connection = client_stub
        device._is_connected = True

        async def run_set_heat_mode():
            await device.set_heat_mode(HeatMode.LOW)
            self.assertEqual(device.heat_mode, HeatMode.LOW)

        asyncio.run(run_set_heat_mode())

        client_stub.write_gatt_char.assert_has_awaits(
            [
                call(
                    DeviceAttribute.CMD_REQUEST.value,
                    ARCTECH_PROFILE.heat_on,
                    response=True,
                ),
                call(
                    DeviceAttribute.CMD_REQUEST.value,
                    Command.SET_THERMOSTAT.value + bytes([THERMOSTAT_MAX]),
                    response=True,
                ),
            ],
        )

    def test_set_heat_mode_arctech_profile(self) -> None:
        """ARCTECH devices use explicit heat on/off and level toggle commands."""

        @dataclass
        class Spec:
            descr: str
            current_mode: HeatMode
            new_mode: HeatMode
            exp_mode: HeatMode
            exp_commands: list[bytes]

        specs = [
            Spec(
                descr="OFF -> LOW",
                current_mode=HeatMode.OFF,
                new_mode=HeatMode.LOW,
                exp_mode=HeatMode.LOW,
                exp_commands=[
                    ARCTECH_PROFILE.heat_on,
                    Command.SET_THERMOSTAT.value + bytes([THERMOSTAT_MIN]),
                ],
            ),
            Spec(
                descr="OFF -> HIGH",
                current_mode=HeatMode.OFF,
                new_mode=HeatMode.HIGH,
                exp_mode=HeatMode.HIGH,
                exp_commands=[
                    ARCTECH_PROFILE.heat_on,
                    Command.SET_THERMOSTAT.value + bytes([THERMOSTAT_MIN]),
                    ARCTECH_PROFILE.heat_toggle_level,
                ],
            ),
            Spec(
                descr="LOW -> HIGH",
                current_mode=HeatMode.LOW,
                new_mode=HeatMode.HIGH,
                exp_mode=HeatMode.HIGH,
                exp_commands=[ARCTECH_PROFILE.heat_toggle_level],
            ),
            Spec(
                descr="HIGH -> LOW",
                current_mode=HeatMode.HIGH,
                new_mode=HeatMode.LOW,
                exp_mode=HeatMode.LOW,
                exp_commands=[ARCTECH_PROFILE.heat_toggle_level],
            ),
            Spec(
                descr="LOW -> OFF",
                current_mode=HeatMode.LOW,
                new_mode=HeatMode.OFF,
                exp_mode=HeatMode.OFF,
                exp_commands=[ARCTECH_PROFILE.heat_off],
            ),
            Spec(
                descr="HIGH -> OFF",
                current_mode=HeatMode.HIGH,
                new_mode=HeatMode.OFF,
                exp_mode=HeatMode.OFF,
                exp_commands=[ARCTECH_PROFILE.heat_off],
            ),
            Spec(
                descr="LOW -> LOW",
                current_mode=HeatMode.LOW,
                new_mode=HeatMode.LOW,
                exp_mode=HeatMode.LOW,
                exp_commands=[],
            ),
        ]

        for spec in specs:
            with self.subTest(spec.descr):
                ble_device = self._ble_device_mock()
                device = Device(ble_device)
                device._command_profile = ARCTECH_PROFILE
                device._state.is_powered_on = True
                device._state.heat_mode = spec.current_mode

                client_stub = self._bleak_client_stub()
                client_stub.write_gatt_char = AsyncMock()

                device._connection = client_stub
                device._is_connected = True

                async def run_set_heat_mode():
                    await device.set_heat_mode(spec.new_mode)
                    self.assertEqual(device.heat_mode, spec.exp_mode)

                asyncio.run(run_set_heat_mode())

                client_stub.write_gatt_char.assert_has_awaits(
                    [
                        call(
                            DeviceAttribute.CMD_REQUEST.value,
                            cmd,
                            response=True,
                        )
                        for cmd in spec.exp_commands
                    ],
                )

    def test_set_heat_mode(self) -> None:
        @dataclass
        class Spec:
            descr: str
            is_powered_on: bool
            cur_heat_mode: HeatMode
            new_heat_mode: HeatMode
            exp_heat_mode: HeatMode
            exp_commands: list[bytes]

        specs = [
            Spec(
                descr="Ignore heat change requests when device is powered off",
                is_powered_on=False,
                cur_heat_mode=HeatMode.OFF,
                new_heat_mode=HeatMode.HIGH,
                exp_heat_mode=HeatMode.OFF,
                exp_commands=[],
            ),
            Spec(
                descr=(
                    "Send no commands when the requested mode is the same as "
                    "the current mode"
                ),
                is_powered_on=True,
                cur_heat_mode=HeatMode.LOW,
                new_heat_mode=HeatMode.LOW,
                exp_heat_mode=HeatMode.LOW,
                exp_commands=[],
            ),
            Spec(
                descr="OFF -> LOW",
                is_powered_on=True,
                cur_heat_mode=HeatMode.OFF,
                new_heat_mode=HeatMode.LOW,
                exp_heat_mode=HeatMode.LOW,
                exp_commands=[Command.SET_HEAT_LOW.value],
            ),
            Spec(
                descr="LOW -> OFF",
                is_powered_on=True,
                cur_heat_mode=HeatMode.LOW,
                new_heat_mode=HeatMode.OFF,
                exp_heat_mode=HeatMode.OFF,
                # Sending LOW when already in LOW turns off heat.
                exp_commands=[Command.SET_HEAT_LOW.value],
            ),
            Spec(
                descr="LOW -> HIGH",
                is_powered_on=True,
                cur_heat_mode=HeatMode.LOW,
                new_heat_mode=HeatMode.HIGH,
                exp_heat_mode=HeatMode.HIGH,
                exp_commands=[Command.SET_HEAT_HIGH.value],
            ),
            Spec(
                descr="OFF -> HIGH",
                is_powered_on=True,
                cur_heat_mode=HeatMode.OFF,
                new_heat_mode=HeatMode.HIGH,
                exp_heat_mode=HeatMode.HIGH,
                exp_commands=[
                    Command.SET_HEAT_LOW.value,
                    Command.SET_HEAT_HIGH.value,
                ],
            ),
            Spec(
                descr="HIGH -> LOW",
                is_powered_on=True,
                cur_heat_mode=HeatMode.HIGH,
                new_heat_mode=HeatMode.LOW,
                exp_heat_mode=HeatMode.LOW,
                # Sending HIGH when in HIGH switches to LOW.
                exp_commands=[Command.SET_HEAT_HIGH.value],
            ),
            Spec(
                descr="HIGH -> OFF",
                is_powered_on=True,
                cur_heat_mode=HeatMode.HIGH,
                new_heat_mode=HeatMode.OFF,
                exp_heat_mode=HeatMode.OFF,
                # Sending HIGH when in HIGH switches to LOW;
                # then send another LOW to turn off.
                exp_commands=[
                    Command.SET_HEAT_HIGH.value,
                    Command.SET_HEAT_LOW.value,
                ],
            ),
        ]

        for spec in specs:
            with self.subTest(spec.descr):
                ble_device = self._ble_device_mock()
                device = Device(ble_device)

                client_stub = self._bleak_client_stub()
                client_stub.write_gatt_char = AsyncMock()
                connect_stub = AsyncMock(
                    spec=establish_connection, return_value=client_stub
                )
                with patch(
                    "flamerite_bt.device.establish_connection", new=connect_stub
                ):

                    async def run_set_heat_mode():
                        if spec.is_powered_on:
                            device._state.is_powered_on = True
                        device._state.heat_mode = spec.cur_heat_mode
                        await device.set_heat_mode(spec.new_heat_mode)
                        self.assertEqual(device.heat_mode, spec.exp_heat_mode)

                    asyncio.run(run_set_heat_mode())
                    client_stub.write_gatt_char.assert_has_awaits(
                        [
                            call(
                                DeviceAttribute.CMD_REQUEST.value,
                                cmd,
                                response=True,
                            )
                            for cmd in spec.exp_commands
                        ],
                    )

    def test_set_flame_color(self) -> None:
        for color in Color:
            with self.subTest(f"Set flame color to {color}"):
                ble_device = self._ble_device_mock()
                device = Device(ble_device)

                client_stub = self._bleak_client_stub()
                client_stub.write_gatt_char = AsyncMock()
                connect_stub = AsyncMock(
                    spec=establish_connection, return_value=client_stub
                )
                with patch(
                    "flamerite_bt.device.establish_connection", new=connect_stub
                ):
                    expCalls = [
                        call(
                            DeviceAttribute.CMD_REQUEST.value,
                            Command.SET_FLAME_COLOR.value
                            + bytes([color.value]),
                            response=True,
                        )
                    ]

                    # No commands expected when the color is not being changed.
                    if device.flame_color == color:
                        expCalls = []

                    async def run_set_color():
                        await device.set_flame_color(color)
                        self.assertEqual(device.flame_color, color)

                    asyncio.run(run_set_color())
                    client_stub.write_gatt_char.assert_has_awaits(expCalls)

    def test_set_fuel_color(self) -> None:
        for color in Color:
            with self.subTest(f"Set fuel color to {color}"):
                ble_device = self._ble_device_mock()
                device = Device(ble_device)

                client_stub = self._bleak_client_stub()
                client_stub.write_gatt_char = AsyncMock()
                connect_stub = AsyncMock(
                    spec=establish_connection, return_value=client_stub
                )
                with patch(
                    "flamerite_bt.device.establish_connection", new=connect_stub
                ):
                    expCalls = [
                        call(
                            DeviceAttribute.CMD_REQUEST.value,
                            Command.SET_FUEL_COLOR.value + bytes([color.value]),
                            response=True,
                        )
                    ]

                    # No commands expected when the color is not being changed.
                    if device.flame_color == color:
                        expCalls = []

                    async def run_set_color():
                        await device.set_fuel_color(color)
                        self.assertEqual(device.fuel_color, color)

                    asyncio.run(run_set_color())
                    client_stub.write_gatt_char.assert_has_awaits(expCalls)

    def test_set_flame_brightness(self) -> None:
        @dataclass
        class Spec:
            descr: str
            cur_brightness: int
            new_brightness: int
            exp_commands: list[bytes]

        specs = [
            Spec(
                descr=(
                    "Send no commands when the requested brightness is the "
                    "same as the current brightness"
                ),
                cur_brightness=5,
                new_brightness=5,
                exp_commands=[],
            ),
            Spec(
                descr="Increase brightness from 1 to 2",
                cur_brightness=1,
                new_brightness=2,
                exp_commands=[
                    Command.FLAME_BRIGHTNESS_INC.value,
                ],
            ),
            Spec(
                descr="Increase brightness from 5 to 10",
                cur_brightness=5,
                new_brightness=10,
                exp_commands=[
                    Command.FLAME_BRIGHTNESS_INC.value,
                    Command.FLAME_BRIGHTNESS_INC.value,
                    Command.FLAME_BRIGHTNESS_INC.value,
                    Command.FLAME_BRIGHTNESS_INC.value,
                    Command.FLAME_BRIGHTNESS_INC.value,
                ],
            ),
            Spec(
                descr="Decrease brightness from 2 to 1",
                cur_brightness=2,
                new_brightness=1,
                exp_commands=[
                    Command.FLAME_BRIGHTNESS_DEC.value,
                ],
            ),
            Spec(
                descr="Decrease brightness from 8 to 5",
                cur_brightness=8,
                new_brightness=5,
                exp_commands=[
                    Command.FLAME_BRIGHTNESS_DEC.value,
                    Command.FLAME_BRIGHTNESS_DEC.value,
                    Command.FLAME_BRIGHTNESS_DEC.value,
                ],
            ),
        ]

        for spec in specs:
            with self.subTest(spec.descr):
                ble_device = self._ble_device_mock()
                device = Device(ble_device)

                client_stub = self._bleak_client_stub()
                client_stub.write_gatt_char = AsyncMock()
                connect_stub = AsyncMock(
                    spec=establish_connection, return_value=client_stub
                )
                with patch(
                    "flamerite_bt.device.establish_connection", new=connect_stub
                ):

                    async def run_set_brightness():
                        device._state.flame_brightness = spec.cur_brightness
                        await device.set_flame_brightness(spec.new_brightness)
                        self.assertEqual(
                            device.flame_brightness, spec.new_brightness
                        )

                    asyncio.run(run_set_brightness())

                    expCalls = [
                        call(
                            DeviceAttribute.CMD_REQUEST.value,
                            cmd,
                            response=True,
                        )
                        for cmd in spec.exp_commands
                    ]

                    client_stub.write_gatt_char.assert_has_awaits(expCalls)

    def test_set_fuel_brightness(self) -> None:
        @dataclass
        class Spec:
            descr: str
            cur_brightness: int
            new_brightness: int
            exp_commands: list[bytes]

        specs = [
            Spec(
                descr=(
                    "Send no commands when the requested brightness is the same "
                    "as the current brightness"
                ),
                cur_brightness=5,
                new_brightness=5,
                exp_commands=[],
            ),
            Spec(
                descr="Increase brightness from 1 to 2",
                cur_brightness=1,
                new_brightness=2,
                exp_commands=[
                    Command.FUEL_BRIGHTNESS_INC.value,
                ],
            ),
            Spec(
                descr="Increase brightness from 5 to 10",
                cur_brightness=5,
                new_brightness=10,
                exp_commands=[
                    Command.FUEL_BRIGHTNESS_INC.value,
                    Command.FUEL_BRIGHTNESS_INC.value,
                    Command.FUEL_BRIGHTNESS_INC.value,
                    Command.FUEL_BRIGHTNESS_INC.value,
                    Command.FUEL_BRIGHTNESS_INC.value,
                ],
            ),
            Spec(
                descr="Decrease brightness from 2 to 1",
                cur_brightness=2,
                new_brightness=1,
                exp_commands=[
                    Command.FUEL_BRIGHTNESS_DEC.value,
                ],
            ),
            Spec(
                descr="Decrease brightness from 8 to 5",
                cur_brightness=8,
                new_brightness=5,
                exp_commands=[
                    Command.FUEL_BRIGHTNESS_DEC.value,
                    Command.FUEL_BRIGHTNESS_DEC.value,
                    Command.FUEL_BRIGHTNESS_DEC.value,
                ],
            ),
        ]

        for spec in specs:
            with self.subTest(spec.descr):
                ble_device = self._ble_device_mock()
                device = Device(ble_device)

                client_stub = self._bleak_client_stub()
                client_stub.write_gatt_char = AsyncMock()
                connect_stub = AsyncMock(
                    spec=establish_connection, return_value=client_stub
                )
                with patch(
                    "flamerite_bt.device.establish_connection", new=connect_stub
                ):

                    async def run_set_brightness():
                        device._state.fuel_brightness = spec.cur_brightness
                        await device.set_fuel_brightness(spec.new_brightness)
                        self.assertEqual(
                            device.fuel_brightness, spec.new_brightness
                        )

                    asyncio.run(run_set_brightness())

                    expCalls = [
                        call(
                            DeviceAttribute.CMD_REQUEST.value,
                            cmd,
                            response=True,
                        )
                        for cmd in spec.exp_commands
                    ]

                    client_stub.write_gatt_char.assert_has_awaits(expCalls)

    def test_set_thermostat(self) -> None:
        @dataclass
        class Spec:
            descr: str
            cur_value: int
            new_value: int
            exp_commands: list[bytes]

        specs = [
            Spec(
                descr=(
                    "Send no commands when the requested value is the same "
                    "as the current value"
                ),
                cur_value=THERMOSTAT_MIN,
                new_value=THERMOSTAT_MIN,
                exp_commands=[],
            ),
            Spec(
                descr="Adjust thermostat value",
                cur_value=THERMOSTAT_MIN,
                new_value=THERMOSTAT_MAX,
                exp_commands=[
                    Command.SET_THERMOSTAT.value + bytes([THERMOSTAT_MAX]),
                ],
            ),
        ]

        for spec in specs:
            with self.subTest(spec.descr):
                ble_device = self._ble_device_mock()
                device = Device(ble_device)

                client_stub = self._bleak_client_stub()
                client_stub.write_gatt_char = AsyncMock()
                connect_stub = AsyncMock(
                    spec=establish_connection, return_value=client_stub
                )
                with patch(
                    "flamerite_bt.device.establish_connection", new=connect_stub
                ):

                    async def run_set_thermostat():
                        device._state.thermostat = spec.cur_value
                        await device.set_thermostat(spec.new_value)
                        self.assertEqual(device.thermostat, spec.new_value)

                    asyncio.run(run_set_thermostat())

                    expCalls = [
                        call(
                            DeviceAttribute.CMD_REQUEST.value,
                            cmd,
                            response=True,
                        )
                        for cmd in spec.exp_commands
                    ]

                    client_stub.write_gatt_char.assert_has_awaits(expCalls)

    def test_detect_command_profile_arctech(self) -> None:
        """ARCTECH devices use the ARCTECH command profile."""
        device = Device(self._ble_device_mock())
        device._manufacturer = "ARCTECH"
        device._model_number = "FOTH"

        self.assertEqual(device._detect_command_profile(), ARCTECH_PROFILE)

    def test_detect_command_profile_default(self) -> None:
        """Non-ARCTECH devices use the NITRAFlame command profile."""
        device = Device(self._ble_device_mock())
        device._manufacturer = "Test Manufacturer"
        device._model_number = "Test Model"

        self.assertEqual(device._detect_command_profile(), NITRAFLAME_PROFILE)

    def _ble_device_mock(self) -> BLEDevice:
        """Create a mock BLE device for use in tests."""
        return BLEDevice(
            address="00:11:22:33:44:55",
            name="Flamerite Test Device",
            details={},
        )

    def _bleak_client_stub(self) -> AsyncMock:
        """Create a minimal mock BleakClient for use in tests."""
        client_stub = AsyncMock(spec=BleakClient)
        client_stub.read_gatt_char = AsyncMock(
            side_effect=self._read_attr_side_effect
        )
        client_stub.start_notify = AsyncMock()
        client_stub.disconnect = AsyncMock()
        return client_stub

    def _read_attr_side_effect(self, uuid: str) -> bytes:
        """Side effect function for mocking read_gatt_char."""
        responses = {
            DeviceAttribute.MODEL_NUMBER.value: b"Test Model",
            DeviceAttribute.SERIAL_NUMBER.value: b"Test Serial",
            DeviceAttribute.MANUFACTURER.value: b"Test Manufacturer",
            DeviceAttribute.FW_REVISION.value: b"Test FW Revision",
            DeviceAttribute.HW_REVISION.value: b"Test HW Revision",
        }

        return responses.get(uuid, bytes([0x00]))
