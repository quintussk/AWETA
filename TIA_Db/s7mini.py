#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minimalistische helper rond snap7 voor: connectie en DB-parsing.

Doel: een klein, herbruikbaar subsetje van 'snap7.util' zodat het
uitlezen/schrijven van Siemens DB's eenvoudiger en explicieter is.

Geen externe afhankelijkheden behalve 'snap7'. Alle functies werken op
bytes/bytearray en zijn eenvoudig te testen zonder PLC.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import struct


# ---------------- Bit helpers ----------------
def get_bool(buf: bytes | bytearray, byte_index: int, bit_index: int) -> bool:
    """Lees 1 bit uit buf[byte_index], 0 <= bit_index <= 7."""
    return bool((buf[byte_index] >> bit_index) & 0x01)


def set_bool(buf: bytearray, byte_index: int, bit_index: int, value: bool) -> None:
    """Zet 1 bit in-place in buf[byte_index]."""
    if value:
        buf[byte_index] |= (1 << bit_index)
    else:
        buf[byte_index] &= ~(1 << bit_index)


# ---------------- Integer/real helpers ----------------
def get_byte(buf: bytes | bytearray, byte_index: int) -> int:
    return buf[byte_index]


def set_byte(buf: bytearray, byte_index: int, value: int) -> None:
    buf[byte_index] = value & 0xFF


def get_int(buf: bytes | bytearray, byte_index: int) -> int:
    """S7 INT (16-bit signed, big-endian)."""
    return struct.unpack_from(">h", buf, byte_index)[0]


def set_int(buf: bytearray, byte_index: int, value: int) -> None:
    struct.pack_into(">h", buf, byte_index, int(value))


def get_uint(buf: bytes | bytearray, byte_index: int) -> int:
    """S7 UINT (16-bit unsigned, big-endian)."""
    return struct.unpack_from(">H", buf, byte_index)[0]


def set_uint(buf: bytearray, byte_index: int, value: int) -> None:
    struct.pack_into(">H", buf, byte_index, int(value) & 0xFFFF)


def get_dint(buf: bytes | bytearray, byte_index: int) -> int:
    """S7 DINT (32-bit signed, big-endian)."""
    return struct.unpack_from(">i", buf, byte_index)[0]


def set_dint(buf: bytearray, byte_index: int, value: int) -> None:
    struct.pack_into(">i", buf, byte_index, int(value))


def get_udint(buf: bytes | bytearray, byte_index: int) -> int:
    """S7 UDINT (32-bit unsigned, big-endian)."""
    return struct.unpack_from(">I", buf, byte_index)[0]


def set_udint(buf: bytearray, byte_index: int, value: int) -> None:
    struct.pack_into(">I", buf, byte_index, int(value) & 0xFFFFFFFF)


def get_real(buf: bytes | bytearray, byte_index: int) -> float:
    """S7 REAL (IEEE754 float32, big-endian)."""
    return struct.unpack_from(">f", buf, byte_index)[0]


def set_real(buf: bytearray, byte_index: int, value: float) -> None:
    struct.pack_into(">f", buf, byte_index, float(value))


# ---------------- S7 string helpers ----------------
def get_s7_string(buf: bytes | bytearray, byte_index: int) -> str:
    """
    S7 String (Standard): [MaxLen:uint8][CurLen:uint8][CurLen bytes data]
    """
    max_len = buf[byte_index]
    cur_len = min(buf[byte_index + 1], max_len)
    start = byte_index + 2
    end = start + cur_len
    return bytes(buf[start:end]).decode("latin1", errors="ignore")


def set_s7_string(buf: bytearray, byte_index: int, value: str, max_len: Optional[int] = None) -> None:
    data = value.encode("latin1", errors="ignore")
    if max_len is None:
        max_len = buf[byte_index]
    cur = min(len(data), max_len)
    buf[byte_index] = max_len & 0xFF
    buf[byte_index + 1] = cur & 0xFF
    start = byte_index + 2
    buf[start:start + cur] = data[:cur]
    # zero-pad rest van string area
    pad_to = start + max_len
    if pad_to > start + cur:
        buf[start + cur:pad_to] = b"\x00" * (pad_to - (start + cur))


# ---------------- Connection wrapper ----------------
@dataclass
class S7Client:
    ip: str
    rack: int = 0
    slot: int = 1
    _client: Optional[object] = None

    def connect(self) -> None:
        import snap7  # type: ignore
        self._client = snap7.client.Client()
        self._client.connect(self.ip, self.rack, self.slot)

    def is_connected(self) -> bool:
        return bool(self._client and self._client.get_connected())

    def ensure(self) -> None:
        if not self.is_connected():
            self.connect()

    def disconnect(self) -> None:
        try:
            if self._client and self._client.get_connected():
                self._client.disconnect()
        except Exception:
            pass

    # ---- DB IO ----
    def db_read(self, db_number: int, start: int, size: int) -> bytearray:
        self.ensure()
        data = self._client.db_read(db_number, start, size)
        return bytearray(data)

    def db_write(self, db_number: int, start: int, data: bytes | bytearray) -> None:
        self.ensure()
        self._client.db_write(db_number, start, bytes(data))


# ---------------- Convenience: bitmask lezen/schrijven ----------------
def set_bit_into(byte_val: int, bit_index: int, value: bool) -> int:
    return (byte_val | (1 << bit_index)) if value else (byte_val & ~(1 << bit_index))


__all__ = [
    # connection
    "S7Client",
    # bits
    "get_bool", "set_bool", "set_bit_into",
    # integers/reals
    "get_byte", "set_byte", "get_int", "set_int", "get_uint", "set_uint",
    "get_dint", "set_dint", "get_udint", "set_udint", "get_real", "set_real",
    # strings
    "get_s7_string", "set_s7_string",
]


