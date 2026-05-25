"""Constants for the Flamerite Bluetooth integration."""

from dataclasses import dataclass
from enum import Enum, IntEnum

# The maximum time to wait for a response from the device when querying its state.
DEVICE_RESPONSE_TIMEOUT_SECONDS = 5

SUPPORTED_DEVICE_NAMES = ["NITRAFlame", "Flamerite"]
SUPPORTED_DEVICE_SVC_UUIDS = ["0000fff0-0000-1000-8000-00805f9b34fb"]


class DeviceAttribute(Enum):
    """Device attributes that can be queried."""

    # Read-only
    MODEL_NUMBER = "00002a24-0000-1000-8000-00805f9b34fb"
    SERIAL_NUMBER = "00002a25-0000-1000-8000-00805f9b34fb"
    FW_REVISION = "00002a26-0000-1000-8000-00805f9b34fb"
    HW_REVISION = "00002a27-0000-1000-8000-00805f9b34fb"
    MANUFACTURER = "00002a29-0000-1000-8000-00805f9b34fb"

    # Readable via subscribing to a notification callback.
    CMD_RESPONSE = "0000fff1-0000-1000-8000-00805f9b34fb"
    # Writeable
    CMD_REQUEST = "0000fff2-0000-1000-8000-00805f9b34fb"


class Color(IntEnum):
    """Available flame and bed colors.

    The devices support 5 color palettes. Each color has 4 variations
    (e.g., ORANGE_1 to ORANGE_4) with increasing intensity. In addition,
    there are 5 CYCLE modes that cycle through all colors with
    CYCLE_ORANGE_ONLY cycling only between orange hues."""

    ORANGE_1 = 0x00
    ORANGE_2 = 0x01
    ORANGE_3 = 0x02
    ORANGE_4 = 0x03
    RED_1 = 0x04
    RED_2 = 0x05
    RED_3 = 0x06
    RED_4 = 0x07
    GREEN_1 = 0x08
    GREEN_2 = 0x09
    GREEN_3 = 0x0A
    GREEN_4 = 0x0B
    BLUE_1 = 0x0C
    BLUE_2 = 0x0D
    BLUE_3 = 0x0E
    BLUE_4 = 0x0F
    WHITE_1 = 0x10
    WHITE_2 = 0x11
    WHITE_3 = 0x12
    WHITE_4 = 0x13

    CYCLE_1 = 0x14
    CYCLE_2 = 0x15
    CYCLE_3 = 0x16
    CYCLE_4 = 0x17
    CYCLE_ORANGE_ONLY = 0x18

    def __str__(self):
        tokens = self.name.split("_")
        if self in [
            Color.CYCLE_1,
            Color.CYCLE_1,
            Color.CYCLE_2,
            Color.CYCLE_3,
            Color.CYCLE_4,
        ]:
            return f"Cycle colors (variation {tokens[1]})"
        if self is Color.CYCLE_ORANGE_ONLY:
            return "Cycle colors (orange hues)"

        palette = tokens[0].capitalize()
        return f"{palette} (hue {tokens[1]})"


class HeatMode(IntEnum):
    """Available heat modes for the Flamerite device."""

    OFF = 0x0B
    LOW = 0x0C
    HIGH = 0x0D

    def __str__(self) -> str:
        return str(self.name.capitalize)


# Valid ranges for device-reported values.
THERMOSTAT_MIN = 16
THERMOSTAT_MAX = 31
BRIGHTNESS_MIN = 1
BRIGHTNESS_MAX = 10
COLOR_MIN = Color.ORANGE_1.value
COLOR_MAX = Color.CYCLE_ORANGE_ONLY.value


@dataclass(frozen=True)
class CommandProfile:
    """Command mapping for a supported Flamerite device family."""

    power_on: bytes | None
    power_off: bytes | None
    power_toggle: bytes | None
    heat_on: bytes | None = None
    heat_off: bytes | None = None
    heat_toggle_level: bytes | None = None
    flicker_on: bytes | None = None
    flicker_off: bytes | None = None
    accepts_short_ack_state: bool = False


NITRAFLAME_PROFILE = CommandProfile(
    power_on=None,
    power_off=None,
    power_toggle=bytes.fromhex("a10100"),
    accepts_short_ack_state=False,
)


ARCTECH_PROFILE = CommandProfile(
    power_on=bytes.fromhex("a101ff"),
    power_off=bytes.fromhex("a10100"),
    power_toggle=None,
    heat_on=bytes.fromhex("a10101"),
    heat_off=bytes.fromhex("a10102"),
    heat_toggle_level=bytes.fromhex("a10103"),
    flicker_on=bytes.fromhex("a10108"),
    flicker_off=bytes.fromhex("a10109"),
    accepts_short_ack_state=True,
)


# Commands that can be sent to the device.
class Command(Enum):
    """Commands that can be sent to the Flamerite device via bluetooth."""

    QUERY_STATE = bytes.fromhex("a1010a")
    POWER_TOGGLE = bytes.fromhex("a10100")

    SET_HEAT_LOW = bytes.fromhex("a10101")
    SET_HEAT_HIGH = bytes.fromhex("a10103")

    FLAME_BRIGHTNESS_INC = bytes.fromhex("a10104")
    FLAME_BRIGHTNESS_DEC = bytes.fromhex("a10105")
    FUEL_BRIGHTNESS_INC = bytes.fromhex("a10106")
    FUEL_BRIGHTNESS_DEC = bytes.fromhex("a10107")

    # Set Color commands ('c201' + color) and ('c101' + color)
    SET_FLAME_COLOR = bytes.fromhex("c101")
    SET_FUEL_COLOR = bytes.fromhex("c201")

    # Thermostat control command ('a201' + temp) where temp is in the [16, 31] range.
    SET_THERMOSTAT = bytes.fromhex("a201")
