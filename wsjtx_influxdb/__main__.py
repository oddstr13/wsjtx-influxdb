#!/usr/bin/env python
from dataclasses import dataclass, asdict
from enum import Enum, auto
import socket
import datetime
import sys
from typing import Dict, Iterable, Optional, Tuple, Union
import urllib
from time import time as time_now_s
import requests

from wsjtx_srv.wsjtx import (
    WSJTX_Telegram as Telegram,
    WSJTX_Heartbeat as Heartbeat,
    WSJTX_Status as Status,
    WSJTX_Decode as Decode,
    WSJTX_Clear as Clear,
    WSJTX_Reply as Reply,
    WSJTX_WSPR_Decode as WSPRDecode,
    UDP_Connector,
)
import influxdb
import maidenhead
from pyproj import Geod


from .config import *
from .utils import frequencyToBand


def ratelimit(func):
    func.__last_call = None

    def wrapper(*args, ratelimit=1, **kwargs):
        now = time_now_s()
        if ratelimit is not None and func.__last_call is not None:
            if now - func.__last_call < ratelimit:
                func.__last_call = now
                # print(f"{func} has been rate limited.")
                return None
        func.__last_call = now
        return func(*args, **kwargs)

    return wrapper


class Mode(Enum):
    WSPR = 0
    FST4 = auto()
    FT4 = auto()
    FT8 = auto()
    JT4 = auto()
    JT9 = auto()
    JT65 = auto()
    Q65 = auto()
    MSK144 = auto()

    # Additional modes from pskreporter.info
    JS8 = auto()
    CW = auto()
    VARAC = auto()
    FST4W = auto()
    RTTY = auto()
    PSK31 = auto()
    OPERA = auto()
    PI4 = auto()
    OLIVIA8 = auto()
    FSQ = auto()
    ROS = auto()
    FREEDV = auto()
    SSB = auto()
    Q65B = auto()
    OLIVIA = auto()

    # Additional modes supported by fldigi
    PSK63 = auto()
    IFKP = auto()
    CONTESTIA = auto()
    DOMINOEX = auto()
    MFSK = auto()
    MT63 = auto()
    QPSK31 = auto()
    QPSK63 = auto()
    _8PSK125 = auto()
    PSKR = auto()
    SYNOP = auto()
    THOR = auto()
    SITORB = auto()
    THROB = auto()
    OFDM = auto()

    @staticmethod
    def from_wsjtx(wsjtx_encoded_mode: str):
        return WSJTX_MODE_MAP.get(wsjtx_encoded_mode)

    @classmethod
    def get(cls, name: str):
        if len(name) == 1:
            _wsjtx = cls.from_wsjtx(name)
            if _wsjtx:
                return _wsjtx

        upper_name = name.upper()
        if upper_name in cls.__members__:
            return cls[upper_name]

        stripped = dict(
            [(x.strip("_"), cls[x]) for x in cls.__members__.keys() if "_" in x]
        )
        if upper_name in stripped:
            return stripped[upper_name]

    def __str__(self):
        return self.name.strip("_")


# https://web.archive.org/web/20221213195227/https://physics.princeton.edu//pulsar/K1JT/wsjtx-doc/wsjtx-main-2.5.4.html#_decoded_lines
WSJTX_MODE_MAP = {
    "`": Mode.FST4,
    "+": Mode.FT4,
    "~": Mode.FT8,
    "$": Mode.JT4,
    "@": Mode.JT9,
    "#": Mode.JT65,
    ":": Mode.Q65,
    "&": Mode.MSK144,
}

geod = Geod(ellps="WGS84")


@dataclass
class DecimalDegrees:
    latitude: float
    longitude: float

    @classmethod
    def fromGridsquare(cls, gridsquare: str, center: bool = True):
        latitude, longitude = maidenhead.to_location(gridsquare, center=center)
        return cls(latitude=latitude, longitude=longitude)

    def toGridsquare(self, precission=3):
        return maidenhead.to_maiden(
            lat=self.latitude, lon=self.longitude, precision=precission
        )


