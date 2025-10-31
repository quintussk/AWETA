import struct
from collections import UserDict
from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import snap7

from .parser import parse_db_file

from .type_definitions import AddressInfo, DBField

ElementalType = float | int | bool


class BufferMapping(UserDict):
    """A mapping that allows for easy access to a buffer of bytes.

    The buffer is Siemens S7 compatible (for unoptimised DB's), including the bit packing
    where multiple bools are packed into a single byte.
    """

    def __init__(self, buffer: bytearray, mapping: dict[str, AddressInfo]) -> None:
        super().__init__()
        self.buffer = buffer
        self.data = mapping

    def __getitem__(self, name: str) -> ElementalType:
        offset, format_char = self.data[name]

        # If the format_char is 'H' and the offset is a tuple, handle the bit-level extraction
        if format_char == "H" and isinstance(offset, tuple):
            byte_offset, bit_position = offset
            value = struct.unpack("<H", self.buffer[byte_offset : byte_offset + 2])[0]
            return bool((value >> bit_position) & 1)
        else:
            size = struct.calcsize(format_char)
            return struct.unpack(f">{format_char}", self.buffer[offset : offset + size])[0]

    def __setitem__(self, name: str, value: ElementalType) -> None:
        offset, format_char = self.data[name]
        # If the format_char is 'H' and the offset is a tuple, handle the bit-level assignment
        if format_char == "H" and isinstance(offset, tuple):
            byte_offset, bit_position = offset
            current_value = struct.unpack("<H", self.buffer[byte_offset : byte_offset + 2])[0]

            # Set or clear the bit based on value
            if value:
                current_value |= 1 << bit_position
            else:
                current_value &= ~(1 << bit_position)

            self.buffer[byte_offset : byte_offset + 2] = struct.pack("<H", current_value)
        else:
            size = struct.calcsize(format_char)
            self.buffer[offset : offset + size] = struct.pack(f">{format_char}", value)

    def __repr__(self) -> str:
        # return the unpacked values instead of the self.data field
        return {k: self[k] for k in self.data.keys()}.__repr__()


class S7DataBlock(BufferMapping):
    buffer: bytearray
    mapping: dict[str, tuple[int | tuple[int, int], str]]
    db_number: int
    db_size: int

    def __init__(
        self,
        buffer: bytearray,
        mapping: dict[str, AddressInfo],
        db_number: int,
        db_size: int,
    ):
        super().__init__(buffer, mapping)
        self.db_number = db_number
        self.db_size = db_size

    @staticmethod
    def fields_to_mapping(fields: Iterable[DBField]) -> tuple[dict[str, AddressInfo], int]:
        address = 0
        mapping = {}
        for field in fields:
            if isinstance(field.name_or_names, list):
                for bit, name in enumerate(field.name_or_names):
                    mapping[name] = AddressInfo((address, bit), field.format)
            else:
                mapping[field.name_or_names] = AddressInfo(address, field.format)
            address += struct.calcsize(field.format)

        return mapping, address

    @classmethod
    def from_fields(cls, fields: Iterable[DBField], db_number=None):
        mapping, size = cls.fields_to_mapping(fields)

        return cls(buffer=bytearray(size), db_number=db_number, db_size=size, mapping=mapping)

    @classmethod
    def from_definition_file(cls, path, db_number, nesting_depth_to_skip):
        _, fields, _ = parse_db_file(path, nesting_depth_to_skip=nesting_depth_to_skip)
        return cls.from_fields(fields, db_number)

    def pull(self, client: 'snap7.client.Client'):
        """
        Pulls the data from the external device and updates the internal buffer.

        Args:
            client (snap7.client.Client): The client to use for reading data.
        """
        self.buffer = client.db_read(db_number=self.db_number, start=0, size=self.db_size)

    def push(self, client: 'snap7.client.Client'):
        """
        Pushes the data from the internal buffer to the external device.

        Args:
            client (snap7.client.Client): The client to use for writing data.
        """
        client.db_write(db_number=self.db_number, start=0, data=self.buffer)


if __name__ == "__main__":
    # # Sample usage:
    buf = bytearray(10)
    var_mapping = {
        "enable1": AddressInfo((0, 0), "H"),
        "enable2": AddressInfo((0, 1), "H"),
        "enable3": AddressInfo((0, 2), "H"),
        "enable4": AddressInfo((0, 3), "H"),
        "enable5": AddressInfo((0, 4), "H"),
        "setpointHz2": AddressInfo(6, "f"),
    }

    buffered_vars = BufferMapping(buf, var_mapping)
    buffered_vars["enable2"] = True
    buffered_vars["setpointHz2"] = 23.5

    # from rich import print

    print(buffered_vars)
    print(buffered_vars.__repr__())