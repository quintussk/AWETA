# functions to parse a db definition exported from TIA Portal, read a db and intrpret the data
import struct
from collections.abc import Iterator
from copy import deepcopy
from functools import reduce
from operator import or_
from pathlib import Path
from typing import Any, get_args

from pyparsing import CaselessKeyword, Combine, Dict, Forward, Group, OneOrMore
from pyparsing import Opt as Optional  # workaround for mypy bug
from pyparsing import Regex, Suppress, Word, ZeroOrMore, alphanums, alphas, nums

from TIA_Db.type_definitions import DBField, DBFormat, NameType, S7Type

# Define grammar
QUOTE = Suppress(Word("'\""))
UNQUOTED_IDENT = Word(f"{alphas}_", f"{alphanums}_")
QUOTED_IDENT = QUOTE + Word(f"{alphanums}_. ") + QUOTE
IDENT = QUOTED_IDENT | UNQUOTED_IDENT
REAL = Regex(r"\d+\.\d*")
INT = Regex(r"\d+")
LBRACE, RBRACE, SEMI, COLON = map(Suppress, "{};:")
LBRACKET, RBRACKET = map(Suppress, "[]")
EQUALS = Suppress(":=")
BOOLEAN = CaselessKeyword("True") | CaselessKeyword("False")
COMMENT = Suppress("//" + Regex(r".*"))
POINT = Suppress(".")
hex_prefix = Combine(Word(nums) + "#")
hex_digits = Word(nums + "ABCDEFabcdef")
HEX = Combine(hex_prefix + hex_digits)
VALUE = BOOLEAN | HEX | REAL | INT

# basic dtype can be any of the S7Type
S7_DTYPE = reduce(or_, map(CaselessKeyword, get_args(S7Type)))

# duration can be T#5M or T#5s, T#10M
DURATION = Regex(r"T#\d+[sMHmsdh]")
optional_attribute_assignments = Suppress(
    Optional(
        LBRACE + ZeroOrMore(IDENT + EQUALS + QUOTE + (BOOLEAN | S7_DTYPE | REAL) + QUOTE + Optional(SEMI)) + RBRACE
    )
)

date = IDENT + optional_attribute_assignments

value_assignment = EQUALS + (REAL | BOOLEAN | INT | DURATION)
optional_default_value = Suppress(Optional(expr=value_assignment, default=None))

struct_def = Forward()

# Array syntax: Array[lower..upper] of <type>
# lower and upper can be INT or QUOTED_IDENT (like "2")
array_bounds = INT("lower") + Suppress("..") + (INT | QUOTED_IDENT)("upper")
array_def = (
    CaselessKeyword("Array")
    + LBRACKET
    + array_bounds
    + RBRACKET
    + Suppress(CaselessKeyword("of"))
    + (QUOTED_IDENT | struct_def)("array_type")
)

# Type can be: basic S7 type, quoted identifier (type reference), inline struct, or array
type_spec = (S7_DTYPE + optional_default_value + SEMI) | (QUOTED_IDENT + SEMI) | struct_def | (array_def + SEMI)

struct_element = Dict(
    Group(
        Optional(date)
        + Optional(IDENT)
        + optional_attribute_assignments
        + COLON
        + Optional(type_spec)
    )  # if first:
    #     first = False
    #     await asyncio.sleep(HEATZONE_SIDE_EFFECT_TIME)
    + Optional(COMMENT)
)

struct_def << (
    Suppress(CaselessKeyword("STRUCT"))
    + Optional(COMMENT)
    + Group(OneOrMore(struct_element))
    + Suppress(CaselessKeyword("END_STRUCT"))
    + SEMI
)


# Define 'TYPE' grammar
type_def = Dict(
    Group(
        Suppress("TYPE")
        + IDENT
        + Suppress("VERSION")
        + COLON
        + Suppress(REAL("version"))
        + struct_def
        + Suppress("END_TYPE")
    )
)


