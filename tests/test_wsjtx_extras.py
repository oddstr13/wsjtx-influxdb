import pytest
import datetime
from wsjtx_influxdb.config import RECEIVER_CALLSIGN, RECEIVER_GRID
from wsjtx_influxdb.utils import Entry, Mode

from wsjtx_influxdb.wsjtx_extras import (
    parse_time,
    parseWsjtMessage,
    parseWsjtxAllLog,
    parseWsjtxAllLogLine,
    UDP_CONN,
)


# WSPR_Decode is_new=1 time=7680000 snr=-25 delta_t=0.6000000238418579 frq=10140138 drift=0 callsign=IU2PJI grid=JN45 power=23 off_air=0
# Status dial_frq=14074000 mode=FT8 dx_call=ZD9W report=0 tx_mode=FT8 tx_enabled=0 xmitting=0 decoding=1 rx_df=2259 tx_df=1500 de_call=SWL de_grid=MH09me dx_grid=None tx_watchdog=0 sub_mode=None fast_mode=0 special_op=0 frq_tolerance=4294967295 t_r_period=4294967295 config_name=Default tx_message=None
# Decode is_new=1 time=81810000 snr=-20 delta_t=0.5 delta_f=1709 mode=~ message=CQ SV5AZP KM46 low_confidence=0 off_air=0


@pytest.mark.parametrize(
    "time,delta_t,expected",
    [
        (81810000, 0.6000000238418579, "22:43:30.6"),
        (7680000, 0.5, "02:08:00.5"),
    ],
)
def test_parse_time(time, delta_t, expected):
    expected_time = datetime.datetime.strptime(expected, "%H:%M:%S.%f").time()
    parsed = parse_time(time=time, offset=delta_t)
    assert parsed.time() == expected_time


@pytest.mark.parametrize(
    "message,expected",
    [
        # EC88 looks like locator.
        ("TZ3LTD/P JG4AMP/P R EC88", (False, "JG4AMP/P", None)),
        # LO68 looks like locator.
        ("8P6GE RA4NCC LO68", (False, "RA4NCC", None)),
        ("KK4CQN RA6ABO R-04", (False, "RA6ABO", None)),
        ("CQ R7DX KN84", (True, "R7DX", "KN84")),
        ("KA6BIM UN7JO +05", (False, "UN7JO", None)),
        ("KE0LCS R7DX -15", (False, "R7DX", None)),
        ("YI3WHR RK4HP 73", (False, "RK4HP", None)),
        ("K6BRN RZ6L RR73", (False, "RZ6L", None)),
        ("ZL2BX <...> -09", (False, "<...>", None)),
        # DO88 looks like locator
        ("RV3HSG EK5AUA/R DO88", (False, "EK5AUA/R", None)),
        ("<N6BCE> R0FBA/9", (False, "R0FBA/9", None)),
        ("RC0AT <R0FBA/9> +08", (False, "<R0FBA/9>", None)),
        ("<SV8EUL> <...> R 520305 LG83SK", (False, None, None)),
        ("CQ DX F4BKV IN95", (True, "F4BKV", "IN95")),
        ("CQ NA PF01MAX", (True, "PF01MAX", None)),
    ],
)
def test_parseWsjtMessage(message, expected):
    assert parseWsjtMessage(message) == expected


# ['231006_035100', '3.573', 'Rx', 'FT8', '-16', '0.6', '2753', 'CQ DX F4BKV IN95']


