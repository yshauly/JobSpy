from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


COMPANIES_TABLE_NAME = "companies"
DEFAULT_COMPANIES_JSON_PATH = Path(__file__).resolve().with_name("companies.json")
AIRTABLE_EXPORT_TABLE_KEYS = ("data", "table")
COMPANY_COLUMN_NAME_OVERRIDES = {
    "Company": "company_name",
    "Website": "website_url",
    "Linkedin": "linkedin_url",
    "Crunchbase": "crunchbase_url",
    "Startup Nation Finder": "startup_nation_finder_url",
    "GlassDoor": "glassdoor_url",
    "Facebook": "facebook_url",
    "Twitter": "twitter_url",
    "Instagram": "instagram_url",
    "Youtube": "youtube_url",
    "Geektime Insider": "geektime_insider_url",
    "TikTok": "tiktok_url",
    "POC Linkedin": "poc_linkedin_url",
    "Updated": "source_updated_at",
}
DB_IDENTIFIER_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass(frozen=True)
class CompanyColumnDefinition:
    source_id: str
    source_name: str
    db_name: str
    airtable_type: str
    sql_type: str
    is_multi_select: bool
    is_datetime: bool
    choices_by_id: dict[str, str]


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return str(value).strip() or None


def _safe_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)

    text = _safe_str(value)
    if not text:
        return None

    try:
        return int(text)
    except ValueError:
        try:
            return int(float(text))
        except ValueError:
            return None


def _parse_timestamp(value: Any) -> datetime | None:
    text = _safe_str(value)
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _format_population_summary(summary: dict[str, Any]) -> str:
    return json.dumps(summary, ensure_ascii=False, indent=2, default=str)


def _get_db_connection():
    from jobspy.jobs_table import _get_db_connection as get_jobs_db_connection

    return get_jobs_db_connection()


def _normalize_column_name(column_name: str) -> str:
    override = COMPANY_COLUMN_NAME_OVERRIDES.get(column_name)
    if override:
        return override

    normalized = re.sub(r"[^a-z0-9]+", "_", column_name.lower()).strip("_")
    normalized = re.sub(r"_+", "_", normalized)
    if not normalized:
        raise ValueError(f"Could not derive a database column name for {column_name!r}")
    return normalized


def _validate_db_identifier(identifier: str) -> str:
    if not DB_IDENTIFIER_PATTERN.match(identifier):
        raise ValueError(f"Unsafe SQL identifier: {identifier!r}")
    return identifier


def _coerce_choice_mapping(raw_choices: Any) -> dict[str, str]:
    if isinstance(raw_choices, dict):
        mappings = raw_choices.items()
    elif isinstance(raw_choices, list):
        mappings = ((choice.get("id"), choice) for choice in raw_choices)
    else:
        return {}

    resolved: dict[str, str] = {}
    for choice_id, choice in mappings:
        choice_name = None
        if isinstance(choice, dict):
            choice_name = _safe_str(choice.get("name"))
        else:
            choice_name = _safe_str(choice)

        normalized_choice_id = _safe_str(choice_id)
        if normalized_choice_id and choice_name:
            resolved[normalized_choice_id] = choice_name
    return resolved


def _is_formula_datetime(column: dict[str, Any]) -> bool:
    type_options = column.get("typeOptions") or {}
    return bool(type_options.get("isDateTime"))


def _get_sql_type(column: dict[str, Any], *, db_name: str) -> str:
    airtable_type = _safe_str(column.get("type")) or ""
    if db_name == "source_updated_at":
        return "TIMESTAMPTZ"
    if airtable_type == "checkbox":
        return "BOOLEAN"
    if airtable_type == "number":
        return "INTEGER"
    if airtable_type == "multiSelect":
        return "TEXT[]"
    if airtable_type == "formula" and _is_formula_datetime(column):
        return "TIMESTAMPTZ"
    return "TEXT"


def _build_company_column_definitions(
    columns: list[dict[str, Any]],
) -> list[CompanyColumnDefinition]:
    definitions: list[CompanyColumnDefinition] = []
    seen_db_names: set[str] = set()

    for column in columns:
        source_id = _safe_str(column.get("id"))
        source_name = _safe_str(column.get("name"))
        airtable_type = _safe_str(column.get("type"))
        if not source_id or not source_name or not airtable_type:
            raise ValueError("Each Airtable column must contain id, name, and type")

        db_name = _validate_db_identifier(_normalize_column_name(source_name))
        if db_name in seen_db_names:
            raise ValueError(
                f"Duplicate database column name {db_name!r} derived from Airtable metadata"
            )

        type_options = column.get("typeOptions") or {}
        definitions.append(
            CompanyColumnDefinition(
                source_id=source_id,
                source_name=source_name,
                db_name=db_name,
                airtable_type=airtable_type,
                sql_type=_get_sql_type(column, db_name=db_name),
                is_multi_select=airtable_type == "multiSelect",
                is_datetime=_is_formula_datetime(column) or db_name == "source_updated_at",
                choices_by_id=_coerce_choice_mapping(type_options.get("choices")),
            )
        )
        seen_db_names.add(db_name)

    return definitions


