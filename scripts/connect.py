#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import json
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table as RichTable
except Exception:  # pragma: no cover
    Console = None
    RichTable = None


def load_project(project_file: str):
    p = Path(project_file)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    proj = load_project(str(Path(__file__).resolve().parents[1] / "project.json"))
    if not proj:
        print("No project.json found next to app. Open GUI first and load a DB.")
        return 1

    from TIA_Db.utlis import S7DataBlock
    import snap7

    def_path = proj.get("db_definition_path")
    db_number = proj.get("db_number")
    if not def_path or db_number is None:
        print("Project file missing db_definition_path or db_number")
        return 1

    db = S7DataBlock.from_definition_file(path=def_path, db_number=db_number, nesting_depth_to_skip=1)
    client = snap7.client.Client()

    console = Console() if Console else None
    ip = "192.168.241.191"
    rack = 0
    slot = 1

    while True:
        try:
            if not client.get_connected():
                client.connect(ip, rack, slot)
            if client.get_connected():
                db.buffer = client.db_read(db_number=db.db_number, start=0, size=db.db_size)
                if console and RichTable:
                    table = RichTable(title=f"DB{db.db_number} live")
                    table.add_column("Variable", style="bold")
                    table.add_column("Value")
                    for name in db.data.keys():
                        val = db[name]
                        style = "green" if isinstance(val, bool) and val else ("red" if isinstance(val, bool) else ("cyan" if isinstance(val, (int, float)) else "white"))
                        table.add_row(name, f"[{style}]{val}[/]")
                    console.print(table)
                else:
                    print(dict((k, db[k]) for k in db.data.keys()))
            time.sleep(0.5)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1.0)
    try:
        client.disconnect()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