@pytest.mark.parametrize(
    "line,expected",
    [
        (
            "231006_035130     3.573 Rx FT8    -20  0.6 2753 CQ DX F4BKV IN95",
            Entry(
                mode=Mode.FT8,
                snr=-20,
                frequency=3_575_753,
                time=datetime.datetime.fromisoformat("2023-10-06 03:51:30.600"),
                message="CQ DX F4BKV IN95",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
                cq=True,
                sender_callsign="F4BKV",
                sender_grid="IN95",
            ),
        ),
        (
            "231006_035145     3.573 Rx FT8     -9 -0.2 1446 LB2WD SP5AA -09",
            Entry(
                mode=Mode.FT8,
                snr=-9,
                frequency=3_574_446,
                time=datetime.datetime.fromisoformat("2023-10-06 03:51:44.800"),
                message="LB2WD SP5AA -09",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
                sender_callsign="SP5AA",
            ),
        ),
        (
            "231006_035145     3.573 Rx FT8    -15  0.7 2319 NK9R 9A5TW RR73",
            Entry(
                mode=Mode.FT8,
                snr=-15,
                frequency=3_575_319,
                time=datetime.datetime.fromisoformat("2023-10-06 03:51:45.700"),
                message="NK9R 9A5TW RR73",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
                sender_callsign="9A5TW",
            ),
        ),
        (
            "231006_035200     3.573 Rx FT8    -10  0.9 1354 CQ DX SP2MKE JO93",
            Entry(
                mode=Mode.FT8,
                snr=-10,
                frequency=3_574_354,
                time=datetime.datetime.fromisoformat("2023-10-06 03:52:00.900"),
                message="CQ DX SP2MKE JO93",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
                cq=True,
                sender_callsign="SP2MKE",
                sender_grid="JO93",
            ),
        ),
        (
            "231006_041100     7.074 Rx FT8    -17  0.6 1646 RU3DMX <RO80MZ> R-02",
            Entry(
                mode=Mode.FT8,
                snr=-17,
                frequency=7_075_646,
                time=datetime.datetime.fromisoformat("2023-10-06 04:11:00.600"),
                message="RU3DMX <RO80MZ> R-02",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
                sender_callsign="<RO80MZ>",
            ),
        ),
        (
            "231006_041145     7.074 Rx FT8    -19  0.6  843 CM7JAA R3AP R-25",
            Entry(
                mode=Mode.FT8,
                snr=-19,
                frequency=7_074_843,
                time=datetime.datetime.fromisoformat("2023-10-06 04:11:45.600"),
                message="CM7JAA R3AP R-25",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
                sender_callsign="R3AP",
            ),
        ),
        (
            "231006_041200     7.074 Rx FT8     -7  0.6 2703 CO8WN RU3DMX -14",
            Entry(
                mode=Mode.FT8,
                snr=-7,
                frequency=7_076_703,
                time=datetime.datetime.fromisoformat("2023-10-06 04:12:00.600"),
                message="CO8WN RU3DMX -14",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
                sender_callsign="RU3DMX",
            ),
        ),
        (
            "231006_042915     3.567 Rx FT8    -13  0.8  789 ZD9W DF2GH JN68",
            Entry(
                mode=Mode.FT8,
                snr=-13,
                frequency=3_567_789,
                time=datetime.datetime.fromisoformat("2023-10-06 04:29:15.800"),
                message="ZD9W DF2GH JN68",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
                sender_callsign="DF2GH",
            ),
        ),
        (
            "231006_042915     3.567 Rx FT8    -24  0.9 1532 JJ0NFJ 333XQU R 549 2538",
            Entry(
                mode=Mode.FT8,
                snr=-24,
                frequency=3_568_532,
                time=datetime.datetime.fromisoformat("2023-10-06 04:29:15.900"),
                message="JJ0NFJ 333XQU R 549 2538",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
            ),
        ),
        (
            "231006_182200     7.074 Rx FT8    -12  1.3 2789 UB6HQQ ES6RQ -05",
            Entry(
                mode=Mode.FT8,
                snr=-12,
                frequency=7_076_789,
                time=datetime.datetime.fromisoformat("2023-10-06 18:22:01.300"),
                message="UB6HQQ ES6RQ -05",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
                sender_callsign="ES6RQ",
            ),
        ),
        (
            "231006_182200     7.074 Rx FT8    -16  1.2 2673 CQ 5P1KZX JO57",
            Entry(
                mode=Mode.FT8,
                snr=-16,
                frequency=7_076_673,
                time=datetime.datetime.fromisoformat("2023-10-06 18:22:01.200"),
                message="CQ 5P1KZX JO57",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
                cq=True,
                sender_callsign="5P1KZX",
                sender_grid="JO57",
            ),
        ),
        (
            "231006_182200     7.074 Rx FT8    -17  0.7 2089 <AO23DMPC> R1BJX R-10",
            Entry(
                mode=Mode.FT8,
                snr=-17,
                frequency=7_076_089,
                time=datetime.datetime.fromisoformat("2023-10-06 18:22:00.700"),
                message="<AO23DMPC> R1BJX R-10",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
                sender_callsign="R1BJX",
            ),
        ),
        (
            "231006_182200     7.074 Rx FT8    -20 -0.1  925 4X1UF LB6GJ JP50",
            Entry(
                mode=Mode.FT8,
                snr=-20,
                frequency=7_074_925,
                time=datetime.datetime.fromisoformat("2023-10-06 18:21:59.900"),
                message="4X1UF LB6GJ JP50",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
                sender_callsign="LB6GJ",
            ),
        ),
        (
            "231006_214115     7.074 Rx FT8    -11  1.7 1784 <9H/DK6SP> DH8GHH JO52",
            Entry(
                mode=Mode.FT8,
                snr=-11,
                frequency=7_075_784,
                time=datetime.datetime.fromisoformat("2023-10-06 21:41:16.700"),
                message="<9H/DK6SP> DH8GHH JO52",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
                sender_callsign="DH8GHH",
            ),
        ),
        (
            "231006_214115     7.074 Rx FT8    -13  1.3  787 7J1ADJ DF7TV JN48",
            Entry(
                mode=Mode.FT8,
                snr=-13,
                frequency=7_074_787,
                time=datetime.datetime.fromisoformat("2023-10-06 21:41:16.300"),
                message="7J1ADJ DF7TV JN48",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
                sender_callsign="DF7TV",
            ),
        ),
        (
            "231006_214115     7.074 Rx FT8    -13  1.5 2295 CQ PB0AIC JO21",
            Entry(
                mode=Mode.FT8,
                snr=-13,
                frequency=7_076_295,
                time=datetime.datetime.fromisoformat("2023-10-06 21:41:16.500"),
                message="CQ PB0AIC JO21",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
                cq=True,
                sender_callsign="PB0AIC",
                sender_grid="JO21",
            ),
        ),
        (
            "231009_050115    14.080 Rx FT4    -13  0.1  618 CQ TA2ANK KM69                        a1",
            Entry(
                mode=Mode.FT4,
                snr=-13,
                frequency=14_080_618,
                time=datetime.datetime.fromisoformat("2023-10-09 05:01:15.100"),
                message="CQ TA2ANK KM69                        a1",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
                cq=True,
                sender_callsign="TA2ANK",
                sender_grid=None,
            ),
        ),
        (
            "231009_055730    14.074 Rx FT8     -3  1.6  872 TU; QN5HYK 649RMM R 549 2401",
            Entry(
                mode=Mode.FT8,
                snr=-3,
                frequency=14_074_872,
                time=datetime.datetime.fromisoformat("2023-10-09 05:57:31.600"),
                message="TU; QN5HYK 649RMM R 549 2401",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
            ),
        ),
        (
            "231010_212330    14.074 Rx FT8      7  1.0  337 KC1NNR RR73; GI6FZI <5B4AMM> -08",
            Entry(
                mode=Mode.FT8,
                snr=7,
                frequency=14_074_337,
                time=datetime.datetime.fromisoformat("2023-10-10 21:23:31"),
                message="KC1NNR RR73; GI6FZI <5B4AMM> -08",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
            ),
        ),
        (
            "231013_183000    14.072 Rx FT8    -19  0.9 4219 CQ HA7EC JN97",
            Entry(
                mode=Mode.FT8,
                snr=-19,
                frequency=14_076_219,
                time=datetime.datetime.fromisoformat("2023-10-13 18:30:00.900"),
                message="CQ HA7EC JN97",
                receiver_grid=RECEIVER_GRID,
                receiver_callsign=RECEIVER_CALLSIGN,
                cq=True,
                sender_callsign="HA7EC",
                sender_grid="JN97",
            ),
        ),
        (
            "231013_183000    14.072 Rx FT8 ",
            None,
        ),
        (
            "231013_183000    14.072 Rx FT8    -19  0.9 4219     ",
            None,
        ),
    ],
)
def test_parseWsjtxAllLogLine(line, expected):
    assert parseWsjtxAllLogLine(line) == expected


