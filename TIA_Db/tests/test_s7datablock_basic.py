#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
from TIA_Db.utlis import S7DataBlock
from rich import print

def main() -> int:

    definition_path = Path(__file__).with_name("DB_IO.db")
    db1200 = S7DataBlock.from_definition_file(path=str(definition_path), db_number=1200, nesting_depth_to_skip=1)

    # As dict-like
    print(db1200)
    # Under the hood buffer
    print(db1200.buffer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


