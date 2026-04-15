from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = ROOT_DIR / "data" / "raw" / "chinook" / "Chinook_Sqlite.sqlite"
OUTPUT_PATH = ROOT_DIR / "data" / "processed" / "schema_metadata.json"


def fetch_tables(cursor: sqlite3.Cursor) -> list[str]:
    rows = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def fetch_table_profile(cursor: sqlite3.Cursor, table_name: str) -> dict:
    row_count = cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]").fetchone()[0]
    columns = cursor.execute(f"PRAGMA table_info([{table_name}])").fetchall()
    foreign_keys = cursor.execute(f"PRAGMA foreign_key_list([{table_name}])").fetchall()

    primary_keys = [column[1] for column in columns if column[5] > 0]
    foreign_key_map = {
        item[3]: {"table": item[2], "column": item[4]}
        for item in foreign_keys
    }

    return {
        "name": table_name,
        "row_count": row_count,
        "primary_keys": primary_keys,
        "foreign_keys": [
            {
                "column": column_name,
                "references": reference,
            }
            for column_name, reference in foreign_key_map.items()
        ],
        "columns": [
            {
                "name": column[1],
                "type": column[2] or "TEXT",
                "nullable": column[3] == 0,
            }
            for column in columns
        ],
    }


def main() -> None:
    with sqlite3.connect(DATABASE_PATH) as connection:
        cursor = connection.cursor()
        tables = [fetch_table_profile(cursor, table_name) for table_name in fetch_tables(cursor)]

    payload = {
        "database_name": "Chinook",
        "dialect": "sqlite",
        "source": {
            "name": "chinook-database",
            "repository": "https://github.com/lerocha/chinook-database",
            "database_file": str(DATABASE_PATH.relative_to(ROOT_DIR)).replace("\\", "/"),
        },
        "tables": tables,
    }

    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"metadata written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
