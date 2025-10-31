#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
from TIA_Db.utlis import S7DataBlock
from rich import print

def main() -> int:
    definition_path = Path(__file__).with_name("DB_IO.db")
    db_io = S7DataBlock.from_definition_file(path=str(definition_path), db_number=1200, nesting_depth_to_skip=1)
    
    # Print all field names
    print("Fields:", db_io)
    print("Buffer size:", len(db_io.buffer))
    
    # Test accessing array elements
    print("\nAccessing InfeedBelt[1].I_FT_In:", db_io.get("InfeedBelt[1].I_FT_In", None))
    print("Accessing InfeedBelt[2].I_FT_In:", db_io.get("InfeedBelt[2].I_FT_In", None))
    print("Accessing BCK[1].I_FT_Pusher:", db_io.get("BCK[1].I_FT_Pusher", None))
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
