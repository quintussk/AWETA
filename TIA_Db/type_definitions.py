from typing import Literal, NamedTuple

import pandas as pd

MeasurementType = Literal["Bool", "Float32", "Float64", "Int16", "Int32", "UInt16", "UInt32", "String"]

S7Type = Literal[
    "Real",
    "DReal",
    "Int",
    "DInt",
    "Byte",
    "Word",
    "DWord",
    "Bool",
    "Char",
    "S5Time",
    "Time",
    "Date",
    "Time_of_Day",
    "DTL",
    "UDInt",
]


class Measurement(NamedTuple):
    type: MeasurementType
    time: pd.Timestamp
    key: str
    value: float | int | bool

    def __str__(self):
        return f"{self.key:40s}{self.type:10s}{self.value}"


StructFormatChar = Literal["?", "B", "c", "d", "f", "h", "H", "i", "I", "D", "12c"]


class DBField(NamedTuple):
    name_or_names: str | list[str]
    type: S7Type
    format: StructFormatChar


class DBFormat(NamedTuple):
    format: str
    fields: list[DBField]
    size: int


class NameType(NamedTuple):
    name: list[str]
    type: S7Type


class AddressInfo(NamedTuple):
    address: int | tuple[int, int]
    format: StructFormatChar


class FieldDescriptor(NamedTuple):
    name: str
    address_info: AddressInfo