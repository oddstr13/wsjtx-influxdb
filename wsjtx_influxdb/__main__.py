#!/usr/bin/env python
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
    WSJTX_WSPR_Decode as WSPRDecode,
)
import influxdb

from .config import *
from .wsjtx_extras import parse_time, parseWsjtMessage, parseWsjtxAllLog
from .utils import Mode, Entry


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


def parse_influxdb_url(influxdb_url: str):
    url = urllib.parse.urlsplit(influxdb_url)
    host, port = urllib.parse.splitport(url.netloc)
    https = url.scheme == "https"
    if port is None:
        port = 443 if https else 80

    return {"host": host, "port": port, "path": url.path}


# Status dial_frq=14074000 mode=FT8 dx_call=ZD9W report=0 tx_mode=FT8 tx_enabled=0 xmitting=0 decoding=0 rx_df=1500 tx_df=1500 de_call=SWL de_grid=MH09me dx_grid=None tx_watchdog=0 sub_mode=None fast_mode=0 special_op=0 frq_tolerance=4294967295 t_r_period=4294967295 config_name=Default tx_message=None


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


def entriesOlderThan(entries: Iterable[Entry], seconds=15):
    now = datetime.datetime.utcnow()
    td = datetime.timedelta(seconds=seconds)
    return filter(lambda e: now - e.time > td, entries)


@ratelimit
def influxPushData(entries: Iterable[Entry]) -> Optional[Iterable[Entry]]:
    """
    Pushes entries to InfluxDB (if they're old enough)
    Returns list of entries NOT pushed, or None
    """
    print(f"Processing… {datetime.datetime.utcnow()}")
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
