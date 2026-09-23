import pytest

from pinefeat_focuser import protocol as proto
from pinefeat_focuser.device import LensController
from .fake_serial import FakeTransport


def make_lens(responses: dict) -> LensController:
    transport = FakeTransport(responses)
    return LensController("FAKE", transport=transport)


def test_get_focus():
    lens = make_lens({"f": "405"})
    assert lens.get_focus() == 405


def test_set_focus_sends_correct_command():
    transport = FakeTransport({"f500": "ok"})
    lens = LensController("FAKE", transport=transport)
    lens.set_focus(500)
    assert transport.sent == ["f500"]


def test_move_focus_positive_and_negative():
    transport = FakeTransport({"f+100": "ok", "f-50": "ok"})
    lens = LensController("FAKE", transport=transport)
    lens.move_focus(100)
    lens.move_focus(-50)
    assert transport.sent == ["f+100", "f-50"]


def test_move_focus_to_min_and_infinity():
    transport = FakeTransport({"m": "ok", "i": "ok"})
    lens = LensController("FAKE", transport=transport)
    lens.move_focus_to_min()
    lens.move_focus_to_infinity()
    assert transport.sent == ["m", "i"]


def test_calibrate_ok():
    lens = make_lens({"c": "ok"})
    lens.calibrate()  # should not raise


def test_calibrate_not_connected_raises():
    lens = make_lens({"c": "nc"})
    with pytest.raises(proto.LensNotConnectedError):
        lens.calibrate()


def test_get_focus_position_range():
    lens = make_lens({"r": "0-1203"})
    r = lens.get_focus_position_range()
    assert (r.min, r.max) == (0, 1203)


def test_get_aperture_range():
    lens = make_lens({"a": "3.5-22.6"})
    r = lens.get_aperture_range()
    assert r.min == pytest.approx(3.5)
    assert r.max == pytest.approx(22.6)


def test_set_aperture():
    transport = FakeTransport({"a5.6": "ok"})
    lens = LensController("FAKE", transport=transport)
    lens.set_aperture(5.6)
    assert transport.sent == ["a5.6"]


def test_is_motor_active():
    lens = make_lens({"e": "y"})
    assert lens.is_motor_active() is True


def test_get_status_combines_calls():
    lens = make_lens({"f": "405", "e": "n", "t": "95"})
    status = lens.get_status()
    assert status.focus_position == 405
    assert status.moving is False
    assert status.move_time_ms == 95


def test_get_serial_number_not_connected_raises():
    lens = make_lens({"n": "nc"})
    with pytest.raises(proto.LensNotConnectedError):
        lens.get_serial_number()


def test_set_focus_speed_invalid_value_raises_before_send():
    transport = FakeTransport({})
    lens = LensController("FAKE", transport=transport)
    with pytest.raises(proto.InvalidParameterError):
        lens.set_focus_speed(9)
    assert transport.sent == []


def test_wait_until_idle_returns_when_not_moving():
    lens = make_lens({"e": "n"})
    lens.wait_until_idle(poll_interval=0.01, overall_timeout=1)


def test_wait_until_idle_times_out():
    lens = make_lens({"e": ["y"] * 100})
    with pytest.raises(TimeoutError):
        lens.wait_until_idle(poll_interval=0.005, overall_timeout=0.02)


def test_close_closes_transport():
    transport = FakeTransport({})
    lens = LensController("FAKE", transport=transport)
    lens.close()
    assert transport.is_open is False
