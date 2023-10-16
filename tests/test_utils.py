from io import StringIO

import pytest

from wsjtx_influxdb.utils import parseBandplanCsv, frequencyToBand, FrequencyRange, Mode

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


def test_mode():
    assert Mode.get("~") == Mode.FT8
    assert Mode.get("OLIVIA8") == Mode.OLIVIA8
    assert Mode.get("8psk125") == Mode._8PSK125
