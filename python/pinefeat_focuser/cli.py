"""Command-line interface for controlling a Pinefeat focuser board."""

from __future__ import annotations

import argparse
import sys
import time

from . import config as cfgmod
from . import protocol as proto
from .device import LensController, list_available_ports


def _resolve_connection(args: argparse.Namespace) -> tuple[str, int]:
    """Work out (port, baudrate) from CLI args, saved profile, or last-used."""
    config = cfgmod.load_config()

    if args.profile:
        profile = config.get_profile(args.profile)
        if not profile:
            print(f"error: no saved profile named {args.profile!r}", file=sys.stderr)
            sys.exit(2)
        port = args.port or profile.port
        baudrate = args.baud or profile.baudrate
        return port, baudrate

    port = args.port or config.last_port
    baudrate = args.baud or config.last_baudrate
    if not port:
        print(
            "error: no serial port specified and none saved yet; "
            "use --port or run 'pinefeat-focuser ports' to list available ports",
            file=sys.stderr,
        )
        sys.exit(2)
    return port, baudrate


def _remember_connection(port: str, baudrate: int) -> None:
    config = cfgmod.load_config()
    config.last_port = port
    config.last_baudrate = baudrate
    cfgmod.save_config(config)


def _connect(args: argparse.Namespace) -> LensController:
    port, baudrate = _resolve_connection(args)
    try:
        lens = LensController(port, baudrate=baudrate)
    except Exception as exc:  # serial.SerialException, etc.
        print(f"error: failed to open {port!r}: {exc}", file=sys.stderr)
        sys.exit(1)
    _remember_connection(port, baudrate)
    return lens


def _run(func, args: argparse.Namespace) -> int:
    lens = _connect(args)
    try:
        func(lens, args)
        return 0
    except proto.PinefeatFocuserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        lens.close()


# -- command implementations -------------------------------------------------


def cmd_ports(args: argparse.Namespace) -> int:
    ports = list_available_ports()
    if not ports:
        print("No serial ports found.")
        return 0
    for p in ports:
        print(f"{p.device}\t{p.description}")
    return 0


def cmd_profiles(args: argparse.Namespace) -> int:
    config = cfgmod.load_config()
    action = args.profile_action
    if action == "list":
        if not config.profiles:
            print("No saved profiles.")
            return 0
        for p in config.profiles:
            print(f"{p.name}\t{p.port}\t{p.baudrate}")
        return 0
    if action == "save":
        config.upsert_profile(
            cfgmod.ConnectionProfile(
                name=args.name, port=args.port, baudrate=args.baud or 115200
            )
        )
        cfgmod.save_config(config)
        print(f"Saved profile {args.name!r}.")
        return 0
    if action == "remove":
        if config.remove_profile(args.name):
            cfgmod.save_config(config)
            print(f"Removed profile {args.name!r}.")
            return 0
        print(f"No such profile: {args.name!r}", file=sys.stderr)
        return 1
    return 1


def _info(lens: LensController, args: argparse.Namespace) -> None:
    info = lens.get_info()
    print(info.raw)


def _calibrate(lens: LensController, args: argparse.Namespace) -> None:
    print("Calibrating... (this traverses the full focus range)")
    lens.calibrate()
    print("ok")


def _focus_get(lens: LensController, args: argparse.Namespace) -> None:
    print(lens.get_focus())


def _focus_set(lens: LensController, args: argparse.Namespace) -> None:
    lens.set_focus(args.value)
    print("ok")


def _focus_move(lens: LensController, args: argparse.Namespace) -> None:
    lens.move_focus(args.delta)
    print("ok")


def _focus_min(lens: LensController, args: argparse.Namespace) -> None:
    lens.move_focus_to_min()
    print("ok")


def _focus_inf(lens: LensController, args: argparse.Namespace) -> None:
    lens.move_focus_to_infinity()
    print("ok")


def _aperture_get(lens: LensController, args: argparse.Namespace) -> None:
    r = lens.get_aperture_range()
    print(f"{r.min}-{r.max}")


def _aperture_set(lens: LensController, args: argparse.Namespace) -> None:
    lens.set_aperture(args.value)
    print("ok")


def _aperture_open(lens: LensController, args: argparse.Namespace) -> None:
    lens.adjust_aperture(args.stops)
    print("ok")


def _aperture_close(lens: LensController, args: argparse.Namespace) -> None:
    lens.adjust_aperture(-args.stops)
    print("ok")


