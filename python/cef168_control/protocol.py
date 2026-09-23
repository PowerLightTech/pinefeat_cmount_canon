"""Command builders and response parsers for the cef168 ASCII serial protocol.

This module is pure (no I/O): it only knows how to build command strings to
send over the wire and how to parse/validate the text responses documented in
``doc/serial.md``. Keeping it I/O-free makes it trivial to unit test.
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class CefError(Exception):
    """Base class for all cef168 protocol errors."""


class LensNotConnectedError(CefError):
    """Raised when the device reports ``nc`` (lens not connected)."""

    def __init__(self) -> None:
        super().__init__("Lens is not connected to the controller")


class InvalidResponseError(CefError):
    """Raised when the device reports ``er`` or an unparsable response."""

    def __init__(self, command: str, response: str) -> None:
        self.command = command
        self.response = response
        super().__init__(
            f"Invalid response {response!r} for command {command!r}"
        )


class InvalidParameterError(CefError):
    """Raised when a caller supplies a parameter outside the accepted range."""


# --------------------------------------------------------------------------
# Response value types
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RangeInt:
    min: int
    max: int


@dataclass(frozen=True)
class RangeFloat:
    min: float
    max: float


@dataclass(frozen=True)
class LensInfo:
    """Parsed output of the ``h`` (lens info) command."""

    lens_id: str | None = None
    focal_length: str | None = None
    zoom: str | None = None
    aperture: str | None = None
    focus_distance: str | None = None
    raw: str = ""


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _check_ok_response(command: str, response: str) -> None:
    text = response.strip().lower()
    if text == "ok":
        return
    if text == "nc":
        raise LensNotConnectedError()
    raise InvalidResponseError(command, response)


def _parse_value_response(command: str, response: str) -> str:
    text = response.strip()
    if text.lower() == "nc":
        raise LensNotConnectedError()
    if text.lower() == "er":
        raise InvalidResponseError(command, response)
    return text


def _parse_range(command: str, response: str, cast):
    text = _parse_value_response(command, response)
    parts = text.split("-")
    if len(parts) != 2:
        raise InvalidResponseError(command, response)
    try:
        return cast(parts[0]), cast(parts[1])
    except ValueError as exc:
        raise InvalidResponseError(command, response) from exc


def _fmt_num(value: float) -> str:
    """Format a number for inclusion in a command, dropping a trailing .0."""
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


# --------------------------------------------------------------------------
# Command builders (return the raw ASCII string to write, without CR)
# --------------------------------------------------------------------------


def cmd_info() -> str:
    return "h"


def cmd_calibrate() -> str:
    return "c"


def cmd_get_focal_length() -> str:
    return "l"


def cmd_get_focus_distance_range() -> str:
    return "d"


def cmd_get_focus_position_range() -> str:
    return "r"


def cmd_get_focus() -> str:
    return "f"


def cmd_set_focus(value: int) -> str:
    return f"f{_fmt_num(value)}"


def cmd_move_focus(delta: int) -> str:
    if delta == 0:
        raise InvalidParameterError("Focus move delta must be non-zero")
    sign = "+" if delta > 0 else "-"
    return f"f{sign}{_fmt_num(abs(delta))}"


def cmd_move_focus_infinity() -> str:
    return "i"


def cmd_move_focus_min() -> str:
    return "m"


def cmd_get_aperture_range() -> str:
    return "a"


def cmd_set_aperture(fstop: float) -> str:
    return f"a{_fmt_num(fstop)}"


def cmd_adjust_aperture(delta_stops: float) -> str:
    if delta_stops == 0:
        raise InvalidParameterError("Aperture adjustment must be non-zero")
    sign = "+" if delta_stops > 0 else "-"
    return f"a{sign}{_fmt_num(abs(delta_stops))}"


def cmd_set_speed(speed: int) -> str:
    if speed not in (1, 2, 3, 4):
        raise InvalidParameterError("Speed must be between 1 and 4")
    return f"s{speed}"


def cmd_get_motor_active() -> str:
    return "e"


def cmd_get_move_time() -> str:
    return "t"


def cmd_get_serial_number() -> str:
    return "n"


def cmd_get_firmware_version() -> str:
    return "v"


# --------------------------------------------------------------------------
# Response parsers
# --------------------------------------------------------------------------


def parse_info(response: str) -> LensInfo:
    text = _parse_value_response("h", response)
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip().lower()] = value.strip()
    return LensInfo(
        lens_id=fields.get("lens id"),
        focal_length=fields.get("focal length"),
        zoom=fields.get("zoom"),
        aperture=fields.get("aperture"),
        focus_distance=fields.get("focus distance"),
        raw=text,
    )


def parse_ok(command: str, response: str) -> None:
    _check_ok_response(command, response)


def parse_int(command: str, response: str) -> int:
    text = _parse_value_response(command, response)
    try:
        return int(float(text))
    except ValueError as exc:
        raise InvalidResponseError(command, response) from exc


def parse_float(command: str, response: str) -> float:
    text = _parse_value_response(command, response)
    try:
        return float(text)
    except ValueError as exc:
        raise InvalidResponseError(command, response) from exc


def parse_int_range(command: str, response: str) -> RangeInt:
    lo, hi = _parse_range(command, response, int)
    return RangeInt(min=lo, max=hi)


def parse_float_range(command: str, response: str) -> RangeFloat:
    lo, hi = _parse_range(command, response, float)
    return RangeFloat(min=lo, max=hi)


def parse_bool_yn(command: str, response: str) -> bool:
    text = _parse_value_response(command, response).lower()
    if text == "y":
        return True
    if text == "n":
        return False
    raise InvalidResponseError(command, response)


def parse_str(command: str, response: str) -> str:
    return _parse_value_response(command, response)
