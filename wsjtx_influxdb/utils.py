from collections import namedtuple
from decimal import Decimal
from typing import Dict, Optional, TextIO, Tuple, Union
from functools import cache
from importlib import resources

NumberType = Union[int, float, Decimal]


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