var_def = Dict(
    Group(
        Suppress(CaselessKeyword("VAR"))
        + ZeroOrMore(struct_element)
        + Group(OneOrMore(struct_element))
        + Suppress("END_VAR")
    )
)

default_value_element = Group(ZeroOrMore(IDENT + POINT) + IDENT + Suppress(EQUALS) + VALUE + Suppress(SEMI)) + Group(
    ZeroOrMore(Suppress(EQUALS) + VALUE + Suppress(SEMI))
)

defaults_values_block = Dict(
    Group(Suppress(CaselessKeyword("BEGIN")) + ZeroOrMore(default_value_element) + Suppress("END_DATA_BLOCK"))
)("BEGIN")

# Define 'DATA_BLOCK' grammar
data_block_def = Dict(
    Group(
        Suppress("DATA_BLOCK")
        + QUOTE
        + IDENT
        + QUOTE
        + optional_attribute_assignments
        + Suppress("VERSION")
        + COLON
        + Suppress(REAL)
        + Suppress(Optional(CaselessKeyword("NON_RETAIN")))
        + (var_def | struct_def | QUOTED_IDENT)
    )
)("DATA_BLOCK")

program = Group(ZeroOrMore(type_def))("TYPES") + data_block_def + defaults_values_block

# fmt: off
s7_dtype_mapping: dict[S7Type, dict] = {
    "Real": {"struct": "f", "measurement_type": "Float32"},  # single-precision float
    "DReal": {"struct": "d", "measurement_type": "Float64"},  # double-precision float
    "Int": {"struct": "h", "measurement_type": "Int16"},  # 16-bit signed integer
    "DInt": {"struct": "i", "measurement_type": "Int32"},  # 32-bit signed integer
    "Byte": {"struct": "B", "measurement_type": "UInt8"},  # 8-bit unsigned integer
    "Word": {"struct": "H", "measurement_type": "UInt16"},  # 16-bit unsigned integer
    "DWord": {"struct": "I", "measurement_type": "UInt32"},  # 32-bit unsigned integer
    "Bool": {"struct": "?", "measurement_type": "Bool"},  # boolean
    "Char": {"struct": "c", "measurement_type": "Char"},  # char
    "S5Time": {"struct": "H", "measurement_type": "UInt16"},  # 16-bit value, time in steps of 10ms
    "Time": {"struct": "i", "measurement_type": "Int32"},  # 32-bit value, time in steps of 1ms (signed integer)
    "Date": {"struct": "H", "measurement_type": "UInt16"},  # 16-bit value, days since 1990-1-1
    "Time_of_Day": {"struct": "I", "measurement_type": "UInt32"},  # 32-bit value, time in steps of 1ms
    "UDInt": {"struct": "i", "measurement_type": "Int32"},  # 32-bit signed integer
}
# fmt: on

s7_dtype_to_struct_mapping = {k: v["struct"] for k, v in s7_dtype_mapping.items()}
s7_dtype_to_measurement_mapping: dict = {k: v["measurement_type"] for k, v in s7_dtype_mapping.items()}


