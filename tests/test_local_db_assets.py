from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.local_db_assets import build_local_database_assets, get_local_asset_paths, refresh_database_assets, refresh_local_database_assets


class LocalDatabaseAssetsTestCase(unittest.TestCase):
    def test_build_local_database_assets_writes_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "demo.sqlite"
            connection = sqlite3.connect(database_path)
            try:
                cursor = connection.cursor()
                cursor.execute("CREATE TABLE customers(id INTEGER PRIMARY KEY, name TEXT, city TEXT)")
                cursor.execute("INSERT INTO customers(name, city) VALUES('Alice', 'Beijing')")
                connection.commit()
            finally:
                connection.close()

            asset_paths = build_local_database_assets(database_path)
            self.assertEqual(asset_paths, get_local_asset_paths(database_path.resolve()))
            self.assertTrue(asset_paths["metadata"].exists())
            self.assertTrue(asset_paths["semantic"].exists())
            self.assertTrue(asset_paths["examples"].exists())

            payload = json.loads(asset_paths["metadata"].read_text(encoding="utf-8"))
            self.assertEqual(payload["database_name"], "demo")
            self.assertTrue(payload["description"])
            self.assertEqual(payload["tables"][0]["name"], "customers")
            self.assertEqual(payload["tables"][0]["row_count"], 1)
            self.assertTrue(payload["tables"][0]["description"])
            self.assertTrue(payload["tables"][0]["columns"][0]["description"])

            semantic_payload = json.loads(asset_paths["semantic"].read_text(encoding="utf-8"))
            self.assertTrue(semantic_payload["database_summary"])
            self.assertIn("customers", semantic_payload["table_descriptions"])
            self.assertIn("customers.id", semantic_payload["column_descriptions"])

    def test_refresh_local_database_assets_updates_live_schema_and_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "demo.sqlite"
            connection = sqlite3.connect(database_path)
            try:
                cursor = connection.cursor()
                cursor.execute("CREATE TABLE customers(id INTEGER PRIMARY KEY, name TEXT)")
                cursor.execute("INSERT INTO customers(name) VALUES('Alice')")
                connection.commit()
            finally:
                connection.close()

            asset_paths = build_local_database_assets(database_path)
            initial_payload = json.loads(asset_paths["metadata"].read_text(encoding="utf-8"))
            initial_description = initial_payload["tables"][0]["description"]

            connection = sqlite3.connect(database_path)
            try:
                cursor = connection.cursor()
                cursor.execute("INSERT INTO customers(name) VALUES('Bob')")
                cursor.execute("CREATE TABLE orders(order_id INTEGER PRIMARY KEY, customer_id INTEGER)")
                connection.commit()
            finally:
                connection.close()

            refresh_local_database_assets(database_path)

            refreshed_payload = json.loads(asset_paths["metadata"].read_text(encoding="utf-8"))
            tables = {table["name"]: table for table in refreshed_payload["tables"]}
            self.assertEqual(tables["customers"]["row_count"], 2)
            self.assertEqual(tables["customers"]["description"], initial_description)
            self.assertIn("orders", tables)
            self.assertEqual(tables["orders"]["row_count"], 0)

            semantic_payload = json.loads(asset_paths["semantic"].read_text(encoding="utf-8"))
            self.assertIn("orders", semantic_payload["table_descriptions"])
            self.assertIn("orders.order_id", semantic_payload["column_descriptions"])

    def test_refresh_database_assets_preserves_custom_semantic_config_for_non_local_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            database_path = temp_root / "chinook_like.sqlite"
            metadata_path = temp_root / "processed" / "schema_metadata.json"
            semantic_path = temp_root / "processed" / "semantic_layer.json"
            examples_path = temp_root / "processed" / "demo_questions.json"

            connection = sqlite3.connect(database_path)
            try:
                cursor = connection.cursor()
                cursor.execute("CREATE TABLE Artist(ArtistId INTEGER PRIMARY KEY, Name TEXT)")
                cursor.execute("INSERT INTO Artist(Name) VALUES('Alice')")
                connection.commit()
            finally:
                connection.close()

            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.write_text(
                json.dumps(
                    {
                        "database_name": "Chinook",
                        "dialect": "sqlite",
                        "source": {
                            "name": "chinook-database",
                            "repository": "https://example.invalid/chinook",
                            "database_file": "data/raw/chinook/Chinook_Sqlite.sqlite",
                        },
                        "tables": [
                            {
                                "name": "Artist",
                                "row_count": 1,
                                "primary_keys": ["ArtistId"],
                                "foreign_keys": [],
                                "columns": [
                                    {"name": "ArtistId", "type": "INTEGER", "nullable": False},
                                    {"name": "Name", "type": "TEXT", "nullable": True},
                                ],
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            semantic_path.write_text(
                json.dumps(
                    {
                        "table_aliases": {"Artist": ["艺人", "歌手"]},
                        "column_aliases": {"Artist.Name": ["艺人名"]},
                        "metric_templates": [{"name": "艺人数", "table": "Artist", "column": "ArtistId", "aggregation": "COUNT"}],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            examples_path.write_text(json.dumps({"questions": [{"question": "有多少艺人", "sql": "SELECT COUNT(*) FROM Artist", "explanation": "统计艺人数"}]}, ensure_ascii=False, indent=2), encoding="utf-8")

            connection = sqlite3.connect(database_path)
            try:
                cursor = connection.cursor()
                cursor.execute("INSERT INTO Artist(Name) VALUES('Bob')")
                cursor.execute("ALTER TABLE Artist ADD COLUMN Country TEXT")
                connection.commit()
            finally:
                connection.close()

            refresh_database_assets(database_path, metadata_path, semantic_path, examples_path)

            refreshed_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            refreshed_semantic = json.loads(semantic_path.read_text(encoding="utf-8"))
            refreshed_examples = json.loads(examples_path.read_text(encoding="utf-8"))

            artist_table = next(table for table in refreshed_metadata["tables"] if table["name"] == "Artist")
            self.assertEqual(artist_table["row_count"], 2)
            self.assertEqual([column["name"] for column in artist_table["columns"]], ["ArtistId", "Name", "Country"])
            self.assertEqual(refreshed_metadata["source"]["repository"], "https://example.invalid/chinook")
            self.assertEqual(refreshed_semantic["table_aliases"]["Artist"], ["艺人", "歌手"])
            self.assertEqual(refreshed_semantic["metric_templates"][0]["name"], "艺人数")
            self.assertIn("Artist.Country", refreshed_semantic["column_descriptions"])
            self.assertEqual(refreshed_examples["questions"][0]["question"], "有多少艺人")


if __name__ == "__main__":
    unittest.main()