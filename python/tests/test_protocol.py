import pytest

from pinefeat_focuser import protocol as proto


# -- command builders ---------------------------------------------------


def test_cmd_set_focus_int():
    assert proto.cmd_set_focus(500) == "f500"


def test_cmd_move_focus_positive():
    assert proto.cmd_move_focus(100) == "f+100"


def test_cmd_move_focus_negative():
    assert proto.cmd_move_focus(-200) == "f-200"


def test_cmd_move_focus_zero_raises():
    with pytest.raises(proto.InvalidParameterError):
        proto.cmd_move_focus(0)


def test_cmd_set_aperture_formats_floats():
    assert proto.cmd_set_aperture(5.6) == "a5.6"


def test_cmd_set_aperture_drops_trailing_zero():
    assert proto.cmd_set_aperture(4.0) == "a4"


def test_cmd_adjust_aperture_sign():
    assert proto.cmd_adjust_aperture(4.0) == "a+4"
    assert proto.cmd_adjust_aperture(-1.0) == "a-1"


def test_cmd_set_speed_valid():
    assert proto.cmd_set_speed(3) == "s3"


def test_cmd_set_speed_invalid_raises():
    with pytest.raises(proto.InvalidParameterError):
        proto.cmd_set_speed(5)


# -- response parsers -----------------------------------------------------


def test_parse_ok():
    proto.parse_ok("f500", "ok")


def test_parse_ok_error_response_raises():
    with pytest.raises(proto.InvalidResponseError):
        proto.parse_ok("f500", "er")


def test_parse_ok_not_connected_raises():
    with pytest.raises(proto.LensNotConnectedError):
        proto.parse_ok("f500", "nc")


def test_parse_int():
    assert proto.parse_int("f", "405") == 405


def test_parse_int_range():
    r = proto.parse_int_range("r", "0-1203")
    assert r.min == 0
    assert r.max == 1203


def test_parse_float_range():
    r = proto.parse_float_range("d", "2.24-6.48")
    assert r.min == pytest.approx(2.24)
    assert r.max == pytest.approx(6.48)


def test_parse_float_range_malformed_raises():
    with pytest.raises(proto.InvalidResponseError):
        proto.parse_float_range("d", "not-a-range")


def test_parse_bool_yn():
    assert proto.parse_bool_yn("e", "y") is True
    assert proto.parse_bool_yn("e", "n") is False


def test_parse_bool_yn_invalid_raises():
    with pytest.raises(proto.InvalidResponseError):
        proto.parse_bool_yn("e", "maybe")


def test_parse_str_not_connected_raises():
    with pytest.raises(proto.LensNotConnectedError):
        proto.parse_str("n", "nc")


def test_parse_info():
    raw = (
        "Lens ID: 0xEB\n"
        "Focal length: 10-22 mm\n"
        "Zoom: 1x\n"
        "Aperture: f/3.5-22.6\n"
        "Focus distance: 0.23-0.23 m"
    )
    info = proto.parse_info(raw)
    assert info.lens_id == "0xEB"
    assert info.focal_length == "10-22 mm"
    assert info.zoom == "1x"
    assert info.aperture == "f/3.5-22.6"
    assert info.focus_distance == "0.23-0.23 m"
    assert info.raw == raw
