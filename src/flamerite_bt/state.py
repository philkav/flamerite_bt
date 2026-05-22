"""Flamerite state parsing logic."""

from .const import (
    BRIGHTNESS_MAX,
    BRIGHTNESS_MIN,
    COLOR_MAX,
    COLOR_MIN,
    THERMOSTAT_MAX,
    THERMOSTAT_MIN,
    Color,
    HeatMode,
)


class State:
    """Representation of the Flamerite device state."""

    is_powered_on: bool
    heat_mode: HeatMode
    thermostat: int
    flame_color: Color
    fuel_color: Color
    flame_brightness: int
    fuel_brightness: int
    accepts_short_ack_state: bool

    def __init__(self, accepts_short_ack_state: bool = False) -> None:
        self.is_powered_on = False
        self.heat_mode = HeatMode.OFF
        self.thermostat = THERMOSTAT_MIN
        self.flame_color = Color.ORANGE_1
        self.fuel_color = Color.ORANGE_1
        self.flame_brightness = BRIGHTNESS_MIN
        self.fuel_brightness = BRIGHTNESS_MIN
        self.accepts_short_ack_state = accepts_short_ack_state

    def update_from_bytes(self, data: bytearray) -> bool:
        """Update state from raw byte data read from the device.
        Returns True if the update was successful."""

        # All async responses have the following structure:
        # --------------
        # [0] space (0x20)
        # [1] payload length in bytes
        # [...] response payload; variable
        if len(data) < 2 or data[0] != 0x20:
            return False

        # We only care about QUERY_STATE responses (cmd: a1010a) which always contain
        # exactly 7 bytes.
        exp_res_payload_len = 7
        state_payload = data[2:]

        if len(state_payload) == 2 and self.accepts_short_ack_state:
            return True

        if len(state_payload) != exp_res_payload_len:
            return False

        # Response payload has the following structure:
        # [0] device state (0x0A: off; 0x0B: on - no heat,
        #     0x0C: ON - low heat, 0x0d: ON - high heat)
        # [1] unknown
        # [2] thermostat temperature offset (0 to 15); add 16 to convert to the
        #     actual thermostat value
        # [3] flame brightness (0 to 9)
        # [4] fuel brightness (0 to 9)
        # [5] flame color
        # [6] fuel color
        self.is_powered_on = int(state_payload[0]) > 0x0A
        self.heat_mode = (
            HeatMode(int(state_payload[0]))
            if self.is_powered_on
            else HeatMode.OFF
        )
        self.thermostat = clamp(
            int(state_payload[2]) + 16, THERMOSTAT_MIN, THERMOSTAT_MAX
        )
        self.flame_brightness = clamp(
            1 + int(state_payload[3]), BRIGHTNESS_MIN, BRIGHTNESS_MAX
        )
        self.fuel_brightness = clamp(
            1 + int(state_payload[4]), BRIGHTNESS_MIN, BRIGHTNESS_MAX
        )
        self.flame_color = Color(
            clamp(int(state_payload[5]), COLOR_MIN, COLOR_MAX)
        )
        self.fuel_color = Color(
            clamp(int(state_payload[6]), COLOR_MIN, COLOR_MAX)
        )
        return True

    def set_thermostat(self, temperature_celsius: int) -> None:
        """Set the thermostat temperature in Celsius."""
        self.thermostat = clamp(
            temperature_celsius, THERMOSTAT_MIN, THERMOSTAT_MAX
        )

    def set_fuel_brightness(self, brightness: int) -> None:
        """Set the fuel brightness level (1-10)."""
        self.fuel_brightness = clamp(brightness, BRIGHTNESS_MIN, BRIGHTNESS_MAX)

    def set_flame_brightness(self, brightness: int) -> None:
        """Set the flame brightness level (1-10)."""
        self.flame_brightness = clamp(
            brightness, BRIGHTNESS_MIN, BRIGHTNESS_MAX
        )

    def __str__(self):
        return (
            f"Status: {'ON' if self.is_powered_on else 'OFF'}, "
            f"Heat Mode: {self.heat_mode}, "
            f"Thermostat: {self.thermostat}C, "
            f"Flame Brightness: {self.flame_brightness}, "
            f"Flame Color: {self.flame_color}, "
            f"Fuel Brightness: {self.fuel_brightness}, "
            f"Fuel Color: {self.fuel_color}"
        )


def clamp(value: int, min_value: int, max_value: int) -> int:
    """Clamp an integer value between min_value and max_value (inclusive)."""
    return max(min_value, min(value, max_value))