def calculate_qth_distance_bearing(
    qth_from: str, qth_to: str, center: bool = True
) -> Tuple[int, float]:
    dec_from = DecimalDegrees.fromGridsquare(qth_from, center=center)
    dec_to = DecimalDegrees.fromGridsquare(qth_to, center=center)

    # pskreporter.info is using simple sphere calculations, we use WGS84.
    # bearing, rev, distance = Geod(ellps="sphere").inv(from_lon, from_lat, to_lon, to_lat)

    bearing, _reverse_bearing, distance = geod.inv(
        dec_from.longitude, dec_from.latitude, dec_to.longitude, dec_to.latitude
    )

    # Convert from ±180° to 0-360°
    if bearing < 0:
        bearing = 180 - abs(bearing) + 180

    return int(distance), bearing


def parse_time(time: int, offset: float):
    now = datetime.datetime.utcnow()
    yesterday = now - datetime.timedelta(days=1)

    seconds, ms = divmod(time, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    tm = datetime.time(hour=hours, minute=minutes, second=seconds, microsecond=ms)
    # print(tm.isoformat())
    now_dt = datetime.datetime.combine(now.date(), tm)
    yesterday_dt = datetime.datetime.combine(yesterday.date(), tm)

    # print(now_dt, yesterday_dt)
    now_diff = abs(now - now_dt)
    yesterday_diff = abs(now - yesterday_dt)
    # print(now_diff, yesterday_diff)

    if now_diff < yesterday_diff:
        stamp = now_dt
    else:
        stamp = yesterday_dt

    stamp += datetime.timedelta(seconds=offset)

    return stamp


def parse_influxdb_url(influxdb_url: str):
    url = urllib.parse.urlsplit(influxdb_url)
    host, port = urllib.parse.splitport(url.netloc)
    https = url.scheme == "https"
    if port is None:
        port = 443 if https else 80

    return {"host": host, "port": port, "path": url.path}


# Status dial_frq=14074000 mode=FT8 dx_call=ZD9W report=0 tx_mode=FT8 tx_enabled=0 xmitting=0 decoding=0 rx_df=1500 tx_df=1500 de_call=SWL de_grid=MH09me dx_grid=None tx_watchdog=0 sub_mode=None fast_mode=0 special_op=0 frq_tolerance=4294967295 t_r_period=4294967295 config_name=Default tx_message=None


@dataclass
class Entry:
    mode: Mode
    snr: int
    frequency: int
    message: str
    time: datetime.datetime
    receiver_grid: str
    receiver_callsign: str

    sender_grid: Optional[str] = None
    sender_callsign: Optional[str] = None
    target_callsign: Optional[str] = None

    cq: bool = False

    @property
    def distance(self) -> Optional[int]:
        return calculate_qth_distance_bearing(self.receiver_grid, self.sender_grid)[0]

    @property
    def heading(self) -> Optional[float]:
        return calculate_qth_distance_bearing(self.receiver_grid, self.sender_grid)[1]

    @property
    def sender_coordinates(self) -> Optional[DecimalDegrees]:
        if self.sender_grid:
            return DecimalDegrees.fromGridsquare(self.sender_grid)

    @property
    def band_name(self) -> Optional[str]:
        return frequencyToBand(self.frequency)

    def __str__(self):
        return f"{self.time}\t{self.snr:> 2d}\t{self.mode}\t{self.frequency/1000: 8.3f} kHz\t{self.message}"


def entryToInfluxdb(entry: Entry):
    m: Dict[str, Union[str, dict]] = {
        "measurement": "entry",
        "time": entry.time.isoformat(),
    }
    m["tags"]: Dict[str, Union[str, int, float, bool]] = {}
    m["fields"]: Dict[str, Union[str, int, float, bool]] = {}

    m["tags"]["mode"] = str(entry.mode)
    m["tags"]["cq"] = entry.cq
    # TODO: Should be field if many receivers are expected
    m["tags"]["receiver_grid"] = entry.receiver_grid
    # TODO: Should be field if many receivers are expected
    m["tags"]["receiver_callsign"] = entry.receiver_callsign

    m["tags"]["received_hour"] = entry.time.hour
    m["tags"]["received_month"] = entry.time.month
    m["tags"]["received_year"] = entry.time.year
    (
        m["tags"]["received_isoyear"],
        m["tags"]["received_isoweek"],
        m["tags"]["received_isoweekday"],
    ) = entry.time.isocalendar()

    m["fields"]["snr"] = entry.snr
    m["tags"]["snr"] = entry.snr
    m["fields"]["frequency"] = entry.frequency
    m["fields"]["message"] = entry.message

    band = entry.band_name
    if band:
        m["tags"]["band"] = band

    if entry.sender_grid:
        m["tags"]["has_sender_grid"] = True
        m["fields"]["distance"] = entry.distance
        m["fields"]["heading"] = entry.heading
        m["tags"]["heading"] = int(entry.heading)
        m["fields"]["sender_grid"] = entry.sender_grid

        coords = entry.sender_coordinates
        m["fields"]["sender_latitude"] = coords.latitude
        m["fields"]["sender_longitude"] = coords.longitude
        del coords

    else:
        m["tags"]["has_sender_grid"] = False

    if entry.sender_callsign:
        m["fields"]["sender_callsign"] = entry.sender_callsign

    if entry.target_callsign:
        m["fields"]["target_callsign"] = entry.target_callsign

    return m


def sortEntries(entries: Iterable[Entry]):
    return sorted(entries, key=lambda e: (e.time, e.frequency))


def entriesOlderThan(entries: Iterable[Entry], seconds=5):
    now = datetime.datetime.utcnow()
    td = datetime.timedelta(seconds=seconds)
    return filter(lambda e: now - e.time > td, entries)


class BasicClass:
    pass


class UdpConn(UDP_Connector):
    def __init__(self):
        pass


UDP_CONN = UdpConn()


def parseWsjtMessage(message: str):
    msplit = message.strip().split()
    cq = msplit[0].upper() == "CQ"
    if len(msplit) > 1 and msplit[1].upper() == "DX":
        msplit.pop(1)
    # TODO: implement full message parsing
    # TZ3LTD/P JG4AMP/P R EC88
    # 8P6GE RA4NCC LO68
    # KK4CQN RA6ABO R-04
    # CQ R7DX KN84
    # KA6BIM UN7JO +05
    # KE0LCS R7DX -15
    # YI3WHR RK4HP 73
    # K6BRN RZ6L RR73
    # ZL2BX <...> -09
    # RV3HSG EK5AUA/R DO88
    # <N6BCE> R0FBA/9
    # RC0AT <R0FBA/9> +08
    # <SV8EUL> <...> R 520305 LG83SK

    tel = BasicClass()
    tel.message = message

    sender_callsign = UDP_CONN.parse_message(tel)
    sender_grid = None
    if cq and len(msplit) == 3:
        if UDP_CONN.is_locator(msplit[2]):
            sender_grid = msplit[2]

    return cq, sender_callsign, sender_grid


def parseWsjtxAllLog(file_path: str) -> Iterable[Entry]:
    with open(file_path, "r", encoding="utf8") as fh:
        for line in fh:
            try:
                line = line.strip()
                data = line.split(maxsplit=7)
                if len(data) < 8:
                    print(data)
                    continue
                # ['231006_035100', '3.573', 'Rx', 'FT8', '-16', '0.6', '2753', 'CQ DX F4BKV IN95']
                (
                    raw_time,
                    raw_freq,
                    _,
                    raw_mode,
                    raw_snr,
                    raw_time_offset,
                    raw_freq_offset,
                    message,
                ) = data

                message = message.strip()
                if not message:
                    continue

                cq, sender_callsign, sender_grid = parseWsjtMessage(message)

                entry = Entry(
                    mode=Mode.get(raw_mode),
                    snr=int(raw_snr),
                    frequency=int(float(raw_freq) * 1000000 + int(raw_freq_offset)),
                    message=message,
                    time=datetime.datetime.strptime(raw_time, "%y%m%d_%H%M%S")
                    + datetime.timedelta(seconds=float(raw_time_offset)),
                    cq=cq,
                    sender_callsign=sender_callsign,
                    sender_grid=sender_grid,
                    receiver_grid=RECEIVER_GRID,
                    receiver_callsign=RECEIVER_CALLSIGN,
                )
                yield entry
            except ValueError:
                print(line)


@ratelimit
def influxPushData(entries: Iterable[Entry]) -> Optional[Iterable[Entry]]:
    """
    Pushes entries to InfluxDB (if they're old enough)
    Returns list of entries NOT pushed, or None
    """
    print("Processing…")
    to_push = sortEntries(entriesOlderThan(entries))
    left = list(entries)
    for entry in to_push:
        left.remove(entry)

    points = map(entryToInfluxdb, to_push)
    try:
        print(f"Writing {len(to_push)} entries…")
        influxdb_client.write_points(
            points=points, database=INFLUXDB_DATABASE, batch_size=100
        )
    except requests.exceptions.RequestException as ex:
        print(f"Failed to write data: {ex}")
        return None

    print("Done processing.")
    return left


if __name__ == "__main__":
    reprocess = "--reprocess" in sys.argv

    influxdb_client = influxdb.InfluxDBClient(
        **parse_influxdb_url(INFLUXDB_URL), database=INFLUXDB_DATABASE
    )
    if reprocess:
        influxdb_client.drop_database(INFLUXDB_DATABASE)
    influxdb_client.create_database(INFLUXDB_DATABASE)

    # u = wsjtx_srv.UDP_Connector(ip = "0.0.0.0", wbf = None)
    entry_queue: list[Entry] = []

    def processQueue():
        if entry_queue:
            if len(entry_queue) >= 1000:
                res = influxPushData(entry_queue, ratelimit=None)
            else:
                res = influxPushData(entry_queue)
            if res is not None:
                entry_queue.clear()
                entry_queue.extend(res)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("", 2237))

        if reprocess:
            for entry in parseWsjtxAllLog("ALL.TXT"):
                entry_queue.append(entry)
                processQueue()

        dial_frequency = 0
        local_grid: str = RECEIVER_GRID
        local_call: str = RECEIVER_CALLSIGN

        # Status dial_frq=14074000 mode=FT8 dx_call=ZD9W report=0 tx_mode=FT8 tx_enabled=0 xmitting=0 decoding=1 rx_df=2259 tx_df=1500 de_call=SWL de_grid=MH09me dx_grid=None tx_watchdog=0 sub_mode=None fast_mode=0 special_op=0 frq_tolerance=4294967295 t_r_period=4294967295 config_name=Default tx_message=None
        # Decode is_new=1 time=81810000 snr=-20 delta_t=0.5 delta_f=1709 mode=~ message=CQ SV5AZP KM46 low_confidence=0 off_air=0

        while True:
            processQueue()

            data, address = sock.recvfrom(4096)
            # print(address, data)
            tel = Telegram.from_bytes(data)
            if type(tel) not in [Status, Decode]:
                if type(tel) is not Heartbeat:
                    print(tel)
                continue

            if isinstance(tel, Status):
                if tel.dial_frq != dial_frequency:
                    print(
                        f"{datetime.datetime.utcnow()}\tFrequency changed\t{tel.dial_frq/1000:8.3f} kHz"
                    )
                dial_frequency = tel.dial_frq
                local_grid = tel.de_grid
                local_call = tel.de_call
                continue

            elif isinstance(tel, Decode):
                if not dial_frequency:
                    continue

                if tel.off_air or not tel.is_new:
                    continue

                if tel.low_confidence:
                    print(tel)
                    continue

                if tel.message is None:
                    print(tel)
                    continue

                cq, sender_callsign, sender_grid = parseWsjtMessage(tel.message)

                entry = Entry(
                    message=tel.message,
                    mode=Mode.get(tel.mode),
                    snr=int(tel.snr),
                    frequency=dial_frequency + tel.delta_f,
                    time=parse_time(tel.time, tel.delta_t),
                    receiver_grid=local_grid,
                    receiver_callsign=local_call,
                    cq=cq,
                    sender_callsign=sender_callsign,
                    sender_grid=sender_grid,
                )

                print(entry)
                entry_queue.append(entry)
                # print(asdict(entry))

            elif isinstance(tel, WSPRDecode):
                if tel.off_air or not tel.is_new:
                    continue
                # WSPR_Decode is_new=1 time=7680000 snr=-25 delta_t=0.6000000238418579 frq=10140138 drift=0 callsign=IU2PJI grid=JN45 power=23 off_air=0
                mode = Mode.WSPR
                snr = tel.wspr
                time = parse_time(tel.time, tel.delta_t)
                freq = tel.frq
                message = f"WSPR {tel.callsign} {tel.grid} {tel.power}"

                print(f"{time}\t{snr:> 2d}\t{mode}\t{freq/1000: 8.3f} kHz\t{message}")

            else:
                print(tel)

    # calculate and log heading, distance
    # sumarize per minute, hour: number of messages per mode and total
