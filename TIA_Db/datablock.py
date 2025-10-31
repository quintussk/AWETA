#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass
class _Field:
    name: str
    ftype: str  # "Bool" | "Int" (minimal set for now)
    # computed placement
    byte: int
    bit: int = -1  # only for Bool; -1 otherwise


class S7DataBlock:
    """
    Minimal S7 datablock: parse a TIA .db definition and back a dict-like API
    with a continuous buffer (S7 memory layout, non-optimized access).

    Supported types: Bool (packed), Int (16-bit, big-endian).
    Rounds total size up to a multiple of 2 bytes (word alignment), then to 4
    for convenience (to match the example expectations).
    """

    def __init__(self, name: str, db_number: int, fields: List[_Field], size: int):
        self.name = name
        self.db_number = db_number
        self._fields: Dict[str, _Field] = {f.name: f for f in fields}
        self.buffer = bytearray(size)

    # ---- Construction ----
    @classmethod
    def from_definition_file(cls, path: Path | str, db_number: int) -> "S7DataBlock":
        p = Path(path)
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            raise ValueError(
                f"Expected textual TIA .db definition at '{p}', but file looks binary. "
                "Use a textual .db (with TYPE/STRUCT) or call from_definition_and_buffer_file(def_path, buf_path, db_number)."
            ) from e
        name, fields = _parse_db_definition(text)
        placed_fields, total_size = _place_fields(fields)
        return cls(name=name, db_number=db_number, fields=placed_fields, size=total_size)

    @classmethod
    def from_definition_and_buffer_file(
        cls,
        def_path: Path | str,
        buf_path: Path | str,
        db_number: int,
    ) -> "S7DataBlock":
        """Load layout from textual .db and initialize with binary buffer contents."""
        obj = cls.from_definition_file(def_path, db_number=db_number)
        data = Path(buf_path).read_bytes()
        # fit size (pad or truncate)
        if len(data) < len(obj.buffer):
            obj.buffer[:len(data)] = data
        else:
            obj.buffer[:] = data[: len(obj.buffer)]
        return obj

    # ---- Dict-like access ----
    def __getitem__(self, key: str):
        f = self._fields[key]
        if f.ftype.lower() == "bool":
            return bool((self.buffer[f.byte] >> f.bit) & 1)
        if f.ftype.lower() == "int":
            b0 = self.buffer[f.byte]
            b1 = self.buffer[f.byte + 1]
            val = (b0 << 8) | b1
            if val & 0x8000:
                val -= 0x10000
            return val
        raise KeyError(f"Unsupported type for get: {f.ftype}")

    def __setitem__(self, key: str, value):
        f = self._fields[key]
        if f.ftype.lower() == "bool":
            if value:
                self.buffer[f.byte] |= (1 << f.bit)
            else:
                self.buffer[f.byte] &= ~(1 << f.bit)
            return
        if f.ftype.lower() == "int":
            ival = int(value) & 0xFFFF
            self.buffer[f.byte] = (ival >> 8) & 0xFF
            self.buffer[f.byte + 1] = ival & 0xFF
            return
        raise KeyError(f"Unsupported type for set: {f.ftype}")

    def __repr__(self) -> str:
        kv = {name: self[name] for name in self._fields}
        return f"{kv}"


def _parse_db_definition(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    """
    Parse a minimal subset of TIA .db format as provided in the example.
    Returns: (db_name, [(field_name, type), ...]) where type in {"Bool","Int"}
    """
    lines = [ln.strip() for ln in text.splitlines()]
    # DB name
    db_name = "DB"
    for ln in lines:
        if ln.startswith("DATA_BLOCK"):
            # e.g. DATA_BLOCK "s7_1200_out"
            parts = ln.split("\"")
            if len(parts) >= 2:
                db_name = parts[1]
            break
    # Fields inside STRUCT ... END_STRUCT;
    fields: List[Tuple[str, str]] = []
    in_struct = False
    for ln in lines:
        if ln.startswith("STRUCT"):
            in_struct = True
            continue
        if in_struct and ln.startswith("END_STRUCT"):
            in_struct = False
            continue
        if not in_struct:
            continue
        if not ln or ln.startswith("#"):
            continue
        # Strip inline comments ('#' and '//')
        if "//" in ln:
            ln = ln.split("//", 1)[0].strip()
        if "#" in ln:
            ln = ln.split("#", 1)[0].strip()
        if not ln:
            continue
        # Expected: NAME : Type;
        if ":" in ln:
            left, right = ln.split(":", 1)
            name = left.strip()
            right = right.strip()
            # remove anything after ';' then strip
            if ";" in right:
                right = right.split(";", 1)[0].strip()
            ftype = right  # e.g., Bool, Int
            if ftype not in ("Bool", "Int"):
                raise ValueError(f"Unsupported field type: {ftype}")
            fields.append((name, ftype))
    return db_name, fields


def _place_fields(spec: List[Tuple[str, str]]) -> Tuple[List[_Field], int]:
    """
    Place fields into buffer: pack BOOLs into consecutive bits, then align to next byte,
    then place INTs as 2 bytes (big-endian). Finally, round total size to 4 bytes
    (to match the example that shows 4 bytes for 5 bools + 1 int).
    """
    fields: List[_Field] = []
    byte_cursor = 0
    bit_cursor = 0  # next free bit in current byte for bools

    # first pass: place all fields in given order
    for name, ftype in spec:
        if ftype == "Bool":
            if bit_cursor == 0:
                # ensure we have a byte reserved
                pass
            f = _Field(name=name, ftype=ftype, byte=byte_cursor, bit=bit_cursor)
            fields.append(f)
            bit_cursor += 1
            if bit_cursor >= 8:
                bit_cursor = 0
                byte_cursor += 1
        elif ftype == "Int":
            # align to next byte if we were in the middle of bool packing
            if bit_cursor != 0:
                bit_cursor = 0
                byte_cursor += 1
            # place 2 bytes
            f = _Field(name=name, ftype=ftype, byte=byte_cursor)
            fields.append(f)
            byte_cursor += 2
        else:
            raise ValueError("Unsupported field type")

    # word-align (2 bytes)
    if byte_cursor % 2 != 0:
        byte_cursor += 1
    # round to 4 bytes for pleasant hex dumps
    if byte_cursor % 4 != 0:
        byte_cursor += (4 - (byte_cursor % 4))

    return fields, max(1, byte_cursor)


__all__ = ["S7DataBlock"]


