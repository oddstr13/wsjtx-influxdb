import datetime
from io import StringIO

import pytest

from wsjtx_influxdb.utils import (
    Entry,
    parseBandplanCsv,
    frequencyToBand,
    FrequencyRange,
    Mode,
    DecimalDegrees,
)

bandplan_data = """
30m;10.100;10.150
CB27;26.960;28.000
10m;28.000;29.700
"""


def test_parse_bandplan():
    res = parseBandplanCsv(StringIO(bandplan_data))
    assert list(res.keys()) == ["30m", "CB27", "10m"]


@pytest.mark.parametrize(
    "frequency,band",
    [
        (1, None),
        (10_110_000, "30m"),
        (27.075e6, "CB27"),
        # Currently conflicts with 70cm HAM band.
        # TODO: Make frequencyToBand return the most specific/narrowest range?
        # (446.09375e6, "PMR446"),
    ],
)
def test_frequency_to_band(frequency, band):
    assert frequencyToBand(frequency) == band


def test_frequencyrange():
    range = FrequencyRange(10.1e6, 10.15e6)
    assert 10.1e6 in range
    assert 10_150_000 in range
    assert range.minimum == 10100000
    assert range.maximum == 10150000
    assert range.contains(10125000)

    assert 10.1 not in range
    assert 10150001 not in range

    assert "foo" not in range


@pytest.mark.parametrize(
    "input,mode,output",
    [
        ("~", Mode.FT8, "FT8"),
        ("OLIVIA8", Mode.OLIVIA8, "OLIVIA8"),
        ("8psk125", Mode._8PSK125, "8PSK125"),
    ],
)
def test_mode(input, mode, output):
    assert Mode.get(input) == mode
    assert str(mode) == output


@pytest.mark.parametrize(
    "gridsquare,latitude,longitude,accuracy",
    [
        ("MH09me", -10.8125, 61.0417, None),
        ("JJ00aa00", 0, 0, 0.005),
        ("II50aa00", -10, -10, 0.005),
        ("AA00aa00", -90, -180, 0.005),
        ("JQ78tf", 78.22916, 15.625, 0.00005),
        ("EL29kn", 29.5625, -95.125, None),
        ("JB17gx", -72.01198, 2.53349, 0.01),
    ],
)
def test_decimaldegrees(gridsquare, latitude, longitude, accuracy):
    dd = DecimalDegrees.fromGridsquare(gridsquare)
    # The default accuracy of approx should equal
    # a global accuracy of about 10cm or better.
    # https://en.wikipedia.org/wiki/Decimal_degrees#Precision
    assert dd.latitude == pytest.approx(latitude, abs=accuracy)
    assert dd.longitude == pytest.approx(longitude, abs=accuracy)

    assert dd.toGridsquare(precission=len(gridsquare) / 2) == gridsquare


def test_entry():
    entry = Entry(
        mode=Mode.FT8,
        snr=8,
        frequency=14_075_901,
        message="CQ DX M0WYB IO81",
        time=datetime.datetime.fromisoformat("2023-10-16 07:01:45.500000"),
        receiver_grid="JP52",
        receiver_callsign="SWL",
        sender_grid="IO81",
        sender_callsign="M0WYB",
        target_callsign=None,
        cq=True,
    )

    print(entry.distance, entry.heading)
    assert entry.distance == 1_484_504
    assert entry.heading == pytest.approx(220.863, abs=0.0005)
    assert entry.band_name == "20m"
    print(repr(str(entry)))
    assert (
        str(entry)
        == "2023-10-16 07:01:45.500000\t 8\tFT8\t 14075.901 kHz\tCQ DX M0WYB IO81"
    )

    coords = entry.sender_coordinates
    assert (coords.latitude, coords.longitude) == pytest.approx((51.5, -3))

    entry = Entry(
        mode=Mode.FT8,
        snr=-12,
        frequency=14_075_901,
        message="THX 73",
        time=datetime.datetime.fromisoformat("2023-10-16 07:01:45.500000"),
        receiver_grid="JP52",
        receiver_callsign="SWL",
        sender_grid=None,
        sender_callsign=None,
        target_callsign=None,
        cq=False,
    )

    assert entry.distance is None
    assert entry.heading is None
    assert entry.sender_coordinates is None
