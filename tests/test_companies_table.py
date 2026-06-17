from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jobspy import companies_table


class FakeCursor:
    def __init__(self, scripted_steps: list[dict[str, object]]) -> None:
        self._scripted_steps = list(scripted_steps)
        self.executed_sql: list[str] = []
        self.executed_params: list[object] = []
        self._fetchone_value = None

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params=None) -> None:
        if not self._scripted_steps:
            raise AssertionError(f"Unexpected SQL execution: {sql}")

        step = self._scripted_steps.pop(0)
        expected = step["contains"]
        if expected not in sql:
            raise AssertionError(
                f"Expected SQL containing {expected!r}, received:\n{sql}"
            )

        self.executed_sql.append(sql)
        self.executed_params.append(params)
        self._fetchone_value = step.get("fetchone")

    def fetchone(self):
        return self._fetchone_value


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.closed = False

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return self._cursor

    def close(self) -> None:
        self.closed = True


class CompaniesTableTests(unittest.TestCase):
    def test_build_company_column_definitions_uses_meaningful_column_names(self) -> None:
        definitions = companies_table._build_company_column_definitions(
            [
                {
                    "id": "fldCompany",
                    "name": "Company",
                    "type": "multilineText",
                    "typeOptions": None,
                },
                {
                    "id": "fldCompanySize",
                    "name": "Company Size (Israel)",
                    "type": "select",
                    "typeOptions": {
                        "choices": {
                            "sel1": {"name": "11 - 50 employees"},
                        }
                    },
                },
                {
                    "id": "fldLinkedin",
                    "name": "Linkedin",
                    "type": "text",
                    "typeOptions": None,
                },
                {
                    "id": "fldUpdated",
                    "name": "Updated",
                    "type": "formula",
                    "typeOptions": {"isDateTime": True},
                },
            ]
        )

        self.assertEqual(
            [definition.db_name for definition in definitions],
            [
                "company_name",
                "company_size_israel",
                "linkedin_url",
                "source_updated_at",
            ],
        )
        self.assertEqual(definitions[1].choices_by_id["sel1"], "11 - 50 employees")
        self.assertEqual(definitions[3].sql_type, "TIMESTAMPTZ")

    def test_populate_companies_table_from_file_maps_choice_ids_and_upserts(self) -> None:
        payload = {
            "data": {
                "table": {
                    "columns": [
                        {
                            "id": "fldCompany",
                            "name": "Company",
                            "type": "multilineText",
                            "typeOptions": None,
                        },
                        {
                            "id": "fldIndustry",
                            "name": "Industry",
                            "type": "multiSelect",
                            "typeOptions": {
                                "choices": {
                                    "selCyber": {"name": "Cybersecurity"},
                                    "selSoftware": {"name": "Software"},
                                }
                            },
                        },
                        {
                            "id": "fldSize",
                            "name": "Company Size (Israel)",
                            "type": "select",
                            "typeOptions": {
                                "choices": {
                                    "selSmall": {"name": "11 - 50 employees"},
                                }
                            },
                        },
                        {
                            "id": "fldHiring",
                            "name": "Hiring",
                            "type": "checkbox",
                            "typeOptions": None,
                        },
                        {
                            "id": "fldUpdated",
                            "name": "Updated",
                            "type": "formula",
                            "typeOptions": {"isDateTime": True},
                        },
                    ],
                    "rows": [
                        {
                            "id": "recA",
                            "createdTime": "2022-12-29T10:19:04.000Z",
                            "cellValuesByColumnId": {
                                "fldCompany": "Acme Security",
                                "fldIndustry": ["selCyber", "selSoftware"],
                                "fldSize": "selSmall",
                                "fldHiring": True,
                                "fldUpdated": "2025-12-28T17:58:36.000Z",
                            },
                        }
                    ],
                }
            }
        }

        scripted_steps = [
            {"contains": "CREATE TABLE IF NOT EXISTS companies"},
            {"contains": "ADD COLUMN IF NOT EXISTS company_name TEXT"},
            {"contains": "ADD COLUMN IF NOT EXISTS industry TEXT[]"},
            {"contains": "ADD COLUMN IF NOT EXISTS company_size_israel TEXT"},
            {"contains": "ADD COLUMN IF NOT EXISTS hiring BOOLEAN"},
            {"contains": "ADD COLUMN IF NOT EXISTS source_updated_at TIMESTAMPTZ"},
            {"contains": "FROM companies", "fetchone": None},
            {"contains": "INSERT INTO companies"},
        ]
        fake_cursor = FakeCursor(scripted_steps)
        fake_connection = FakeConnection(fake_cursor)

        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path = Path(tmp_dir) / "companies.json"
            json_path.write_text(json.dumps(payload), encoding="utf-8")

            with patch(
                "jobspy.companies_table._get_db_connection",
                return_value=fake_connection,
            ):
                summary = companies_table.populate_companies_table_from_file(json_path)

        self.assertEqual(summary["rows_in_file"], 1)
        self.assertEqual(summary["prepared_records"], 1)
        self.assertEqual(summary["inserted"], 1)
        self.assertEqual(summary["updated"], 0)
        self.assertEqual(summary["skipped_invalid"], 0)
        self.assertEqual(summary["failed"], 0)
        self.assertTrue(fake_connection.closed)

        insert_params = fake_cursor.executed_params[-1]
        self.assertEqual(insert_params[0], "recA")
        self.assertEqual(insert_params[2], "Acme Security")
        self.assertEqual(insert_params[3], ["Cybersecurity", "Software"])
        self.assertEqual(insert_params[4], "11 - 50 employees")
        self.assertTrue(insert_params[5])
        self.assertEqual(insert_params[-1].adapted["id"], "recA")

    def test_populate_companies_table_from_file_dedupes_duplicate_row_ids(self) -> None:
        payload = {
            "data": {
                "table": {
                    "columns": [
                        {
                            "id": "fldCompany",
                            "name": "Company",
                            "type": "multilineText",
                            "typeOptions": None,
                        }
                    ],
                    "rows": [
                        {
                            "id": "recA",
                            "createdTime": "2022-12-29T10:19:04.000Z",
                            "cellValuesByColumnId": {
                                "fldCompany": "First Name",
                            },
                        },
                        {
                            "id": "recA",
                            "createdTime": "2022-12-30T10:19:04.000Z",
                            "cellValuesByColumnId": {
                                "fldCompany": "Second Name Wins",
                            },
                        },
                    ],
                }
            }
        }

        captured_records: list[dict[str, object]] = []

        def fake_upsert(records, column_definitions):
            captured_records.extend(records)
            self.assertEqual(column_definitions[0].db_name, "company_name")
            return {
                "inserted": 1,
                "updated": 0,
                "updated_row_ids": [],
                "failed": 0,
            }

        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path = Path(tmp_dir) / "companies.json"
            json_path.write_text(json.dumps(payload), encoding="utf-8")

            with patch(
                "jobspy.companies_table._upsert_company_records",
                side_effect=fake_upsert,
            ):
                summary = companies_table.populate_companies_table_from_file(json_path)

        self.assertEqual(summary["prepared_records"], 1)
        self.assertEqual(summary["skipped_duplicate_input"], 1)
        self.assertEqual(len(captured_records), 1)
        self.assertEqual(captured_records[0]["company_name"], "Second Name Wins")


if __name__ == "__main__":
    unittest.main()
