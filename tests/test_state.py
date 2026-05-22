import unittest
from dataclasses import dataclass

from flamerite_bt.const import BRIGHTNESS_MIN, THERMOSTAT_MIN, Color, HeatMode
from flamerite_bt.state import State


class TestState(unittest.TestCase):
    def test_state_initialization(self) -> None:
        state = State()
        self.assertEqual(state.is_powered_on, False)
        self.assertEqual(state.heat_mode, HeatMode.OFF)
        self.assertEqual(state.thermostat, THERMOSTAT_MIN)
        self.assertEqual(state.flame_color, Color.ORANGE_1)
        self.assertEqual(state.fuel_color, Color.ORANGE_1)
        self.assertEqual(state.flame_brightness, BRIGHTNESS_MIN)
        self.assertEqual(state.fuel_brightness, BRIGHTNESS_MIN)
        self.assertEqual(state.thermostat, THERMOSTAT_MIN)

    def test_state_successful_update(self) -> None:
        @dataclass
        class ExpectedState:
            """Expected state representation for testing purposes."""

            is_powered_on: bool
            heat_mode: HeatMode
            thermostat: int
            flame_color: Color
            fuel_color: Color
            flame_brightness: int
            fuel_brightness: int

        @dataclass
        class Spec:
            descr: str
            data: bytearray
            expected: ExpectedState

        specs = [
            Spec(
                descr=(
                    "Power OFF, No Heat, Thermostat 16, Flame Brightness 1, "
                    "Fuel Brightness 10, Cycle Variation 1 for Flame Color, "
                    "Cycle variation 5 for Fuel Color"
                ),
                data=bytearray(
                    [0x20, 0x07, 0x0A, 0xA1, 0x00, 0x00, 0x09, 0x14, 0x18]
                ),
                expected=ExpectedState(
                    is_powered_on=False,
                    heat_mode=HeatMode.OFF,
                    thermostat=16,
                    flame_brightness=1,
                    fuel_brightness=10,
                    flame_color=Color.CYCLE_1,
                    fuel_color=Color.CYCLE_ORANGE_ONLY,
                ),
            ),
            Spec(
                descr=(
                    "Power ON, No Heat, Thermostat 16, Flame Brightness 1,"
                    "Fuel Brightness 10, Cycle Variation 1 for Flame Color, "
                    "Cycle variation 5 for Fuel Color"
                ),
                data=bytearray(
                    [0x20, 0x07, 0x0B, 0xA1, 0x00, 0x00, 0x09, 0x14, 0x18]
                ),
                expected=ExpectedState(
                    is_powered_on=True,
                    heat_mode=HeatMode.OFF,
                    thermostat=16,
                    flame_brightness=1,
                    fuel_brightness=10,
                    flame_color=Color.CYCLE_1,
                    fuel_color=Color.CYCLE_ORANGE_ONLY,
                ),
            ),
            Spec(
                descr=(
                    "Power ON, Low Heat, Thermostat 22, Flame Brightness 6, "
                    "Fuel Brightness 4, Flame Color 2, Fuel Color 1"
                ),
                data=bytearray(
                    [0x20, 0x07, 0x0C, 0xA1, 0x06, 0x05, 0x03, 0x02, 0x01]
                ),
                expected=ExpectedState(
                    is_powered_on=True,
                    heat_mode=HeatMode.LOW,
                    thermostat=22,
                    flame_brightness=6,
                    fuel_brightness=4,
                    flame_color=Color.ORANGE_3,
                    fuel_color=Color.ORANGE_2,
                ),
            ),
            Spec(
                descr=(
                    "Power ON, High Heat, Thermostat 22, Flame Brightness 6, "
                    "Fuel Brightness 4, Flame Color 2, Fuel Color 1"
                ),
                data=bytearray(
                    [0x20, 0x07, 0x0D, 0xA1, 0x06, 0x05, 0x03, 0x02, 0x01]
                ),
                expected=ExpectedState(
                    is_powered_on=True,
                    heat_mode=HeatMode.HIGH,
                    thermostat=22,
                    flame_brightness=6,
                    fuel_brightness=4,
                    flame_color=Color.ORANGE_3,
                    fuel_color=Color.ORANGE_2,
                ),
            ),
        ]

        for spec in specs:
            with self.subTest(spec.descr):
                state = State()
                result = state.update_from_bytes(spec.data)
                self.assertTrue(result)
                self.assertEqual(
                    state.is_powered_on, spec.expected.is_powered_on
                )
                self.assertEqual(state.heat_mode, spec.expected.heat_mode)
                self.assertEqual(state.thermostat, spec.expected.thermostat)
                self.assertEqual(
                    state.flame_brightness, spec.expected.flame_brightness
                )
                self.assertEqual(
                    state.fuel_brightness, spec.expected.fuel_brightness
                )
                self.assertEqual(state.flame_color, spec.expected.flame_color)
                self.assertEqual(state.fuel_color, spec.expected.fuel_color)

    def test_state_bad_response_handling(self) -> None:
        @dataclass
        class Spec:
            descr: str
            data: bytearray

        specs = [
            Spec(
                descr="Response too short",
                data=bytearray([0x20]),
            ),
            Spec(
                descr="Incorrect response type",
                data=bytearray(
                    [0x21, 0x07, 0x0B, 0xA1, 0x00, 0x00, 0x09, 0x14, 0x18]
                ),
            ),
            Spec(
                descr="Incorrect payload length",
                data=bytearray(
                    [0x20, 0x06, 0x0B, 0xA1, 0x00, 0x00, 0x09, 0x14]
                ),
            ),
        ]

        for spec in specs:
            with self.subTest(spec.descr):
                state = State()
                result = state.update_from_bytes(spec.data)
                self.assertFalse(result)

    def test_state_short_ack_response_handling(self) -> None:
        """Short ACK frames are only accepted when enabled."""
        data = bytearray(b" \x02\n\xa1")

        state = State()
        self.assertFalse(state.update_from_bytes(data))

        state = State(accepts_short_ack_state=True)
        self.assertTrue(state.update_from_bytes(data))
