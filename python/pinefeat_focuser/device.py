"""High-level, thread-safe API for talking to a Pinefeat focuser board over serial."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from . import protocol as proto

try:
    import serial
    from serial.tools import list_ports
except ImportError as exc:  # pragma: no cover - exercised only without pyserial
    raise ImportError(
        "The 'pyserial' package is required. Install it with 'pip install pyserial'."
    ) from exc

DEFAULT_BAUD_RATE = 115200
DEFAULT_TIMEOUT = 2.0


@dataclass(frozen=True)
class PortInfo:
    device: str
    description: str


def list_available_ports() -> list[PortInfo]:
    """Return the serial ports currently available on this machine."""
    return [
        PortInfo(device=p.device, description=p.description or "")
        for p in list_ports.comports()
    ]


@dataclass
class LensStatus:
    """Snapshot of live telemetry, combining several protocol commands."""

    focus_position: int | None = None
    moving: bool | None = None
    move_time_ms: int | None = None


class SerialTransport:
    """Thin wrapper around :class:`serial.Serial` for sending commands.

    Handles line termination and decoding so :class:`LensController` only
    deals with already-stripped ASCII strings.
    """

    def __init__(
        self,
        port: str,
        baudrate: int = DEFAULT_BAUD_RATE,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._serial = serial.Serial(
            port=port, baudrate=baudrate, timeout=timeout
        )

    def close(self) -> None:
        self._serial.close()

    @property
    def is_open(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    def send(self, command: str) -> str:
        self._serial.reset_input_buffer()
        self._serial.write((command + "\r\n").encode("ascii"))
        raw = self._serial.readline()
        if not raw:
            raise proto.InvalidResponseError(command, "<no response>")
        return raw.decode("ascii", errors="replace").strip()


class LensController:
    """High-level, thread-safe controller for a Pinefeat focuser board
    (cef168, cef135, and other boards implementing the same protocol).

    Example::

        with LensController("COM3") as lens:
            lens.calibrate()
            lens.set_focus(500)
    """

    def __init__(
        self,
        port: str,
        baudrate: int = DEFAULT_BAUD_RATE,
        timeout: float = DEFAULT_TIMEOUT,
        transport: SerialTransport | None = None,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self._lock = threading.RLock()
        self._transport = transport or SerialTransport(port, baudrate, timeout)

    # -- lifecycle ---------------------------------------------------

    def close(self) -> None:
        with self._lock:
            self._transport.close()

    def __enter__(self) -> "LensController":
        return self

    def __exit__(self, *_exc_info) -> None:
        self.close()

    def _send(self, command: str) -> str:
        with self._lock:
            return self._transport.send(command)

    # -- info ----------------------------------------------------------

    def get_info(self) -> proto.LensInfo:
        return proto.parse_info(self._send(proto.cmd_info()))

    def get_focal_length_mm(self) -> int:
        cmd = proto.cmd_get_focal_length()
        return proto.parse_int(cmd, self._send(cmd))

    def get_focus_distance_range_m(self) -> proto.RangeFloat:
        cmd = proto.cmd_get_focus_distance_range()
        return proto.parse_float_range(cmd, self._send(cmd))

    def get_focus_position_range(self) -> proto.RangeInt:
        cmd = proto.cmd_get_focus_position_range()
        return proto.parse_int_range(cmd, self._send(cmd))

    def get_serial_number(self) -> str:
        cmd = proto.cmd_get_serial_number()
        return proto.parse_str(cmd, self._send(cmd))

    def get_firmware_version(self) -> str:
        cmd = proto.cmd_get_firmware_version()
        return proto.parse_str(cmd, self._send(cmd))

    # -- calibration -----------------------------------------------------

    def calibrate(self) -> None:
        cmd = proto.cmd_calibrate()
        proto.parse_ok(cmd, self._send(cmd))

    # -- focus -----------------------------------------------------------

    def get_focus(self) -> int:
        cmd = proto.cmd_get_focus()
        return proto.parse_int(cmd, self._send(cmd))

    def set_focus(self, value: int) -> None:
        cmd = proto.cmd_set_focus(value)
        proto.parse_ok(cmd, self._send(cmd))

    def move_focus(self, delta: int) -> None:
        cmd = proto.cmd_move_focus(delta)
        proto.parse_ok(cmd, self._send(cmd))

    def move_focus_to_infinity(self) -> None:
        cmd = proto.cmd_move_focus_infinity()
        proto.parse_ok(cmd, self._send(cmd))

    def move_focus_to_min(self) -> None:
        cmd = proto.cmd_move_focus_min()
        proto.parse_ok(cmd, self._send(cmd))

    def set_focus_speed(self, speed: int) -> None:
        cmd = proto.cmd_set_speed(speed)
        proto.parse_ok(cmd, self._send(cmd))

    # -- aperture ----------------------------------------------------------

    def get_aperture_range(self) -> proto.RangeFloat:
        cmd = proto.cmd_get_aperture_range()
        return proto.parse_float_range(cmd, self._send(cmd))

    def set_aperture(self, fstop: float) -> None:
        cmd = proto.cmd_set_aperture(fstop)
        proto.parse_ok(cmd, self._send(cmd))

    def adjust_aperture(self, delta_stops: float) -> None:
        cmd = proto.cmd_adjust_aperture(delta_stops)
        proto.parse_ok(cmd, self._send(cmd))

    # -- status / telemetry ------------------------------------------------

    def is_motor_active(self) -> bool:
        cmd = proto.cmd_get_motor_active()
        return proto.parse_bool_yn(cmd, self._send(cmd))

    def get_move_time_ms(self) -> int:
        cmd = proto.cmd_get_move_time()
        return proto.parse_int(cmd, self._send(cmd))

    def get_status(self) -> LensStatus:
        """Convenience snapshot combining focus position + motor state."""
        return LensStatus(
            focus_position=self.get_focus(),
            moving=self.is_motor_active(),
            move_time_ms=self.get_move_time_ms(),
        )

    def wait_until_idle(
        self, poll_interval: float = 0.2, overall_timeout: float | None = 30.0
    ) -> None:
        """Block until the motor stops moving (or timeout expires)."""
        start = time.monotonic()
        while self.is_motor_active():
            if overall_timeout is not None and (
                time.monotonic() - start > overall_timeout
            ):
                raise TimeoutError("Timed out waiting for lens motor to become idle")
            time.sleep(poll_interval)
