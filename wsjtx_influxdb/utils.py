import datetime
from collections import namedtuple
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, auto
from typing import Dict, Optional, TextIO, Tuple, Union
from functools import cache, lru_cache
from importlib import resources

from pyproj import Geod
import maidenhead  # type: ignore [import]

NumberType = Union[int, float, Decimal]


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
        if self.sender_grid:
            return calculate_qth_distance_bearing(
                self.receiver_grid, self.sender_grid
            ).distance
        return None

    @property
    def heading(self) -> Optional[float]:
        if self.sender_grid:
            return calculate_qth_distance_bearing(
                self.receiver_grid, self.sender_grid
            ).bearing
        return None

    @property
    def sender_coordinates(self) -> Optional[DecimalDegrees]:
        if self.sender_grid:
            return DecimalDegrees.fromGridsquare(self.sender_grid)
        return None

    @property
    def band_name(self) -> Optional[str]:
        return frequencyToBand(self.frequency)

    def __str__(self):
        return f"{self.time}\t{self.snr:> 2d}\t{self.mode}\t{self.frequency/1000: 8.3f} kHz\t{self.message}"


class FrequencyRange(namedtuple("FrequencyRange", ["minimum", "maximum"])):
    minimum: NumberType
    maximum: NumberType

    def contains(self, frequency: NumberType) -> bool:
        return frequency >= self.minimum and frequency <= self.maximum

    def __contains__(self, __key: object) -> bool:
        if isinstance(__key, NumberType.__args__):  # type: ignore [attr-defined]
            return self.contains(__key)
        return super().__contains__(__key)


def frequencyToBand(frequency: int) -> Optional[str]:
    for name, frequency_range in getBandplan().items():
        if frequency in frequency_range:
            return name
    print(f"Unknown band: {frequency}")
    return None


@cache
def getBandplan() -> Dict[str, FrequencyRange]:
    from . import data

    bandplan_file = resources.files(data) / "bandplan_MHz.csv"
    with bandplan_file.open("r", encoding="utf8") as fh:
        return parseBandplanCsv(fh)


def parseBandplanCsv(file_handle: TextIO) -> Dict[str, FrequencyRange]:
    _bandplan = {}
    for line in file_handle:
        line = line.strip()
        if line:
            name, min_frequency, max_frequency = line.split(";")
            _bandplan[name] = FrequencyRange(
                int(float(min_frequency) * 1000000),
                int(float(max_frequency) * 1000000),
            )
            print(name, _bandplan[name])
    return _bandplan


geod = Geod(ellps="WGS84")


class DistanceBearing(namedtuple("DistanceBearing", ["distance", "bearing"])):
    distance: int
    bearing: float


@lru_cache(maxsize=512)
def calculate_qth_distance_bearing(
    qth_from: str, qth_to: str, center: bool = True
) -> DistanceBearing:
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

    return DistanceBearing(int(distance), bearing)