def _extract_rows_and_columns(json_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not json_path.exists():
        raise FileNotFoundError(f"Companies JSON file not found: {json_path}")

    payload = json.loads(json_path.read_text(encoding="utf-8"))

    table = None
    if isinstance(payload, dict):
        nested_data = payload.get(AIRTABLE_EXPORT_TABLE_KEYS[0])
        if isinstance(nested_data, dict):
            table = nested_data.get(AIRTABLE_EXPORT_TABLE_KEYS[1])
        if table is None:
            table = payload.get("table")

    if not isinstance(table, dict):
        raise ValueError(
            "Expected an Airtable-style export with a table object at payload['data']['table']"
        )

    rows = table.get("rows")
    columns = table.get("columns")
    if not isinstance(rows, list) or not isinstance(columns, list):
        raise ValueError("Expected Airtable table export to contain 'rows' and 'columns' lists")

    dict_rows = [row for row in rows if isinstance(row, dict)]
    dict_columns = [column for column in columns if isinstance(column, dict)]
    if len(dict_rows) != len(rows):
        raise ValueError("Expected every Airtable row to be a JSON object")
    if len(dict_columns) != len(columns):
        raise ValueError("Expected every Airtable column to be a JSON object")

    return dict_rows, dict_columns


def _coerce_checkbox(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value

    text = (_safe_str(value) or "").lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _resolve_choice_value(raw_value: Any, choices_by_id: dict[str, str]) -> str | None:
    choice_id = _safe_str(raw_value)
    if not choice_id:
        return None
    return choices_by_id.get(choice_id) or choice_id


def _resolve_multi_choice_value(
    raw_value: Any, choices_by_id: dict[str, str]
) -> list[str] | None:
    if raw_value is None:
        return None

    if isinstance(raw_value, list):
        items = raw_value
    else:
        items = [raw_value]

    resolved: list[str] = []
    for item in items:
        choice_name = _resolve_choice_value(item, choices_by_id)
        if choice_name and choice_name not in resolved:
            resolved.append(choice_name)
    return resolved or None


def _coerce_company_cell_value(
    raw_value: Any, column_definition: CompanyColumnDefinition
) -> Any:
    if raw_value is None:
        return None

    if column_definition.is_multi_select:
        return _resolve_multi_choice_value(raw_value, column_definition.choices_by_id)

    if column_definition.airtable_type == "select":
        return _resolve_choice_value(raw_value, column_definition.choices_by_id)

    if column_definition.sql_type == "TIMESTAMPTZ":
        return _parse_timestamp(raw_value)

    if column_definition.airtable_type == "checkbox":
        return _coerce_checkbox(raw_value)

    if column_definition.sql_type == "INTEGER":
        return _safe_int(raw_value)

    return _safe_str(raw_value)


def _build_company_record(
    row: dict[str, Any], column_definitions: list[CompanyColumnDefinition]
) -> dict[str, Any] | None:
    row_id = _safe_str(row.get("id"))
    cell_values = row.get("cellValuesByColumnId")
    if not row_id or not isinstance(cell_values, dict):
        return None

    record: dict[str, Any] = {
        "airtable_row_id": row_id,
        "airtable_created_time": _parse_timestamp(row.get("createdTime")),
        "raw_json": row,
    }

    for column_definition in column_definitions:
        record[column_definition.db_name] = _coerce_company_cell_value(
            cell_values.get(column_definition.source_id),
            column_definition,
        )

    return record


def _prepare_company_records(
    rows: list[dict[str, Any]],
    column_definitions: list[CompanyColumnDefinition],
) -> tuple[list[dict[str, Any]], int, int]:
    records_by_row_id: dict[str, dict[str, Any]] = {}
    skipped_invalid = 0
    skipped_duplicate_input = 0

    for row in rows:
        record = _build_company_record(row, column_definitions)
        if not record:
            skipped_invalid += 1
            continue

        row_id = record["airtable_row_id"]
        if row_id in records_by_row_id:
            skipped_duplicate_input += 1
        records_by_row_id[row_id] = record

    return list(records_by_row_id.values()), skipped_invalid, skipped_duplicate_input


def _ensure_companies_table(
    cursor, column_definitions: list[CompanyColumnDefinition]
) -> None:
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {COMPANIES_TABLE_NAME} (
            airtable_row_id TEXT PRIMARY KEY,
            airtable_created_time TIMESTAMPTZ,
            raw_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    for column_definition in column_definitions:
        cursor.execute(
            f"""
            ALTER TABLE {COMPANIES_TABLE_NAME}
            ADD COLUMN IF NOT EXISTS {column_definition.db_name} {column_definition.sql_type}
            """
        )


def _company_insert_values(
    record: dict[str, Any],
    column_definitions: list[CompanyColumnDefinition],
    json_adapter,
) -> tuple[Any, ...]:
    return (
        record["airtable_row_id"],
        record["airtable_created_time"],
        *[record.get(column_definition.db_name) for column_definition in column_definitions],
        json_adapter(record["raw_json"]),
    )


def _upsert_company_records(
    company_records: list[dict[str, Any]],
    column_definitions: list[CompanyColumnDefinition],
) -> dict[str, Any]:
    from psycopg2.extras import Json

    if not company_records:
        return {
            "inserted": 0,
            "updated": 0,
            "updated_row_ids": [],
            "failed": 0,
        }

    dynamic_columns = [column_definition.db_name for column_definition in column_definitions]
    insert_columns = [
        "airtable_row_id",
        "airtable_created_time",
        *dynamic_columns,
        "raw_json",
    ]
    update_columns = ["airtable_created_time", *dynamic_columns, "raw_json"]
    select_sql = f"""
        SELECT 1
        FROM {COMPANIES_TABLE_NAME}
        WHERE airtable_row_id = %s
        LIMIT 1
    """
    insert_sql = f"""
        INSERT INTO {COMPANIES_TABLE_NAME} (
            {", ".join(insert_columns)},
            created_at,
            updated_at
        )
        VALUES (
            {", ".join(["%s"] * len(insert_columns))},
            NOW(),
            NOW()
        )
    """
    update_sql = f"""
        UPDATE {COMPANIES_TABLE_NAME}
        SET
            {", ".join(f"{column} = %s" for column in update_columns)},
            updated_at = NOW()
        WHERE airtable_row_id = %s
    """

    inserted = 0
    updated = 0
    updated_row_ids: list[str] = []
    failed = 0

    conn = _get_db_connection()
    try:
        with conn:
            with conn.cursor() as cursor:
                _ensure_companies_table(cursor, column_definitions)
                total = len(company_records)
                for index, record in enumerate(company_records, start=1):
                    if total and (index == 1 or index % 25 == 0 or index == total):
                        print(
                            f"DB progress {index}/{total} | "
                            f"inserted={inserted} updated={updated} failed={failed}"
                        )

                    values = _company_insert_values(record, column_definitions, Json)
                    row_id = record["airtable_row_id"]
                    try:
                        cursor.execute(select_sql, (row_id,))
                        exists = cursor.fetchone() is not None

                        if exists:
                            cursor.execute(update_sql, (*values[1:], row_id))
                            updated += 1
                            updated_row_ids.append(row_id)
                        else:
                            cursor.execute(insert_sql, values)
                            inserted += 1
                    except Exception as exc:
                        failed += 1
                        print(f"DB row failed for {row_id}: {exc}")
    finally:
        conn.close()

    return {
        "inserted": inserted,
        "updated": updated,
        "updated_row_ids": updated_row_ids,
        "failed": failed,
    }


def populate_companies_table_from_file(
    json_path: Path | str | None = None,
) -> dict[str, Any]:
    effective_path = (
        Path(json_path).expanduser().resolve()
        if json_path is not None
        else DEFAULT_COMPANIES_JSON_PATH
    )
    rows, columns = _extract_rows_and_columns(effective_path)
    column_definitions = _build_company_column_definitions(columns)

    print(f"Loaded {len(rows)} companies from {effective_path}")
    print(
        "Connecting to PostgreSQL and populating "
        f"{COMPANIES_TABLE_NAME} table"
    )

    prepared_records, skipped_invalid, skipped_duplicate_input = _prepare_company_records(
        rows,
        column_definitions,
    )
    upsert_summary = _upsert_company_records(prepared_records, column_definitions)

    summary = {
        "rows_in_file": len(rows),
        "columns_in_file": len(columns),
        "prepared_records": len(prepared_records),
        "inserted": upsert_summary["inserted"],
        "updated": upsert_summary["updated"],
        "updated_row_ids": upsert_summary["updated_row_ids"],
        "skipped_invalid": skipped_invalid,
        "skipped_duplicate_input": skipped_duplicate_input,
        "failed": upsert_summary["failed"],
    }
    print(f"{COMPANIES_TABLE_NAME} population finished")
    print(_format_population_summary(summary))
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Populate the companies table from an Airtable-style companies JSON export"
        )
    )
    parser.add_argument(
        "json_path",
        nargs="?",
        default=None,
        help=(
            "Optional path to companies.json. Defaults to a sibling companies.json "
            "next to this module."
        ),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    populate_companies_table_from_file(args.json_path)


if __name__ == "__main__":
    main()