def _speed_set(lens: LensController, args: argparse.Namespace) -> None:
    lens.set_focus_speed(args.value)
    print("ok")


def _status_once(lens: LensController) -> None:
    status = lens.get_status()
    print(
        f"focus={status.focus_position} moving={status.moving} "
        f"move_time_ms={status.move_time_ms}"
    )


def _status(lens: LensController, args: argparse.Namespace) -> None:
    if not args.watch:
        _status_once(lens)
        return
    try:
        while True:
            _status_once(lens)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass


# -- argument parser ----------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pinefeat-focuser",
        description="Standalone controller for Pinefeat focuser boards (cef168, cef135, and compatible boards; serial protocol).",
    )
    parser.add_argument("--port", help="Serial port, e.g. COM3 or /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, help="Baud rate (default 115200)")
    parser.add_argument("--profile", help="Use a saved connection profile by name")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ports", help="List available serial ports").set_defaults(
        func=cmd_ports
    )

    profiles_parser = sub.add_parser("profiles", help="Manage saved connection profiles")
    profiles_sub = profiles_parser.add_subparsers(
        dest="profile_action", required=True
    )
    profiles_sub.add_parser("list", help="List saved profiles")
    save_p = profiles_sub.add_parser("save", help="Save a connection profile")
    save_p.add_argument("name")
    save_p.add_argument("port")
    save_p.add_argument("--baud", type=int, default=115200)
    remove_p = profiles_sub.add_parser("remove", help="Remove a saved profile")
    remove_p.add_argument("name")
    profiles_parser.set_defaults(func=cmd_profiles)

    sub.add_parser("info", help="Print lens info").set_defaults(
        func=lambda a: _run(_info, a)
    )
    sub.add_parser("calibrate", help="Run the calibration procedure").set_defaults(
        func=lambda a: _run(_calibrate, a)
    )

    focus_parser = sub.add_parser("focus", help="Focus control")
    focus_sub = focus_parser.add_subparsers(dest="focus_action", required=True)
    focus_sub.add_parser("get", help="Read absolute focus position").set_defaults(
        func=lambda a: _run(_focus_get, a)
    )
    fset = focus_sub.add_parser("set", help="Set absolute focus position")
    fset.add_argument("value", type=int)
    fset.set_defaults(func=lambda a: _run(_focus_set, a))
    fmove = focus_sub.add_parser("move", help="Move focus by a relative delta")
    fmove.add_argument(
        "delta", type=int, help="Positive moves toward infinity, negative toward minimum"
    )
    fmove.set_defaults(func=lambda a: _run(_focus_move, a))
    focus_sub.add_parser("min", help="Move focus to minimum").set_defaults(
        func=lambda a: _run(_focus_min, a)
    )
    focus_sub.add_parser("inf", help="Move focus to infinity").set_defaults(
        func=lambda a: _run(_focus_inf, a)
    )

    aperture_parser = sub.add_parser("aperture", help="Aperture control")
    aperture_sub = aperture_parser.add_subparsers(
        dest="aperture_action", required=True
    )
    aperture_sub.add_parser("get", help="Read aperture f-stop range").set_defaults(
        func=lambda a: _run(_aperture_get, a)
    )
    aset = aperture_sub.add_parser("set", help="Set aperture to an f-stop value")
    aset.add_argument("value", type=float)
    aset.set_defaults(func=lambda a: _run(_aperture_set, a))
    aopen = aperture_sub.add_parser("open", help="Open the iris by N stops")
    aopen.add_argument("stops", type=float)
    aopen.set_defaults(func=lambda a: _run(_aperture_open, a))
    aclose = aperture_sub.add_parser("close", help="Close the iris by N stops")
    aclose.add_argument("stops", type=float)
    aclose.set_defaults(func=lambda a: _run(_aperture_close, a))

    speed_parser = sub.add_parser("speed", help="Set focusing speed (1-4)")
    speed_parser.add_argument("value", type=int)
    speed_parser.set_defaults(func=lambda a: _run(_speed_set, a))

    status_parser = sub.add_parser("status", help="Show live status")
    status_parser.add_argument(
        "--watch", action="store_true", help="Continuously poll and print status"
    )
    status_parser.add_argument(
        "--interval", type=float, default=0.5, help="Polling interval in seconds"
    )
    status_parser.set_defaults(func=lambda a: _run(_status, a))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
