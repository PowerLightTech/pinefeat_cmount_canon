# Pinefeat Focuser Standalone Control App

A standalone, cross-platform (Windows/Linux/macOS) application for
controlling a **Pinefeat focuser board**'s lens focus and aperture directly
over its serial protocol. It has no dependency on ASCOM, INDI, libcamera, or
the kernel driver in this repository — you only need a serial connection
(wired UART or USB CDC virtual COM port) to the board.

This app is hardware-generic: it works with any Pinefeat board that
implements the ASCII serial protocol described in `../doc/serial.md`,
including:
- **cef168** — the Raspberry Pi / libcamera lens controller in this
  repository, connected over its UART header.
- **cef135** — Pinefeat's USB-connected EF/EF-S lens controller adapter
  (normally paired with the `PinefeatCEF` ASCOM focuser driver), connected
  over its USB CDC virtual COM port.
- Any other current or future Pinefeat board speaking the same protocol.

It ships with:
- A Python library (`pinefeat_focuser.device.LensController`) wrapping the
  protocol commands.
- A command-line interface (`pinefeat-focuser`).
- A Tkinter GUI (`pinefeat-focuser-gui`).

## Why generic?

The serial command set (`c`, `f`/`m`, `r`, `a`, `e`, `v`, etc., with `ok`/
`er`/`nc` responses) is shared across Pinefeat's focuser boards — only the
physical transport differs (wired UART vs. USB CDC). Rather than write a
separate app per board, this app talks to "a Pinefeat focuser" over
whichever serial port you point it at, so the same CLI/GUI/library works
across the current product line without modification.

## Installation

Requires Python 3.10+.

```shell
cd python
pip install -e .
```

This installs the `pinefeat-focuser` and `pinefeat-focuser-gui` console
scripts along with the only runtime dependency,
[`pyserial`](https://pypi.org/project/pyserial/).

For running the test suite, install the dev extra instead:

```shell
pip install -e .[dev]
pytest
```

## CLI usage

```shell
# List available serial ports
pinefeat-focuser ports

# Show lens info (uses the last-used port automatically after first use)
pinefeat-focuser --port COM3 info

# Run calibration (traverses the full focus range)
pinefeat-focuser --port COM3 calibrate

# Focus control
pinefeat-focuser --port COM3 focus get
pinefeat-focuser --port COM3 focus set 500
pinefeat-focuser --port COM3 focus move 100    # towards infinity
pinefeat-focuser --port COM3 focus move -- -50 # towards minimum
pinefeat-focuser --port COM3 focus min
pinefeat-focuser --port COM3 focus inf

# Aperture control
pinefeat-focuser --port COM3 aperture get
pinefeat-focuser --port COM3 aperture set 5.6
pinefeat-focuser --port COM3 aperture open 1
pinefeat-focuser --port COM3 aperture close 1

# Focusing speed (1-4, if supported by the lens)
pinefeat-focuser --port COM3 speed 2

# Live status (one-shot or continuously polled)
pinefeat-focuser --port COM3 status
pinefeat-focuser --port COM3 status --watch --interval 0.5

# Save/reuse named connection profiles (e.g. one per board you own)
pinefeat-focuser profiles save my-cef168 /dev/ttyAMA0 --baud 115200
pinefeat-focuser profiles save my-cef135 COM4
pinefeat-focuser --profile my-cef168 info
pinefeat-focuser profiles list
```

The last-used port/baud rate is automatically remembered in a per-user
config file (`config.json` under an OS-appropriate config directory, e.g.
`%APPDATA%\pinefeat-focuser` on Windows, `~/Library/Application
Support/pinefeat-focuser` on macOS, or
`$XDG_CONFIG_HOME/pinefeat-focuser` / `~/.config/pinefeat-focuser` on
Linux), so subsequent commands can omit `--port`/`--baud`. Named profiles
let you switch between multiple boards (e.g. a cef168 and a cef135) without
re-typing connection details.

## GUI usage

```shell
pinefeat-focuser-gui
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

## Connecting to a specific board

- **cef168** (this repo's Raspberry Pi board): connect via its UART
  header/USB-TTL adapter; see `../doc/serial.md` for pinout and electrical
  details. Typical baud rate: 115200.
- **cef135** (USB adapter): connect via USB; it enumerates as a standard
  USB CDC virtual COM port. Find it with `pinefeat-focuser ports`. Make
  sure no other application (e.g. the ASCOM driver/its focuser app) has the
  port open at the same time. Baud rate is generally irrelevant over USB
  CDC, but the default 115200 can be used or adjusted with `--baud` if
  needed.

Either way, once you have the port name, the rest of the CLI/GUI usage is
identical.

## Library usage

```python
from pinefeat_focuser.device import LensController

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
  pinefeat_focuser/
    protocol.py   # pure command builders + response parsers (no I/O)
    device.py     # LensController: thread-safe API over pyserial
    config.py     # JSON config persistence (last-used port, profiles)
    cli.py        # `pinefeat-focuser` command-line entry point
    gui.py        # `pinefeat-focuser-gui` Tkinter entry point
  tests/
    test_protocol.py
    test_device.py     # uses a fake transport, no hardware required
    fake_serial.py
  pyproject.toml
```

## Notes

- Only the ASCII serial protocol is implemented (not the V4L2/I2C control
  path used by cef168's kernel driver/`calibrate.cpp`), since this app is
  meant to run standalone on any machine with a serial connection to a
  board.
- Error responses `er` (unknown/invalid command) and `nc` (lens not
  connected) are surfaced as Python exceptions
  (`InvalidResponseError`, `LensNotConnectedError`, both subclasses of
  `PinefeatFocuserError`) and shown to the user in both the CLI and GUI.