@pytest.mark.parametrize(
    "line,expected",
    [
        (
            "231009_190145    14.074 Rx FT8    -231009_190215    14.074 Rx FT8     15  0.5  480 CQ MI0OBR IO74",
            ValueError,
        ),
    ],
)
def test_parseWsjtxAllLogLine_Error(line, expected):
    with pytest.raises(expected):
        parseWsjtxAllLogLine(line)


@pytest.mark.parametrize(
    "data,expected",
    [
        (
            """
231006_035145     3.573 Rx FT8     -9 -0.2 1446 LB2WD SP5AA -09
231006_035145     3.573 Rx FT8    -15  0.7 2319 NK9R 9A5TW RR73
231006_035200     3.573 Rx FT8    -10  0.9 1354 CQ DX SP2MKE JO93
231009_190145    14.074 Rx FT8    -231009_190215    14.074 Rx FT8     15  0.5  480 CQ MI0OBR IO74
foo bar baz
""",
            [
                Entry(
                    mode=Mode.FT8,
                    snr=-9,
                    frequency=3_574_446,
                    time=datetime.datetime.fromisoformat("2023-10-06 03:51:44.800"),
                    message="LB2WD SP5AA -09",
                    receiver_grid=RECEIVER_GRID,
                    receiver_callsign=RECEIVER_CALLSIGN,
                    sender_callsign="SP5AA",
                ),
                Entry(
                    mode=Mode.FT8,
                    snr=-15,
                    frequency=3_575_319,
                    time=datetime.datetime.fromisoformat("2023-10-06 03:51:45.700"),
                    message="NK9R 9A5TW RR73",
                    receiver_grid=RECEIVER_GRID,
                    receiver_callsign=RECEIVER_CALLSIGN,
                    sender_callsign="9A5TW",
                ),
                Entry(
                    mode=Mode.FT8,
                    snr=-10,
                    frequency=3_574_354,
                    time=datetime.datetime.fromisoformat("2023-10-06 03:52:00.900"),
                    message="CQ DX SP2MKE JO93",
                    receiver_grid=RECEIVER_GRID,
                    receiver_callsign=RECEIVER_CALLSIGN,
                    cq=True,
                    sender_callsign="SP2MKE",
                    sender_grid="JO93",
                ),
            ],
        )
    ],
)
def test_parseWsjtxAllLog(data, expected, tmp_path):
    with open(tmp_path / "ALL.TXT", "wt", encoding="utf8") as fh:
        fh.write(data)

    assert list(parseWsjtxAllLog(tmp_path / "ALL.TXT")) == expected


@pytest.mark.parametrize(
    "locator,expected",
    (
        ("PF01MAX", False),
        # RR73 is technically a valid locator in the archtic ocean,
        # but most often used for acknowledging end of contact.
        ("RR73", False),
        ("KN28LH", True),
        ("JO93", True),
        ("MH09me", True),
        ("JJ00aa00", True),
        ("II50aa00", True),
        ("AA00aa00", True),
        ("JQ78tf", True),
        ("EL29kn", True),
        ("JB17gx", True),

    ),
)
def test_is_locator(locator, expected):
    assert UDP_CONN.is_locator(locator) == expected
