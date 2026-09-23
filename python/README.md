# cef168 Standalone Control App

A standalone, cross-platform (Windows/Linux/macOS) application for
controlling a Pinefeat _cef168_ lens controller board's focus and aperture
directly over its **serial (UART) interface**. It has no dependency on
ASCOM, libcamera, or the kernel driver in this repository — you only need a
USB-to-serial/TTL connection to the board (see `../doc/serial.md` for the
protocol and electrical interface).

It ships with:
- A Python library (`cef168_control.device.LensController`) wrapping the
  protocol commands.
- A command-line interface (`cef168`).
- A Tkinter GUI (`cef168-gui`).

## Installation

Requires Python 3.10+.

```shell
cd python
pip install -e .
```

This installs the `cef168` and `cef168-gui` console scripts along with the
only runtime dependency, [`pyserial`](https://pypi.org/project/pyserial/).

For running the test suite, install the dev extra instead:

```shell
pip install -e .[dev]
pytest
```

## CLI usage

```shell
# List available serial ports
cef168 ports

# Show lens info (uses the last-used port automatically after first use)
cef168 --port COM3 info

# Run calibration (traverses the full focus range)
cef168 --port COM3 calibrate

# Focus control
cef168 --port COM3 focus get
cef168 --port COM3 focus set 500
cef168 --port COM3 focus move 100    # towards infinity
cef168 --port COM3 focus move -- -50 # towards minimum
cef168 --port COM3 focus min
cef168 --port COM3 focus inf

# Aperture control
cef168 --port COM3 aperture get
cef168 --port COM3 aperture set 5.6
cef168 --port COM3 aperture open 1
cef168 --port COM3 aperture close 1

# Focusing speed (1-4, if supported by the lens)
cef168 --port COM3 speed 2

# Live status (one-shot or continuously polled)
cef168 --port COM3 status
cef168 --port COM3 status --watch --interval 0.5

# Save/reuse named connection profiles
cef168 profiles save my-rig COM3 --baud 115200
cef168 --profile my-rig info
cef168 profiles list
```

The last-used port/baud rate is automatically remembered in a per-user
config file (`config.json` under an OS-appropriate config directory, e.g.
`%APPDATA%\cef168` on Windows, `~/Library/Application Support/cef168` on
macOS, or `$XDG_CONFIG_HOME/cef168` / `~/.config/cef168` on Linux), so
subsequent commands can omit `--port`/`--baud`.

## GUI usage

```shell
cef168-gui
```

The GUI provides:
- A connection bar with serial port discovery/refresh, baud rate, and
  connect/disconnect, plus saved connection profiles.
- A live status panel (focus position, motor moving state, last move time)
  refreshed automatically via a background polling thread.
- Focus controls: absolute set/get, relative near/far step buttons,
  min/infinity shortcuts, and focusing speed.
- Aperture controls: absolute set, f-stop range readout, and open/close
  step buttons.
- A calibration button (with a confirmation prompt, since calibration
  traverses the full focus range).

## Library usage

```python
from cef168_control.device import LensController

with LensController("COM3") as lens:
    lens.calibrate()
    lens.wait_until_idle()
    lens.set_focus(500)
    status = lens.get_status()
    print(status.focus_position, status.moving, status.move_time_ms)
```

## Project layout

```
python/
  cef168_control/
    protocol.py   # pure command builders + response parsers (no I/O)
    device.py     # LensController: thread-safe API over pyserial
    config.py     # JSON config persistence (last-used port, profiles)
    cli.py        # `cef168` command-line entry point
    gui.py        # `cef168-gui` Tkinter entry point
  tests/
    test_protocol.py
    test_device.py     # uses a fake transport, no hardware required
    fake_serial.py
  pyproject.toml
```

## Notes

- Only the ASCII serial protocol is implemented (not the V4L2/I2C control
  path used by the kernel driver/`calibrate.cpp`), since this app is meant
  to run standalone on any machine with a serial connection to the board.
- Error responses `er` (unknown/invalid command) and `nc` (lens not
  connected) are surfaced as Python exceptions
  (`InvalidResponseError`, `LensNotConnectedError`) and shown to the user in
  both the CLI and GUI.
