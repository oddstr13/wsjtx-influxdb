import datetime
from enum import Enum, auto
from typing import Iterable

from wsjtx_srv.wsjtx import UDP_Connector

from .utils import Entry, Mode
from .config import RECEIVER_CALLSIGN, RECEIVER_GRID


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

    class Tel:
        message: str

    tel = Tel()
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


class UdpConn(UDP_Connector):
    def __init__(self):
        pass


UDP_CONN = UdpConn()