def resolve_data_types(types: dict[str, Any], prefix: list[str], d: Any) -> Iterator[tuple[list[str], Any]]:
    # Check if this is an array definition (has all three required keys)
    if isinstance(d, dict) and "lower" in d and "upper" in d and "array_type" in d:
        # This is an array: Array[lower..upper] of <type>
        # Handle lower (should be int or string)
        lower_val = d["lower"]
        if isinstance(lower_val, list) and len(lower_val) > 0:
            lower_str = str(lower_val[0])
        else:
            lower_str = str(lower_val)
        try:
            lower = int(lower_str)
        except ValueError:
            lower = int(''.join(filter(str.isdigit, lower_str)) or "1")
        
        # Handle upper (can be list from QUOTED_IDENT)
        upper_val = d["upper"]
        if isinstance(upper_val, list) and len(upper_val) > 0:
            upper_str = str(upper_val[0]).strip('"\'')
        else:
            upper_str = str(upper_val).strip('"\'')
        try:
            upper = int(upper_str)
        except ValueError:
            upper = int(''.join(filter(str.isdigit, upper_str)) or "1")
        
        # Handle array_type (can be list from QUOTED_IDENT)
        array_type_val = d["array_type"]
        if isinstance(array_type_val, list) and len(array_type_val) > 0:
            array_type_name = str(array_type_val[0]).strip('"\'')
        else:
            array_type_name = str(array_type_val).strip('"\'')
        
        # Resolve array_type from types dict
        if array_type_name in types:
            array_type = types[array_type_name]
        else:
            # If not found in types, treat as base type
            array_type = array_type_name
        
        # Expand array: for each index from lower to upper, recursively resolve the type
        for idx in range(lower, upper + 1):
            array_index_prefix = prefix + [f"[{idx}]"]
            yield from resolve_data_types(types, array_index_prefix, array_type)
        return
    
    if isinstance(d, dict):
        # Check if this dict might be an array definition before iterating
        # If not an array, process as normal nested structure
        for k, v in d.items():
            yield from resolve_data_types(types, prefix + [k], v)
    elif isinstance(d, str):
        # Check if this is a type reference (quoted identifier)
        if d in types:
            yield from resolve_data_types(types, prefix, deepcopy(types[d]))
        else:
            # Not a type reference, treat as base type
            yield prefix, d
    else:
        if d == "DTL":
            # now we need to unpack a date time struct from Siemens
            yield prefix + ["YEAR"], "Word"
            yield prefix + ["MONTH"], "Byte"
            yield prefix + ["DAY"], "Byte"
            yield prefix + ["WEEKDAY"], "Byte"
            yield prefix + ["HOUR"], "Byte"
            yield prefix + ["MINUTE"], "Byte"
            yield prefix + ["SECOND"], "Byte"
            yield prefix + ["NANOSECOND"], "DWord"
        else:
            yield prefix, d


def _join_name_parts(parts: list[str], delimiter: str = ".") -> str:
    """Join name parts, handling array indices specially.
    
    Array indices (parts starting with '[') are appended to the previous part
    without a delimiter. Example: ['InfeedBelt', '[1]', 'I_FT_In'] -> 'InfeedBelt[1].I_FT_In'
    """
    if not parts:
        return ""
    result = [parts[0]]
    for part in parts[1:]:
        if part.startswith("["):
            # Array index: append to previous part without delimiter
            result[-1] = result[-1] + part
        else:
            result.append(part)
    return delimiter.join(result)


def generate_struct_format(name_type_pairs: list[NameType], nested_field_delimiter=".") -> DBFormat:
    """
    Generates a structured format (`DBFormat`) from a list of field name and type pairs.

    This function groups consecutive Boolean fields together just like s7 / Tia Portal does for PLC's.
    Non-Boolean fields are converted according to their respective type mapping to struct format.
    Boolean fields are represented with a 'H' format (2 bytes) when accumulated.

    Parameters:
    - name_type_pairs (list[NameType]): A list of field name and type pairs.
    - nested_field_delimiter (str, optional): A delimiter used for joining nested field names. Defaults to '.'.

    Returns:
    - DBFormat: A data structure containing the generated struct format string, the corresponding fields,
               and the calculated size.

    Notes:
    - Boolean fields are accumulated up to a maximum of 16 before being added to the resulting format.
    - If the type of field changes or if the prefix of the name changes (i.e. it is in a different struct),
      the accumulated Boolean fields (if any) are added to the resulting format.
    - If the type is not a Boolean, the field is directly added to the resulting format.

    Example:
    For a given list with two Boolean fields ['a', 'Bool'] and ['b', 'Bool'] and one Int field ['c', 'Int'],
    the resulting DBFormat might have a format string like ">HHI", fields containing the two Bool fields
    combined and the Int field separately, and a size calculated based on this format string.
    """
    fields = []
    bool_counter = 0
    prefix: list[str] = []
    prev_prefix: list[str] = []
    bools: list[str] = []
    for i in name_type_pairs:
        prefix = i.name[:-1]
        if bool_counter > 0 and (i.type != "Bool" or prefix != prev_prefix or bool_counter == 17):
            fields.append(
                DBField(
                    name_or_names=bools,
                    type="Bool",
                    format="H",
                )
            )
            bool_counter = 0
            bools = []

        if i.type == "Bool":
            bool_counter += 1
            bools.append(_join_name_parts(i.name, nested_field_delimiter))
        else:
            fields.append(
                DBField(
                    name_or_names=_join_name_parts(i.name, nested_field_delimiter),
                    type=i.type,
                    format=s7_dtype_to_struct_mapping[i.type],
                )
            )
        prev_prefix = prefix
    if bool_counter > 0:
        fields.append(
            DBField(
                name_or_names=bools,
                type="Bool",
                format="H",
            )
        )
        bool_counter = 0

    fmt = ">" + "".join([p.format for p in fields])

    return DBFormat(format=fmt, fields=fields, size=struct.calcsize(fmt))


