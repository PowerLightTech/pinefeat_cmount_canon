"""Standalone control library/CLI/GUI for Pinefeat focuser boards.

This package talks to any Pinefeat focuser board (e.g. cef168, cef135, and
other boards implementing the same command set) over its ASCII serial
protocol (see ``doc/serial.md`` in the repository root, over either a wired
UART or a USB CDC virtual serial port) and does not depend on ASCOM or any
Windows-only components.
"""

__version__ = "0.1.0"
