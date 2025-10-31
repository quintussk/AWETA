#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
from TIA_Db import S7DataBlock

def main() -> int:

    definition_path = Path(__file__).with_name("DB_IO.db")
    db1200 = S7DataBlock.from_definition_file(path=str(definition_path), db_number=1200)

    # As dict-like
    print(db1200)

    # Under the hood buffer
    print(db1200.buffer)

    # Modify a boolean
    db1200["PLC_DQ_3"] = True
    print(db1200.buffer)

    # Quick checks consistent with the example
    assert db1200["PLC_DQ_0"] is False
    assert db1200["PLC_DQ_3"] is True
    assert db1200["SB_AQ_0"] == 0
    # buffer should show bit 3 set in first byte
    assert db1200.buffer[0] == 0x08

    print("All S7DataBlock checks passed. ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