def parse_db_file(p: Path | str, nesting_depth_to_skip=1) -> DBFormat:
    """Parse a DB file and return a DBFormat object.

    Args:
        p (Path): Path to the DB file
        nesting_depth_to_skip (int, optional): How many levels in the nested data to skip when generating the fieldnames for nested fields.

    Returns:
        DBFormat: The parsed DB file
    """
    p = Path(p)
    result = program.parseString(p.read_text(encoding="utf-8-sig"), parse_all=True).as_dict()
    # default = defaults.parseString(p.read_text(encoding="utf-8-sig"), parse_all=True).as_dict()
    types = result["TYPES"]
    data = result["DATA_BLOCK"]
    result["BEGIN"]  # er kan hier nog wat met de default waardes gedaan worden.
    
    # Debug: print the parsed structure for arrays
    # import json
    # print("DATA_BLOCK structure:", json.dumps({k: type(v).__name__ for k, v in data.items()}, indent=2))
    
    # Collect resolved types, ensuring type is always a string
    resolved_pairs = []
    for k, v in resolve_data_types(types, [], data):
        if not isinstance(k, list) or len(k) == 0:
            continue
        # Ensure type is a string (S7 type name)
        if isinstance(v, str):
            resolved_pairs.append((k, v))
        elif isinstance(v, (dict, list)):
            # If type is a complex structure, we shouldn't be here - skip or error
            # This might happen if arrays aren't being expanded correctly
            continue
        else:
            # Try to convert to string
            resolved_pairs.append((k, str(v)))
    
    result = generate_struct_format(
        [
            NameType(
                name=k,
                type=v,
            )
            for k, v in resolved_pairs
        ]
    )

    if nesting_depth_to_skip > 0:
        fields = []
        for field in result.fields:
            if isinstance(field.name_or_names, list):
                name_or_names = [skip_nested_levels(name, nesting_depth_to_skip) for name in field.name_or_names]
            else:
                name_or_names = skip_nested_levels(field.name_or_names, nesting_depth_to_skip)
            fields.append(DBField(name_or_names=name_or_names, type=field.type, format=field.format))
        result = DBFormat(format=result.format, fields=fields, size=result.size)

    return result


def skip_nested_levels(name, nesting_depth_to_skip):
    return ".".join(name.split(".")[nesting_depth_to_skip:])


if __name__ == "__main__":
    format, fields, size = parse_db_file(
        Path("/home/quintus/workspace3/base-unit-tester/src/base_unit_tester/datablocks/test_DB.db"), 1
    )
    print(
        [
            n
            for field in fields
            for n in (field.name_or_names if isinstance(field.name_or_names, list) else [field.name_or_names])
        ]
    )

    print(size)