from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from jobspy import jobs_table


class FakeCursor:
    def __init__(self, scripted_steps: list[dict[str, object]]) -> None:
        self._scripted_steps = list(scripted_steps)
        self.executed_sql: list[str] = []
        self.executed_params: list[object] = []
        self._fetchone_value = None
        self._fetchall_value: list[object] = []

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
        self._fetchall_value = step.get("fetchall", [])

    def fetchone(self):
        return self._fetchone_value

    def fetchall(self):
        return list(self._fetchall_value)


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


class JobsTablePersistenceTests(unittest.TestCase):
    def test_bulk_upsert_jobs_uses_job_url_conflict_key(self) -> None:
        scripted_steps = [
            {"contains": "ADD COLUMN IF NOT EXISTS reposted_at DATE"},
            {"contains": "FROM pg_indexes", "fetchone": None},
            {"contains": "DROP TABLE IF EXISTS tmp_jobs_job_url_dedup_map"},
            {"contains": "CREATE TEMP TABLE tmp_jobs_job_url_dedup_map"},
            {"contains": "INSERT INTO tmp_jobs_job_url_dedup_map"},
            {
                "contains": "SELECT COUNT(*) FROM tmp_jobs_job_url_dedup_map",
                "fetchone": (2,),
            },
            {"contains": "UPDATE jobs AS winner"},
            {"contains": "UPDATE user_job_first_match AS winner"},
            {"contains": "DELETE FROM user_job_first_match AS loser"},
            {"contains": "UPDATE user_job_first_match AS row_to_move"},
            {"contains": "UPDATE user_job_kanban_cards AS winner"},
            {"contains": "DELETE FROM user_job_kanban_cards AS loser"},
            {"contains": "UPDATE user_job_kanban_cards AS row_to_move"},
            {"contains": "UPDATE job_match_email_deliveries AS winner"},
            {"contains": "DELETE FROM job_match_email_deliveries AS loser"},
            {"contains": "UPDATE job_match_email_deliveries AS row_to_move"},
            {"contains": "DELETE FROM jobs AS duplicate_jobs", "fetchone": (2,)},
            {"contains": "CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_job_url"},
            {"contains": "CREATE TEMP TABLE tmp_jobs_import"},
            {"contains": "UPDATE tmp_jobs_import"},
            {"contains": "DROP TABLE IF EXISTS tmp_jobs_job_url_dedup_map"},
            {"contains": "CREATE TEMP TABLE tmp_jobs_job_url_dedup_map"},
            {
                "contains": "JOIN jobs AS source_external_job",
            },
            {
                "contains": "SELECT COUNT(*) FROM tmp_jobs_job_url_dedup_map",
                "fetchone": (0,),
            },
            {
                "contains": "UPDATE jobs AS existing_job",
            },
            {
                "contains": "JOIN jobs j\n          ON j.job_url = s.job_url",
                "fetchall": [("https://example.com/jobs/1", "new-external-id")],
            },
            {
                "contains": "WHERE j.title IS DISTINCT FROM s.title",
                "fetchall": [("https://example.com/jobs/1", "new-external-id")],
            },
            {
                "contains": "COALESCE(NULLIF(BTRIM(s.external_id), ''), NULLIF(BTRIM(j.external_id), ''), s.job_url) AS job_id",
                "fetchall": [],
            },
            {"contains": "ON CONFLICT (job_url) DO UPDATE"},
        ]
        fake_cursor = FakeCursor(scripted_steps)
        fake_connection = FakeConnection(fake_cursor)
        captured_values: list[tuple[object, ...]] = []

        def fake_execute_values(cursor, sql, values, page_size=100):
            self.assertIn("INSERT INTO tmp_jobs_import", sql)
            captured_values.extend(values)

        with patch("jobspy.jobs_table._get_db_connection", return_value=fake_connection):
            with patch("psycopg2.extras.execute_values", side_effect=fake_execute_values):
                summary = jobs_table._bulk_upsert_jobs(
                    [
                        {
                            "title": "Backend Engineer",
                            "location": "Tel Aviv",
                            "posted_time": "2026-04-05",
                            "published_at": None,
                            "job_url": "https://example.com/jobs/1",
                            "company_name": "Acme",
                            "company_url": "https://example.com/company/acme",
                            "company_id": "acme",
                            "description": "Build services",
                            "applications_count": "3",
                            "contract_type": "full-time",
                            "experience_level": "mid",
                            "work_type": "remote",
                            "sector": "software",
                            "salary": None,
                            "poster_full_name": None,
                            "poster_profile_url": None,
                            "apply_url": "https://example.com/jobs/1/apply",
                            "apply_type": "external",
                            "benefits": None,
                            "source": "comeet",
                            "external_id": "new-external-id",
                            "raw_json": {"job_url": "https://example.com/jobs/1"},
                        }
                    ]
                )

        self.assertEqual(summary["inserted"], 0)
        self.assertEqual(summary["updated"], 1)
        self.assertEqual(summary["deleted_duplicate_rows"], 2)
        self.assertTrue(captured_values)
        self.assertTrue(
            any(
                "ON CONFLICT (job_url) DO UPDATE" in sql
                for sql in fake_cursor.executed_sql
            )
        )
        self.assertTrue(
            any("ON j.job_url = s.job_url" in sql for sql in fake_cursor.executed_sql)
        )
        self.assertTrue(
            any(
                "existing_job.source = staged_job.source" in sql
                for sql in fake_cursor.executed_sql
            )
        )
        self.assertTrue(
            any(
                "existing_job.external_id = staged_job.external_id" in sql
                for sql in fake_cursor.executed_sql
            )
        )
        normalize_dates_sql = next(
            sql for sql in fake_cursor.executed_sql if "UPDATE tmp_jobs_import" in sql
        )
        self.assertIn(
            "posted_time = COALESCE(NULLIF(BTRIM(posted_time), ''), NOW()::text)",
            normalize_dates_sql,
        )
        self.assertIn(
            "published_at = COALESCE(published_at, NOW()::date)",
            normalize_dates_sql,
        )
        self.assertTrue(
            any(
                "UPDATE user_job_first_match AS winner" in sql
                for sql in fake_cursor.executed_sql
            )
        )
        self.assertFalse(
            any(
                "AND j.external_id = s.external_id" in sql
                for sql in fake_cursor.executed_sql
            )
        )

    def test_bulk_upsert_jobs_can_include_duplicate_flag(self) -> None:
        scripted_steps = [
            {"contains": "ADD COLUMN IF NOT EXISTS reposted_at DATE"},
            {"contains": "FROM pg_indexes", "fetchone": (1,)},
            {"contains": "CREATE TEMP TABLE tmp_jobs_import"},
            {"contains": "UPDATE tmp_jobs_import"},
            {"contains": "DROP TABLE IF EXISTS tmp_jobs_job_url_dedup_map"},
            {"contains": "CREATE TEMP TABLE tmp_jobs_job_url_dedup_map"},
            {"contains": "JOIN jobs AS source_external_job"},
            {
                "contains": "SELECT COUNT(*) FROM tmp_jobs_job_url_dedup_map",
                "fetchone": (0,),
            },
            {"contains": "UPDATE jobs AS existing_job"},
            {
                "contains": "JOIN jobs j\n          ON j.job_url = s.job_url",
                "fetchall": [],
            },
            {
                "contains": "WHERE j.title IS DISTINCT FROM s.title",
                "fetchall": [],
            },
            {"contains": "ON CONFLICT (job_url) DO UPDATE"},
            {"contains": "FROM information_schema.columns", "fetchall": []},
        ]
        fake_cursor = FakeCursor(scripted_steps)
        fake_connection = FakeConnection(fake_cursor)
        captured_values: list[tuple[object, ...]] = []

        def fake_execute_values(cursor, sql, values, page_size=100):
            self.assertIn("is_duplicate", sql)
            captured_values.extend(values)

        with patch("jobspy.jobs_table._get_db_connection", return_value=fake_connection):
            with patch("psycopg2.extras.execute_values", side_effect=fake_execute_values):
                summary = jobs_table._bulk_upsert_jobs(
                    [
                        {
                            "title": "Backend Engineer",
                            "location": "Tel Aviv",
                            "posted_time": "2026-04-05",
                            "published_at": None,
                            "job_url": "https://example.com/jobs/1",
                            "company_name": "Acme",
                            "company_url": "https://example.com/company/acme",
                            "company_id": "acme",
                            "description": "Build services",
                            "applications_count": "3",
                            "contract_type": "full-time",
                            "experience_level": "mid",
                            "work_type": "remote",
                            "sector": "software",
                            "salary": None,
                            "poster_full_name": None,
                            "poster_profile_url": None,
                            "apply_url": "https://example.com/jobs/1/apply",
                            "apply_type": "external",
                            "benefits": None,
                            "source": "linkedin",
                            "external_id": "new-external-id",
                            "is_duplicate": True,
                            "raw_json": {"job_url": "https://example.com/jobs/1"},
                        }
                    ],
                    include_duplicate_flag=True,
                )

        self.assertEqual(summary["inserted"], 1)
        self.assertTrue(captured_values)
        self.assertIs(captured_values[0][-2], True)
        create_staging_sql = next(
            sql
            for sql in fake_cursor.executed_sql
            if "CREATE TEMP TABLE tmp_jobs_import" in sql
        )
        upsert_sql = next(
            sql
            for sql in fake_cursor.executed_sql
            if "ON CONFLICT (job_url) DO UPDATE" in sql
        )
        self.assertIn("is_duplicate BOOLEAN", create_staging_sql)
        self.assertIn("is_duplicate = EXCLUDED.is_duplicate", upsert_sql)

    def test_bulk_upsert_jobs_merges_cross_key_identity_collisions(self) -> None:
        scripted_steps = [
            {"contains": "ADD COLUMN IF NOT EXISTS reposted_at DATE"},
            {"contains": "FROM pg_indexes", "fetchone": (1,)},
            {"contains": "CREATE TEMP TABLE tmp_jobs_import"},
            {"contains": "UPDATE tmp_jobs_import"},
            {"contains": "DROP TABLE IF EXISTS tmp_jobs_job_url_dedup_map"},
            {"contains": "CREATE TEMP TABLE tmp_jobs_job_url_dedup_map"},
            {
                "contains": "JOIN jobs AS source_external_job",
            },
            {
                "contains": "SELECT COUNT(*) FROM tmp_jobs_job_url_dedup_map",
                "fetchone": (1,),
            },
            {"contains": "UPDATE jobs AS winner"},
            {"contains": "UPDATE user_job_first_match AS winner"},
            {"contains": "DELETE FROM user_job_first_match AS loser"},
            {"contains": "UPDATE user_job_first_match AS row_to_move"},
            {"contains": "UPDATE user_job_kanban_cards AS winner"},
            {"contains": "DELETE FROM user_job_kanban_cards AS loser"},
            {"contains": "UPDATE user_job_kanban_cards AS row_to_move"},
            {"contains": "UPDATE job_match_email_deliveries AS winner"},
            {"contains": "DELETE FROM job_match_email_deliveries AS loser"},
            {"contains": "UPDATE job_match_email_deliveries AS row_to_move"},
            {"contains": "DELETE FROM jobs AS duplicate_jobs", "fetchone": (1,)},
            {"contains": "UPDATE jobs AS existing_job"},
            {
                "contains": "JOIN jobs j\n          ON j.job_url = s.job_url",
                "fetchall": [("https://example.com/jobs/1", "4370503008")],
            },
            {
                "contains": "WHERE j.title IS DISTINCT FROM s.title",
                "fetchall": [("https://example.com/jobs/1", "4370503008")],
            },
            {
                "contains": "COALESCE(NULLIF(BTRIM(s.external_id), ''), NULLIF(BTRIM(j.external_id), ''), s.job_url) AS job_id",
                "fetchall": [],
            },
            {"contains": "ON CONFLICT (job_url) DO UPDATE"},
            {"contains": "FROM information_schema.columns", "fetchall": []},
        ]
        fake_cursor = FakeCursor(scripted_steps)
        fake_connection = FakeConnection(fake_cursor)

        with patch("jobspy.jobs_table._get_db_connection", return_value=fake_connection):
            with patch("psycopg2.extras.execute_values") as mock_execute_values:
                jobs_table._bulk_upsert_jobs(
                    [
                        {
                            "title": "Backend Engineer",
                            "location": "Tel Aviv",
                            "posted_time": "2026-04-05",
                            "published_at": None,
                            "job_url": "https://example.com/jobs/1",
                            "company_name": "Acme",
                            "company_url": "https://example.com/company/acme",
                            "company_id": "acme",
                            "description": "Build services",
                            "applications_count": "3",
                            "contract_type": "full-time",
                            "experience_level": "mid",
                            "work_type": "remote",
                            "sector": "software",
                            "salary": None,
                            "poster_full_name": None,
                            "poster_profile_url": None,
                            "apply_url": "https://example.com/jobs/1/apply",
                            "apply_type": "external",
                            "benefits": None,
                            "source": "linkedin",
                            "external_id": "4370503008",
                            "raw_json": {"job_url": "https://example.com/jobs/1"},
                        }
                    ]
                )

        self.assertTrue(mock_execute_values.called)
        self.assertTrue(
            any(
                "JOIN jobs AS source_external_job" in sql
                for sql in fake_cursor.executed_sql
            )
        )
        self.assertTrue(
            any(
                "source_external_job.external_id = staged_job.external_id" in sql
                for sql in fake_cursor.executed_sql
            )
        )
        self.assertTrue(
            any(
                "job_url_job.job_url = staged_job.job_url" in sql
                for sql in fake_cursor.executed_sql
            )
        )
        self.assertTrue(
            any(
                "DELETE FROM jobs AS duplicate_jobs" in sql
                for sql in fake_cursor.executed_sql
            )
        )

    def test_bulk_upsert_jobs_preserves_existing_job_dates_and_skips_date_only_refreshes(
        self,
    ) -> None:
        scripted_steps = [
            {"contains": "ADD COLUMN IF NOT EXISTS reposted_at DATE"},
            {"contains": "FROM pg_indexes", "fetchone": (1,)},
            {"contains": "CREATE TEMP TABLE tmp_jobs_import"},
            {"contains": "UPDATE tmp_jobs_import"},
            {"contains": "DROP TABLE IF EXISTS tmp_jobs_job_url_dedup_map"},
            {"contains": "CREATE TEMP TABLE tmp_jobs_job_url_dedup_map"},
            {
                "contains": "JOIN jobs AS source_external_job",
            },
            {
                "contains": "SELECT COUNT(*) FROM tmp_jobs_job_url_dedup_map",
                "fetchone": (0,),
            },
            {"contains": "UPDATE jobs AS existing_job"},
            {
                "contains": "JOIN jobs j\n          ON j.job_url = s.job_url",
                "fetchall": [("https://example.com/jobs/1", "new-external-id")],
            },
            {
                "contains": "WHERE j.title IS DISTINCT FROM s.title",
                "fetchall": [],
            },
            {"contains": "ON CONFLICT (job_url) DO UPDATE"},
        ]
        fake_cursor = FakeCursor(scripted_steps)
        fake_connection = FakeConnection(fake_cursor)

        with patch("jobspy.jobs_table._get_db_connection", return_value=fake_connection):
            with patch("psycopg2.extras.execute_values"):
                summary = jobs_table._bulk_upsert_jobs(
                    [
                        {
                            "title": "Backend Engineer",
                            "location": "Tel Aviv",
                            "posted_time": "2026-06-07",
                            "published_at": None,
                            "job_url": "https://example.com/jobs/1",
                            "company_name": "Acme",
                            "company_url": "https://example.com/company/acme",
                            "company_id": "acme",
                            "description": "Build services",
                            "applications_count": "3",
                            "contract_type": "full-time",
                            "experience_level": "mid",
                            "work_type": "remote",
                            "sector": "software",
                            "salary": None,
                            "poster_full_name": None,
                            "poster_profile_url": None,
                            "apply_url": "https://example.com/jobs/1/apply",
                            "apply_type": "external",
                            "benefits": None,
                            "source": "comeet",
                            "external_id": "new-external-id",
                            "raw_json": {
                                "job_url": "https://example.com/jobs/1",
                                "date_posted": "2026-06-07",
                            },
                        }
                    ]
                )

        self.assertEqual(summary["inserted"], 0)
        self.assertEqual(summary["updated"], 0)

        upsert_sql = next(
            sql
            for sql in fake_cursor.executed_sql
            if "ON CONFLICT (job_url) DO UPDATE" in sql
        )
        self.assertIn(
            "posted_time = COALESCE(jobs.posted_time, EXCLUDED.posted_time)",
            upsert_sql,
        )
        self.assertIn(
            "published_at = COALESCE(jobs.published_at, EXCLUDED.published_at)",
            upsert_sql,
        )
        self.assertIn("reposted_at = CASE", upsert_sql)
        self.assertIn("WHEN EXCLUDED.source = 'linkedin'", upsert_sql)
        self.assertIn(
            "description = COALESCE(NULLIF(BTRIM(EXCLUDED.description), ''), jobs.description)",
            upsert_sql,
        )
        self.assertIn(
            "COALESCE(jobs.raw_json, '{}'::jsonb) ? 'date_posted'",
            upsert_sql,
        )
        self.assertIn(
            "COALESCE(EXCLUDED.raw_json, '{}'::jsonb) - 'description'",
            upsert_sql,
        )
        self.assertIn(
            "COALESCE(jobs.raw_json, '{}'::jsonb) || (CASE",
            upsert_sql,
        )

    def test_bulk_upsert_jobs_treats_linkedin_newer_posted_date_as_repost(
        self,
    ) -> None:
        scripted_steps = [
            {"contains": "ADD COLUMN IF NOT EXISTS reposted_at DATE"},
            {"contains": "FROM pg_indexes", "fetchone": (1,)},
            {"contains": "CREATE TEMP TABLE tmp_jobs_import"},
            {"contains": "UPDATE tmp_jobs_import"},
            {"contains": "DROP TABLE IF EXISTS tmp_jobs_job_url_dedup_map"},
            {"contains": "CREATE TEMP TABLE tmp_jobs_job_url_dedup_map"},
            {
                "contains": "JOIN jobs AS source_external_job",
            },
            {
                "contains": "SELECT COUNT(*) FROM tmp_jobs_job_url_dedup_map",
                "fetchone": (0,),
            },
            {"contains": "UPDATE jobs AS existing_job"},
            {
                "contains": "JOIN jobs j\n          ON j.job_url = s.job_url",
                "fetchall": [("https://www.linkedin.com/jobs/view/1001", "1001")],
            },
            {
                "contains": "j.reposted_at IS DISTINCT FROM CASE",
                "fetchall": [("https://www.linkedin.com/jobs/view/1001", "1001")],
            },
            {
                "contains": "COALESCE(NULLIF(BTRIM(s.external_id), ''), NULLIF(BTRIM(j.external_id), ''), s.job_url) AS job_id",
                "fetchall": [],
            },
            {"contains": "ON CONFLICT (job_url) DO UPDATE"},
            {"contains": "FROM information_schema.columns", "fetchall": []},
        ]
        fake_cursor = FakeCursor(scripted_steps)
        fake_connection = FakeConnection(fake_cursor)

        with patch("jobspy.jobs_table._get_db_connection", return_value=fake_connection):
            with patch("psycopg2.extras.execute_values"):
                summary = jobs_table._bulk_upsert_jobs(
                    [
                        {
                            "title": "Backend Engineer",
                            "location": "Tel Aviv",
                            "posted_time": "2026-06-12",
                            "published_at": date(2026, 6, 12),
                            "job_url": "https://www.linkedin.com/jobs/view/1001",
                            "company_name": "Acme",
                            "company_url": "https://www.linkedin.com/company/acme",
                            "company_id": "acme",
                            "description": "Build services",
                            "applications_count": "3",
                            "contract_type": "full-time",
                            "experience_level": "mid",
                            "work_type": "remote",
                            "sector": "software",
                            "salary": None,
                            "poster_full_name": None,
                            "poster_profile_url": None,
                            "apply_url": "https://www.linkedin.com/jobs/view/1001/apply",
                            "apply_type": "linkedin",
                            "benefits": None,
                            "source": "linkedin",
                            "external_id": "1001",
                            "raw_json": {
                                "job_url": "https://www.linkedin.com/jobs/view/1001",
                                "date_posted": "2026-06-12",
                            },
                        }
                    ]
                )

        self.assertEqual(summary["inserted"], 0)
        self.assertEqual(summary["updated"], 1)

        select_changed_sql = next(
            sql
            for sql in fake_cursor.executed_sql
            if "j.reposted_at IS DISTINCT FROM CASE" in sql
        )
        self.assertIn("WHEN s.source = 'linkedin'", select_changed_sql)
        self.assertIn("AND s.published_at IS NOT NULL", select_changed_sql)
        self.assertIn("AND j.published_at IS NOT NULL", select_changed_sql)
        self.assertIn(
            "AND s.published_at > COALESCE(GREATEST(j.published_at, j.reposted_at), j.published_at, j.reposted_at)",
            select_changed_sql,
        )

        upsert_sql = next(
            sql
            for sql in fake_cursor.executed_sql
            if "ON CONFLICT (job_url) DO UPDATE" in sql
        )
        self.assertIn("reposted_at = CASE", upsert_sql)
        self.assertIn("WHEN EXCLUDED.source = 'linkedin'", upsert_sql)

    def test_bulk_upsert_jobs_bulk_activates_reposted_linkedin_jobs_parsed(
        self,
    ) -> None:
        scripted_steps = [
            {"contains": "ADD COLUMN IF NOT EXISTS reposted_at DATE"},
            {"contains": "FROM pg_indexes", "fetchone": (1,)},
            {"contains": "CREATE TEMP TABLE tmp_jobs_import"},
            {"contains": "UPDATE tmp_jobs_import"},
            {"contains": "DROP TABLE IF EXISTS tmp_jobs_job_url_dedup_map"},
            {"contains": "CREATE TEMP TABLE tmp_jobs_job_url_dedup_map"},
            {"contains": "JOIN jobs AS source_external_job"},
            {
                "contains": "SELECT COUNT(*) FROM tmp_jobs_job_url_dedup_map",
                "fetchone": (0,),
            },
            {"contains": "UPDATE jobs AS existing_job"},
            {
                "contains": "JOIN jobs j\n          ON j.job_url = s.job_url",
                "fetchall": [],
            },
            {
                "contains": "WHERE j.title IS DISTINCT FROM s.title",
                "fetchall": [],
            },
            {"contains": "ON CONFLICT (job_url) DO UPDATE"},
            {
                "contains": "FROM information_schema.columns",
                "fetchall": [
                    ("raw_job_id",),
                    ("status",),
                ],
            },
            {
                "contains": "UPDATE jobs_parsed AS jp",
                "fetchall": [(1,), (1,)],
            },
        ]
        fake_cursor = FakeCursor(scripted_steps)
        fake_connection = FakeConnection(fake_cursor)

        with patch("jobspy.jobs_table._get_db_connection", return_value=fake_connection):
            with patch("psycopg2.extras.execute_values"):
                summary = jobs_table._bulk_upsert_jobs(
                    [
                        {
                            "title": "Backend Engineer",
                            "location": "Tel Aviv",
                            "posted_time": "2026-06-12",
                            "published_at": date(2026, 6, 12),
                            "job_url": "https://www.linkedin.com/jobs/view/1001",
                            "company_name": "Acme",
                            "company_url": "https://www.linkedin.com/company/acme",
                            "company_id": "acme",
                            "description": "Build services",
                            "applications_count": "3",
                            "contract_type": "full-time",
                            "experience_level": "mid",
                            "work_type": "remote",
                            "sector": "software",
                            "salary": None,
                            "poster_full_name": None,
                            "poster_profile_url": None,
                            "apply_url": "https://www.linkedin.com/jobs/view/1001/apply",
                            "apply_type": "linkedin",
                            "benefits": None,
                            "source": "linkedin",
                            "external_id": "1001",
                            "raw_json": {
                                "job_url": "https://www.linkedin.com/jobs/view/1001",
                                "date_posted": "2026-06-12",
                            },
                        }
                    ]
                )

        self.assertEqual(summary["parsed_jobs_activated"], 2)

        jobs_parsed_sql = next(
            sql
            for sql in fake_cursor.executed_sql
            if "UPDATE jobs_parsed AS jp" in sql
        )
        self.assertIn("WITH reposted_linkedin_jobs AS", jobs_parsed_sql)
        self.assertIn("JOIN tmp_jobs_import s", jobs_parsed_sql)
        self.assertIn("AND j.reposted_at IS NOT NULL", jobs_parsed_sql)
        self.assertIn("UPDATE jobs_parsed AS jp", jobs_parsed_sql)
        self.assertIn("SET status = %s", jobs_parsed_sql)
        self.assertIn("jp.raw_job_id = rlj.id", jobs_parsed_sql)
        self.assertIn("jp.status IS DISTINCT FROM %s", jobs_parsed_sql)
        self.assertIn(
            (jobs_table.LINKEDIN_SOURCE, "active", "active"),
            fake_cursor.executed_params,
        )

    def test_populate_jobs_table_from_file_dedupes_duplicate_job_urls_in_input(self) -> None:
        rows = [
            {
                "site": "linkedin",
                "title": "Data Engineer",
                "company": "Acme",
                "location": "Tel Aviv",
                "date_posted": "2026-04-05",
                "job_url": "https://www.linkedin.com/jobs/view/4312995054?trackingId=abc",
                "description": "first copy",
            },
            {
                "site": "linkedin",
                "title": "Data Engineer",
                "company": "Acme",
                "location": "Tel Aviv",
                "date_posted": "2026-04-05",
                "job_url": "https://www.linkedin.com/jobs/view/4312995054",
                "description": "second copy wins",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path = Path(tmp_dir) / "linkedin_jobs.json"
            json_path.write_text(json.dumps(rows), encoding="utf-8")
            captured_records: list[dict[str, object]] = []

            def fake_bulk_upsert(records):
                captured_records.extend(records)
                return {
                    "inserted": 1,
                    "inserted_job_urls": [
                        "https://www.linkedin.com/jobs/view/4312995054",
                    ],
                    "updated": 0,
                    "updated_external_ids": [],
                    "updated_job_urls": [],
                    "deleted_duplicate_rows": 0,
                    "failed": 0,
                }

            with patch("jobspy.jobs_table._bulk_upsert_jobs", side_effect=fake_bulk_upsert):
                summary = jobs_table.populate_jobs_table_from_file(json_path)

        self.assertEqual(summary["prepared_records"], 1)
        self.assertEqual(
            summary["inserted_job_urls"],
            ["https://www.linkedin.com/jobs/view/4312995054"],
        )
        self.assertEqual(summary["skipped_duplicate_input"], 1)
        self.assertEqual(len(captured_records), 1)
        self.assertEqual(
            captured_records[0]["job_url"],
            "https://www.linkedin.com/jobs/view/4312995054",
        )
        self.assertEqual(captured_records[0]["description"], "second copy wins")

    def test_populate_jobs_table_from_file_keeps_linkedin_apply_fields(self) -> None:
        rows = [
            {
                "site": "linkedin",
                "title": "Data Engineer",
                "company": "Acme",
                "location": "Tel Aviv",
                "date_posted": "2026-04-05",
                "job_url": "https://www.linkedin.com/jobs/view/4312995054",
                "apply_url": "https://www.linkedin.com/jobs/view/4312995054/apply",
                "job_url_direct": "https://company.example.com/jobs/4312995054/apply",
                "company_logo": "https://cdn.example.com/logo.png",
                "description": "guest-only copy",
            }
        ]

        json_path = Path(__file__).resolve().parents[1] / ".tmp_linkedin_guest_only_jobs.json"
        captured_records: list[dict[str, object]] = []

        def fake_bulk_upsert(records):
            captured_records.extend(records)
            return {
                "inserted": 1,
                "updated": 0,
                "updated_external_ids": [],
                "updated_job_urls": [],
                "deleted_duplicate_rows": 0,
                "failed": 0,
            }

        try:
            json_path.write_text(json.dumps(rows), encoding="utf-8")
            with patch("jobspy.jobs_table._bulk_upsert_jobs", side_effect=fake_bulk_upsert):
                summary = jobs_table.populate_jobs_table_from_file(json_path)
        finally:
            json_path.unlink(missing_ok=True)

        self.assertEqual(summary["prepared_records"], 1)
        self.assertEqual(len(captured_records), 1)
        self.assertEqual(
            captured_records[0]["apply_url"],
            "https://company.example.com/jobs/4312995054/apply",
        )
        self.assertEqual(captured_records[0]["apply_type"], "external")

    def test_populate_jobs_table_from_file_does_not_print_summary(self) -> None:
        rows = [
            {
                "site": "linkedin",
                "title": "Backend Engineer",
                "company": "Acme",
                "location": "Tel Aviv",
                "date_posted": "2026-04-05",
                "job_url": "https://www.linkedin.com/jobs/view/4312995054",
                "description": "guest-only copy",
            }
        ]

        json_path = (
            Path(__file__).resolve().parents[1]
            / ".tmp_linkedin_jobs_no_console_summary.json"
        )
        try:
            json_path.write_text(json.dumps(rows), encoding="utf-8")

            def fake_bulk_upsert(records):
                return {
                    "inserted": len(records),
                    "updated": 0,
                    "updated_external_ids": [],
                    "updated_job_urls": [],
                    "deleted_duplicate_rows": 0,
                    "failed": 0,
                }

            with patch("jobspy.jobs_table._bulk_upsert_jobs", side_effect=fake_bulk_upsert):
                with patch("builtins.print") as mock_print:
                    summary = jobs_table.populate_jobs_table_from_file(json_path)
        finally:
            json_path.unlink(missing_ok=True)

        self.assertEqual(summary["prepared_records"], 1)
        self.assertEqual(summary["inserted"], 1)
        mock_print.assert_not_called()

    def test_populate_comeet_jobs_table_dedupes_duplicate_job_urls_in_input(self) -> None:
        rows = [
            {
                "title": "Platform Engineer",
                "company": "Acme",
                "location": "Israel",
                "date_posted": "2026-04-05",
                "job_url": "https://www.comeet.com/jobs/acme/AA.001/platform-engineer/12.345?utm_source=test",
                "description": "first copy",
            },
            {
                "title": "Platform Engineer",
                "company": "Acme",
                "location": "Israel",
                "date_posted": "2026-04-05",
                "job_url": "https://www.comeet.com/jobs/acme/AA.001/platform-engineer/12.345",
                "description": "second copy wins",
            },
        ]
        captured_records: list[dict[str, object]] = []

        def fake_bulk_upsert(records):
            captured_records.extend(records)
            return {
                "inserted": 1,
                "updated": 0,
                "updated_external_ids": [],
                "updated_job_urls": [],
                "deleted_duplicate_rows": 0,
                "failed": 0,
            }

        with patch("jobspy.jobs_table._bulk_upsert_jobs", side_effect=fake_bulk_upsert):
            summary = jobs_table.populate_comeet_jobs_table(rows)

        self.assertEqual(summary["prepared_records"], 1)
        self.assertEqual(summary["skipped_duplicate_input"], 1)
        self.assertEqual(len(captured_records), 1)
        self.assertEqual(
            captured_records[0]["job_url"],
            "https://www.comeet.com/jobs/acme/AA.001/platform-engineer/12.345",
        )
        self.assertEqual(captured_records[0]["description"], "second copy wins")

    def test_populate_comeet_jobs_table_does_not_print_summary(self) -> None:
        rows = [
            {
                "title": "Platform Engineer",
                "company": "Acme",
                "location": "Israel",
                "date_posted": "2026-04-05",
                "job_url": "https://www.comeet.com/jobs/acme/AA.001/platform-engineer/12.345",
                "description": "first copy",
            }
        ]

        def fake_bulk_upsert(records):
            return {
                "inserted": len(records),
                "updated": 0,
                "updated_external_ids": [],
                "updated_job_urls": [],
                "deleted_duplicate_rows": 0,
                "failed": 0,
            }

        with patch("jobspy.jobs_table._bulk_upsert_jobs", side_effect=fake_bulk_upsert):
            with patch("builtins.print") as mock_print:
                summary = jobs_table.populate_comeet_jobs_table(rows)

        self.assertEqual(summary["prepared_records"], 1)
        self.assertEqual(summary["inserted"], 1)
        mock_print.assert_not_called()

    def test_populate_jobs_table_from_file_builds_comeet_records(self) -> None:
        rows = [
            {
                "site": "comeet",
                "title": "Product Manager",
                "company": "365scores",
                "location": "Tel Aviv-Yafo, Tel Aviv District, Israel",
                "date_posted": "2026-06-15",
                "job_url": (
                    "https://www.comeet.com/jobs/365scores/B3.006/"
                    "product-manager/81.A6B?utm_source=test"
                ),
                "apply_url": "https://www.comeet.com/jobs/365scores/B3.006/product-manager/81.A6B",
                "job_url_direct": "https://www.comeet.com/jobs/365scores/B3.006/product-manager/81.A6B",
                "listing_type": "hybrid",
                "description": "Lead product discovery",
            }
        ]

        json_path = (
            Path(__file__).resolve().parents[1]
            / ".tmp_company_career_pages_comeet_jobs.json"
        )
        try:
            json_path.write_text(json.dumps(rows), encoding="utf-8")
            captured_records: list[dict[str, object]] = []

            def fake_bulk_upsert(records):
                captured_records.extend(records)
                return {
                    "inserted": 1,
                    "updated": 0,
                    "updated_external_ids": [],
                    "updated_job_urls": [],
                    "deleted_duplicate_rows": 0,
                    "failed": 0,
                }

            with patch("jobspy.jobs_table._bulk_upsert_jobs", side_effect=fake_bulk_upsert):
                summary = jobs_table.populate_jobs_table_from_file(json_path)
        finally:
            json_path.unlink(missing_ok=True)

        self.assertEqual(summary["prepared_records"], 1)
        self.assertEqual(len(captured_records), 1)
        self.assertEqual(captured_records[0]["source"], "comeet")
        self.assertEqual(
            captured_records[0]["job_url"],
            "https://www.comeet.com/jobs/365scores/B3.006/product-manager/81.A6B",
        )
        self.assertEqual(
            captured_records[0]["company_id"],
            "https://www.comeet.com/jobs/365scores/B3.006",
        )
        self.assertEqual(captured_records[0]["company_name"], "365scores")
        self.assertEqual(captured_records[0]["published_at"], date(2026, 6, 15))
        self.assertEqual(captured_records[0]["work_type"], "hybrid")

    def test_populate_jobs_table_from_file_builds_greenhouse_records(self) -> None:
        rows = [
            {
                "site": "greenhouse",
                "title": "Product Designer",
                "company": "Acme",
                "location": "Tel Aviv, TA",
                "date_posted": "2026-04-05",
                "job_url": "https://jobs.acme.com/careers/openings?gh_jid=8480987002&utm_source=test",
                "apply_url": "https://jobs.acme.com/careers/openings?gh_jid=8480987002",
                "listing_type": "hybrid",
                "description": "Design product experiences",
            }
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path = Path(tmp_dir) / "greenhouse_jobs.json"
            json_path.write_text(json.dumps(rows), encoding="utf-8")
            captured_records: list[dict[str, object]] = []

            def fake_bulk_upsert(records):
                captured_records.extend(records)
                return {
                    "inserted": 1,
                    "updated": 0,
                    "updated_external_ids": [],
                    "updated_job_urls": [],
                    "deleted_duplicate_rows": 0,
                    "failed": 0,
                }

            with patch("jobspy.jobs_table._bulk_upsert_jobs", side_effect=fake_bulk_upsert):
                summary = jobs_table.populate_jobs_table_from_file(json_path)

        self.assertEqual(summary["prepared_records"], 1)
        self.assertEqual(len(captured_records), 1)
        self.assertEqual(captured_records[0]["source"], "greenhouse")
        self.assertEqual(captured_records[0]["external_id"], "8480987002")
        self.assertEqual(
            captured_records[0]["job_url"],
            "https://jobs.acme.com/careers/openings?gh_jid=8480987002",
        )
        self.assertEqual(captured_records[0]["company_url"], "https://jobs.acme.com")
        self.assertEqual(captured_records[0]["work_type"], "hybrid")

    def test_populate_jobs_table_from_file_builds_glassdoor_records(self) -> None:
        rows = [
            {
                "site": "glassdoor",
                "title": "Software Engineer",
                "company": "Acme",
                "location": "Tel Aviv",
                "date_posted": "2026-04-05",
                "job_url": "https://www.glassdoor.com/job-listing/j?jl=1009660336259&utm_campaign=test",
                "company_url": "https://www.glassdoor.com/Overview/W-EI_IE8605843.htm?utm_source=test",
                "is_remote": False,
                "description": "Build product systems",
            }
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path = Path(tmp_dir) / "glassdoor_jobs.json"
            json_path.write_text(json.dumps(rows), encoding="utf-8")
            captured_records: list[dict[str, object]] = []

            def fake_bulk_upsert(records):
                captured_records.extend(records)
                return {
                    "inserted": 1,
                    "updated": 0,
                    "updated_external_ids": [],
                    "updated_job_urls": [],
                    "deleted_duplicate_rows": 0,
                    "failed": 0,
                }

            with patch("jobspy.jobs_table._bulk_upsert_jobs", side_effect=fake_bulk_upsert):
                summary = jobs_table.populate_jobs_table_from_file(json_path)

        self.assertEqual(summary["prepared_records"], 1)
        self.assertEqual(len(captured_records), 1)
        self.assertEqual(captured_records[0]["source"], "glassdoor")
        self.assertEqual(captured_records[0]["external_id"], "1009660336259")
        self.assertEqual(
            captured_records[0]["job_url"],
            "https://www.glassdoor.com/job-listing/j?jl=1009660336259",
        )
        self.assertEqual(
            captured_records[0]["company_url"],
            "https://www.glassdoor.com/Overview/W-EI_IE8605843.htm",
        )
        self.assertEqual(captured_records[0]["company_id"], "8605843")
        self.assertEqual(
            captured_records[0]["apply_url"],
            "https://www.glassdoor.com/job-listing/j?jl=1009660336259",
        )

    def test_populate_jobs_table_from_file_builds_eightfold_records(self) -> None:
        rows = [
            {
                "site": "eightfold",
                "id": "563431010318975",
                "title": "Software Engineer",
                "company": "Amdocs",
                "location": "Ra'anana, Center District, Israel",
                "date_posted": "2026-04-05",
                "job_url": (
                    "https://jobs.amdocs.com/careers/job/563431010318975"
                    "?domain=amdocs.com&utm_source=test"
                ),
                "apply_url": "https://jobs.amdocs.com/careers/job/563431010318975",
                "company_url": "https://www.amdocs.com/careers/home?utm_source=test",
                "listing_type": "hybrid",
                "description": "Build distributed systems",
            }
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path = Path(tmp_dir) / "amdocs_jobs.json"
            json_path.write_text(json.dumps(rows), encoding="utf-8")
            captured_records: list[dict[str, object]] = []

            def fake_bulk_upsert(records):
                captured_records.extend(records)
                return {
                    "inserted": 1,
                    "updated": 0,
                    "updated_external_ids": [],
                    "updated_job_urls": [],
                    "deleted_duplicate_rows": 0,
                    "failed": 0,
                }

            with patch("jobspy.jobs_table._bulk_upsert_jobs", side_effect=fake_bulk_upsert):
                summary = jobs_table.populate_jobs_table_from_file(json_path)

        self.assertEqual(summary["prepared_records"], 1)
        self.assertEqual(len(captured_records), 1)
        self.assertEqual(captured_records[0]["source"], "eightfold")
        self.assertEqual(captured_records[0]["external_id"], "563431010318975")
        self.assertEqual(
            captured_records[0]["job_url"],
            "https://jobs.amdocs.com/careers/job/563431010318975",
        )
        self.assertEqual(
            captured_records[0]["company_url"],
            "https://www.amdocs.com/careers/home",
        )
        self.assertEqual(captured_records[0]["company_id"], "www.amdocs.com")
        self.assertEqual(captured_records[0]["work_type"], "hybrid")
        self.assertEqual(
            captured_records[0]["apply_url"],
            "https://jobs.amdocs.com/careers/job/563431010318975",
        )

    def test_populate_jobs_table_from_file_builds_workday_records(self) -> None:
        rows = [
            {
                "site": "workday",
                "id": "2503821",
                "title": "Principal Hardware Board Design Engineer",
                "company": "Marvell",
                "location": "Yokneam, Israel",
                "date_posted": "2026-04-15",
                "job_url": (
                    "https://marvell.wd1.myworkdayjobs.com/MarvellCareers"
                    "/job/Yokneam/Principal-Hardware-System-Design-Engineer_2503821"
                    "?utm_source=test"
                ),
                "apply_url": (
                    "https://marvell.wd1.myworkdayjobs.com/MarvellCareers"
                    "/job/Yokneam/Principal-Hardware-System-Design-Engineer_2503821"
                ),
                "company_url": (
                    "https://marvell.wd1.myworkdayjobs.com/MarvellCareers"
                    "?Country=084562884af243748dad7c84c304d89a"
                ),
                "job_type": "fulltime",
                "description": "Build boards",
            }
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path = Path(tmp_dir) / "marvell_jobs.json"
            json_path.write_text(json.dumps(rows), encoding="utf-8")
            captured_records: list[dict[str, object]] = []

            def fake_bulk_upsert(records):
                captured_records.extend(records)
                return {
                    "inserted": 1,
                    "updated": 0,
                    "updated_external_ids": [],
                    "updated_job_urls": [],
                    "deleted_duplicate_rows": 0,
                    "failed": 0,
                }

            with patch("jobspy.jobs_table._bulk_upsert_jobs", side_effect=fake_bulk_upsert):
                summary = jobs_table.populate_jobs_table_from_file(json_path)

        self.assertEqual(summary["prepared_records"], 1)
        self.assertEqual(len(captured_records), 1)
        self.assertEqual(captured_records[0]["source"], "workday")
        self.assertEqual(captured_records[0]["external_id"], "2503821")
        self.assertEqual(
            captured_records[0]["job_url"],
            "https://marvell.wd1.myworkdayjobs.com/MarvellCareers/job/Yokneam/Principal-Hardware-System-Design-Engineer_2503821",
        )
        self.assertEqual(
            captured_records[0]["company_url"],
            "https://marvell.wd1.myworkdayjobs.com/MarvellCareers",
        )
        self.assertEqual(
            captured_records[0]["company_id"],
            "https://marvell.wd1.myworkdayjobs.com/MarvellCareers",
        )
        self.assertEqual(
            captured_records[0]["apply_url"],
            "https://marvell.wd1.myworkdayjobs.com/MarvellCareers/job/Yokneam/Principal-Hardware-System-Design-Engineer_2503821",
        )

    def test_populate_jobs_table_from_file_builds_redhat_records_via_workday_normalizer(
        self,
    ) -> None:
        rows = [
            {
                "site": "redhat",
                "id": "R-056395",
                "title": "Senior Software Engineer",
                "company": "Red Hat",
                "location": "Raanana, Israel",
                "date_posted": "2026-04-28",
                "job_url": (
                    "https://redhat.wd5.myworkdayjobs.com/Jobs/job/Raanana/"
                    "Senior-Software-Engineer_R-056395-1?utm_source=test"
                ),
                "apply_url": (
                    "https://redhat.wd5.myworkdayjobs.com/Jobs/job/Raanana/"
                    "Senior-Software-Engineer_R-056395-1"
                ),
                "company_url": "https://redhat.wd5.myworkdayjobs.com/Jobs?a=test",
                "job_type": "fulltime",
                "description": "Build open source platforms",
            }
        ]

        json_path = Path.cwd() / ".tmp_redhat_jobs_table_test.json"
        try:
            json_path.write_text(json.dumps(rows), encoding="utf-8")
            captured_records: list[dict[str, object]] = []

            def fake_bulk_upsert(records):
                captured_records.extend(records)
                return {
                    "inserted": 1,
                    "updated": 0,
                    "updated_external_ids": [],
                    "updated_job_urls": [],
                    "deleted_duplicate_rows": 0,
                    "failed": 0,
                }

            with patch("jobspy.jobs_table._bulk_upsert_jobs", side_effect=fake_bulk_upsert):
                summary = jobs_table.populate_jobs_table_from_file(json_path)
        finally:
            json_path.unlink(missing_ok=True)

        self.assertEqual(summary["prepared_records"], 1)
        self.assertEqual(len(captured_records), 1)
        self.assertEqual(captured_records[0]["source"], "workday")
        self.assertEqual(captured_records[0]["external_id"], "R-056395")
        self.assertEqual(
            captured_records[0]["job_url"],
            "https://redhat.wd5.myworkdayjobs.com/Jobs/job/Raanana/Senior-Software-Engineer_R-056395-1",
        )
        self.assertEqual(
            captured_records[0]["company_url"],
            "https://redhat.wd5.myworkdayjobs.com/Jobs",
        )
        self.assertEqual(
            captured_records[0]["apply_url"],
            "https://redhat.wd5.myworkdayjobs.com/Jobs/job/Raanana/Senior-Software-Engineer_R-056395-1",
        )

    def test_populate_jobs_table_from_file_builds_varonis_records(self) -> None:
        rows = [
            {
                "site": "varonis",
                "id": "ohHUyfwa",
                "title": "R&D Infrastructure and Labs Manager",
                "company": "Varonis",
                "location": "Herzliya, Israel",
                "job_function": "R&D",
                "listing_type": "Engineering",
                "job_url": (
                    "https://jobs.jobvite.com/careers/varonis/job/ohHUyfwa"
                    "?jvk=Job&j=ohHUyfwa"
                ),
                "apply_url": (
                    "https://app.jobvite.com/CompanyJobs/Careers.aspx"
                    "?k=Apply&j=ohHUyfwa&c=qTjaVfw1&l=CFtKVfwx"
                ),
                "company_url": "https://careers.varonis.com/",
                "description": "Manage infrastructure",
            }
        ]

        json_path = Path.cwd() / ".tmp_varonis_jobs_table_test.json"
        json_path.write_text(json.dumps(rows), encoding="utf-8")
        captured_records: list[dict[str, object]] = []

        def fake_bulk_upsert(records):
            captured_records.extend(records)
            return {
                "inserted": 1,
                "updated": 0,
                "updated_external_ids": [],
                "updated_job_urls": [],
                "deleted_duplicate_rows": 0,
                "failed": 0,
            }

        try:
            with patch(
                "jobspy.jobs_table._bulk_upsert_jobs",
                side_effect=fake_bulk_upsert,
            ):
                summary = jobs_table.populate_jobs_table_from_file(json_path)
        finally:
            json_path.unlink(missing_ok=True)

        self.assertEqual(summary["prepared_records"], 1)
        self.assertEqual(len(captured_records), 1)
        self.assertEqual(captured_records[0]["source"], "varonis")
        self.assertEqual(captured_records[0]["external_id"], "ohHUyfwa")
        self.assertEqual(
            captured_records[0]["job_url"],
            "https://jobs.jobvite.com/careers/varonis/job/ohHUyfwa",
        )
        self.assertEqual(
            captured_records[0]["apply_url"],
            "https://app.jobvite.com/CompanyJobs/Careers.aspx?k=Apply&j=ohHUyfwa&c=qTjaVfw1&l=CFtKVfwx",
        )
        self.assertEqual(captured_records[0]["company_url"], "https://careers.varonis.com")
        self.assertEqual(captured_records[0]["company_id"], "careers.varonis.com")
        self.assertEqual(captured_records[0]["sector"], "R&D")
        self.assertEqual(captured_records[0]["work_type"], "engineering")

    def test_build_comeet_company_url_record_reads_string_company_name(self) -> None:
        record = jobs_table._build_comeet_company_url_record(
            {
                "company": "Acme",
                "job_url": "https://www.comeet.com/jobs/acme/AA.001/platform-engineer/12.345",
            }
        )

        self.assertIsNotNone(record)
        self.assertEqual(record["company_name"], "Acme")
        self.assertEqual(record["comeet_base_url"], "https://www.comeet.com/jobs/acme/AA.001")
        self.assertEqual(
            record["source_job_url"],
            "https://www.comeet.com/jobs/acme/AA.001/platform-engineer/12.345",
        )

    def test_populate_company_comeet_job_urls_from_airtable_rows_inserts_only_missing_links(
        self,
    ) -> None:
        payload = {
            "msg": "SUCCESS",
            "data": {
                "table": {
                    "rows": [
                        {
                            "id": "recUpwind",
                            "cellValuesByColumnId": {
                                "fldLT11B0cpV6p9Uz": "Upwind Security",
                                "fldHm56Wa148CQZ8h": "https://www.comeet.com/jobs/upwind/49.004",
                            },
                        },
                        {
                            "id": "recOther",
                            "cellValuesByColumnId": {
                                "fldLT11B0cpV6p9Uz": "Other Company",
                                "fldHm56Wa148CQZ8h": "https://example.com/careers",
                            },
                        },
                        {
                            "id": "recUtila",
                            "cellValuesByColumnId": {
                                "fldLT11B0cpV6p9Uz": "Utila",
                                "fldHm56Wa148CQZ8h": "https://www.comeet.com/jobs/utila/D9.00F",
                            },
                        },
                    ]
                }
            },
        }

        scripted_steps = [
            {"contains": "CREATE TABLE IF NOT EXISTS company_comeet_job_urls"},
            {"contains": "FROM company_comeet_job_urls", "fetchone": None},
            {"contains": "INSERT INTO company_comeet_job_urls"},
            {"contains": "FROM company_comeet_job_urls", "fetchone": ("https://www.comeet.com/jobs/utila/D9.00F",)},
        ]
        fake_cursor = FakeCursor(scripted_steps)
        fake_connection = FakeConnection(fake_cursor)

        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path = Path(tmp_dir) / "jobs.json"
            json_path.write_text(json.dumps(payload), encoding="utf-8")

            with patch(
                "jobspy.jobs_table._get_db_connection",
                return_value=fake_connection,
            ):
                summary = jobs_table.populate_company_comeet_job_urls_from_file(json_path)

        self.assertEqual(summary["rows_in_file"], 3)
        self.assertEqual(summary["matching_comeet_rows"], 2)
        self.assertEqual(summary["unique_base_urls"], 2)
        self.assertEqual(summary["inserted"], 1)
        self.assertEqual(summary["updated"], 0)
        self.assertEqual(summary["skipped_existing"], 1)
        self.assertEqual(summary["skipped_invalid"], 1)
        self.assertEqual(summary["skipped_duplicate_input"], 0)
        self.assertEqual(summary["failed"], 0)
        self.assertTrue(fake_connection.closed)

        insert_params = fake_cursor.executed_params[2]
        self.assertEqual(insert_params[0], "https://www.comeet.com/jobs/upwind/49.004")
        self.assertEqual(insert_params[1], "Upwind Security")
        self.assertEqual(insert_params[2], "upwind")
        self.assertEqual(insert_params[3], "49.004")
        self.assertEqual(insert_params[4], "https://www.comeet.com/jobs/upwind/49.004")


class JobsTableSourceNormalizationTests(unittest.TestCase):
    def test_seed_company_career_pages_refreshes_default_config_on_conflict(self) -> None:
        scripted_steps = [
            {"contains": "CREATE TABLE IF NOT EXISTS company_career_pages"},
            {"contains": "ALTER TABLE company_career_pages"},
            {
                "contains": "CREATE INDEX IF NOT EXISTS idx_company_career_pages_company_name"
            },
        ]
        scripted_steps.extend(
            {"contains": "ON CONFLICT (company_key) DO UPDATE SET"}
            for _ in jobs_table.DEFAULT_COMPANY_CAREER_PAGE_ROWS
        )
        fake_cursor = FakeCursor(scripted_steps)

        jobs_table._ensure_company_career_pages_table(
            fake_cursor,
            seed_defaults=True,
        )

        insert_sql = next(
            sql
            for sql in fake_cursor.executed_sql
            if "ON CONFLICT (company_key) DO UPDATE SET" in sql
        )
        update_sql = insert_sql.split("ON CONFLICT (company_key) DO UPDATE SET", 1)[1]
        self.assertIn("extra_params = EXCLUDED.extra_params", update_sql)
        self.assertIn("resolved_fetch_url = EXCLUDED.resolved_fetch_url", update_sql)
        self.assertNotIn("enabled = EXCLUDED.enabled", update_sql)
        self.assertNotIn("status = EXCLUDED.status", update_sql)

    def test_default_company_career_pages_include_nvidia(self) -> None:
        rows_by_key = {
            row["company_key"]: row
            for row in jobs_table.DEFAULT_COMPANY_CAREER_PAGE_ROWS
        }

        self.assertIn("nvidia", rows_by_key)
        nvidia_row = rows_by_key["nvidia"]
        self.assertEqual(nvidia_row["company_name"], "NVIDIA")
        self.assertEqual(nvidia_row["scraper_site"], "eightfold")
        self.assertEqual(
            nvidia_row["career_page_url"],
            (
                "https://jobs.nvidia.com/careers"
                "?start=0&location=Israel&pid=893395263607"
                "&sort_by=distance&filter_include_remote=0"
            ),
        )

    def test_default_company_career_pages_include_elbit_json_feed(self) -> None:
        rows_by_key = {
            row["company_key"]: row
            for row in jobs_table.DEFAULT_COMPANY_CAREER_PAGE_ROWS
        }

        self.assertIn("elbit", rows_by_key)
        elbit_row = rows_by_key["elbit"]
        self.assertEqual(elbit_row["company_name"], "Elbit Systems Israel")
        self.assertEqual(elbit_row["scraper_site"], "json_feed")
        self.assertEqual(
            elbit_row["career_page_url"],
            "https://elbitsystemscareer.com/cron/jobs.json",
        )
        self.assertEqual(
            elbit_row["extra_params"]["json_feed_config"]["field_paths"]["title"],
            "jobTitle",
        )

    def test_default_company_career_pages_include_nice_greenhouse_feed(self) -> None:
        rows_by_key = {
            row["company_key"]: row
            for row in jobs_table.DEFAULT_COMPANY_CAREER_PAGE_ROWS
        }

        self.assertIn("nice", rows_by_key)
        nice_row = rows_by_key["nice"]
        self.assertEqual(nice_row["company_name"], "NICE")
        self.assertEqual(nice_row["scraper_site"], "nice")
        self.assertEqual(nice_row["career_page_url"], jobs_table.NICE_COMPANY_URL)
        self.assertEqual(nice_row["location"], "Israel")
        self.assertEqual(
            nice_row["extra_params"]["json_feed_config"]["field_paths"]["job_url"],
            "absolute_url",
        )

    def test_default_company_career_pages_include_requested_company_urls(self) -> None:
        rows_by_key = {
            row["company_key"]: row
            for row in jobs_table.DEFAULT_COMPANY_CAREER_PAGE_ROWS
        }

        expected_urls = {
            "finastra": (
                "https://finastra.wd3.myworkdayjobs.com/FINC"
                "?locations=9ab6e37cf0b510c42416df84b57e102f"
            ),
            "matrix": "https://www.matrix.co.il/jobs/",
            "nova": "https://www.novami.com/results/?freetext=&location=israel",
            "gong": (
                "https://www.gong.io/careers"
                "?location=Tel+Aviv#careers-listing-section"
            ),
            "monday": "https://monday.com/careers/?location=telaviv",
            "towersemi": "https://careers.towersemi.com/our-loactions/israel/",
            "fiverr": "https://www.fiverr.com/jobs/teams?location=tlv",
            "similarweb": "https://www.similarweb.com/corp/careers/#opportunities",
            "hibob": "https://www.hibob.com/careers/",
            "gtech": "https://gtech.co.il/%D7%9E%D7%A9%D7%A8%D7%95%D7%AA/",
        }

        for company_key, career_page_url in expected_urls.items():
            self.assertIn(company_key, rows_by_key)
            self.assertEqual(
                rows_by_key[company_key]["career_page_url"],
                career_page_url,
            )

        self.assertEqual(
            rows_by_key["nova"]["resolved_fetch_url"],
            "https://www.comeet.com/jobs/nova/A5.007",
        )
        self.assertEqual(
            rows_by_key["fiverr"]["resolved_fetch_url"],
            "https://www.comeet.com/jobs/fiverr/60.002",
        )
        self.assertIn(
            "html_json_script_id",
            rows_by_key["monday"]["extra_params"]["json_feed_config"],
        )
        self.assertIn(
            "detail_fetch",
            rows_by_key["monday"]["extra_params"]["json_feed_config"],
        )
        self.assertEqual(
            rows_by_key["hibob"]["resolved_fetch_url"],
            jobs_table.HIBOB_JOBS_API_URL,
        )
        self.assertIn(
            "rows_path",
            rows_by_key["hibob"]["extra_params"]["json_feed_config"],
        )
        self.assertFalse(rows_by_key["towersemi"]["enabled"])

    def test_list_company_career_pages_creates_table_and_returns_enabled_rows(
        self,
    ) -> None:
        scripted_steps = [
            {"contains": "CREATE TABLE IF NOT EXISTS company_career_pages"},
            {"contains": "ALTER TABLE company_career_pages"},
            {
                "contains": "CREATE INDEX IF NOT EXISTS idx_company_career_pages_company_name"
            },
            {
                "contains": "FROM company_career_pages",
                "fetchall": [
                    (
                        7,
                        "acme",
                        "Acme",
                        ["Acme Inc"],
                        "workday",
                        "https://acme.wd1.myworkdayjobs.com/acme",
                        None,
                        "Israel",
                        "Israel",
                        0,
                        "markdown",
                        None,
                        60,
                        True,
                        {"workday_debug_trace": False},
                        None,
                        None,
                        "active",
                        "workday",
                        "https://acme.wd1.myworkdayjobs.com/acme",
                        {},
                        [],
                        None,
                        None,
                    )
                ],
            },
        ]
        fake_cursor = FakeCursor(scripted_steps)
        fake_connection = FakeConnection(fake_cursor)

        with patch(
            "jobspy.jobs_table._get_db_connection",
            return_value=fake_connection,
        ):
            rows = jobs_table.list_company_career_pages(seed_defaults=False)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], 7)
        self.assertEqual(rows[0]["company_key"], "acme")
        self.assertEqual(rows[0]["company_aliases"], ["Acme Inc"])
        self.assertEqual(rows[0]["scraper_site"], "workday")
        self.assertEqual(rows[0]["extra_params"], {"workday_debug_trace": False})
        self.assertTrue(fake_connection.closed)

    def test_upsert_company_career_page_from_validation_activates_valid_row(
        self,
    ) -> None:
        scripted_steps = [
            {"contains": "CREATE TABLE IF NOT EXISTS company_career_pages"},
            {"contains": "ALTER TABLE company_career_pages"},
            {
                "contains": "CREATE INDEX IF NOT EXISTS idx_company_career_pages_company_name"
            },
            {
                "contains": "INSERT INTO company_career_pages",
                "fetchone": (42, True, "active"),
            },
        ]
        fake_cursor = FakeCursor(scripted_steps)
        fake_connection = FakeConnection(fake_cursor)
        validation_result = {
            "valid": True,
            "company_key": "nice",
            "company_name": "NICE",
            "detected_platform": "greenhouse_public_board",
            "sample_jobs": [{"title": "AI AML Product Manager"}],
            "row": {
                "company_key": "nice",
                "company_name": "NICE",
                "company_aliases": ["NiCE"],
                "scraper_site": "json_feed",
                "career_page_url": "https://www.nice.com/careers/apply",
                "resolved_fetch_url": jobs_table.NICE_GREENHOUSE_JOBS_URL,
                "location": "Israel",
                "country_indeed": "Israel",
                "results_wanted": 0,
                "description_format": "markdown",
                "description_limit": None,
                "request_timeout": 60,
                "extra_params": {"json_feed_config": jobs_table.NICE_JSON_FEED_CONFIG},
            },
        }

        with patch(
            "jobspy.jobs_table._get_db_connection",
            return_value=fake_connection,
        ):
            summary = jobs_table.upsert_company_career_page_from_validation(
                validation_result,
                activate=True,
            )

        self.assertEqual(summary["id"], 42)
        self.assertTrue(summary["enabled"])
        self.assertEqual(summary["status"], "active")
        params = fake_cursor.executed_params[-1]
        self.assertEqual(params[0], "nice")
        self.assertEqual(params[12], True)
        self.assertEqual(params[14], "active")
        self.assertEqual(params[16], jobs_table.NICE_GREENHOUSE_JOBS_URL)
        self.assertTrue(fake_connection.closed)

    def test_build_job_record_accepts_json_feed_rows(self) -> None:
        record = jobs_table._build_job_record(
            {
                "site": "json_feed",
                "id": "19702",
                "title": "R&D Engineer",
                "company": "Elbit Systems Israel",
                "location": "Israel",
                "date_posted": "2026-06-15",
                "job_url": "https://elbitsystemscareer.com/job/?jid=19702",
                "apply_url": "https://elbitsystemscareer.com/job/?jid=19702",
                "company_url": "https://elbitsystemscareer.com/",
                "description": "Build systems",
                "job_function": "Engineering",
            }
        )

        self.assertIsNotNone(record)
        self.assertEqual(record["source"], "json_feed")
        self.assertEqual(record["external_id"], "19702")
        self.assertEqual(record["company_name"], "Elbit Systems Israel")
        self.assertEqual(record["sector"], "Engineering")

    def test_build_job_record_sets_direct_company_page_source_to_company_name(
        self,
    ) -> None:
        record = jobs_table._build_job_record(
            {
                "site": "workday",
                "id": "2503821",
                "title": "Principal Hardware Board Design Engineer",
                "company": "Marvell",
                "location": "Yokneam, Israel",
                "date_posted": "2026-04-15",
                "job_url": (
                    "https://marvell.wd1.myworkdayjobs.com/MarvellCareers"
                    "/job/Yokneam/Principal-Hardware-System-Design-Engineer_2503821"
                ),
                "apply_url": (
                    "https://marvell.wd1.myworkdayjobs.com/MarvellCareers"
                    "/job/Yokneam/Principal-Hardware-System-Design-Engineer_2503821"
                ),
                "company_url": (
                    "https://marvell.wd1.myworkdayjobs.com/MarvellCareers"
                ),
                "direct_company_career_page_key": "marvell",
                "direct_company_career_page_company": "Marvell",
            }
        )

        self.assertIsNotNone(record)
        self.assertEqual(record["source"], "Marvell")
        self.assertEqual(record["external_id"], "2503821")

    def test_populate_jobs_table_marks_configured_company_board_rows_duplicate(
        self,
    ) -> None:
        payload = [
            {
                "site": "linkedin",
                "title": "Backend Engineer",
                "company": "Acme",
                "job_url": "https://www.linkedin.com/jobs/view/1001",
                "description": "Board row",
            },
            {
                "site": "linkedin",
                "title": "Frontend Engineer",
                "company": "Acme",
                "job_url": "https://www.linkedin.com/jobs/view/1002",
                "description": "Direct-table row",
                "direct_company_career_page_key": "acme",
            },
            {
                "site": "apple",
                "title": "Software Engineer",
                "company": "Apple",
                "job_url": (
                    "https://jobs.apple.com/en-il/details/"
                    "200666549-0865/software-engineer"
                ),
            },
        ]
        captured_records: list[dict[str, object]] = []
        captured_include_flag = []

        def fake_bulk_upsert(records, *, include_duplicate_flag=False):
            captured_records.extend(records)
            captured_include_flag.append(include_duplicate_flag)
            return {
                "inserted": len(records),
                "updated": 0,
                "updated_external_ids": [],
                "updated_job_urls": [],
                "deleted_duplicate_rows": 0,
                "failed": 0,
            }

        json_path = Path.cwd() / ".codex-tmp" / "jobs-table-duplicate-mark.json"
        json_path.parent.mkdir(exist_ok=True)
        json_path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            with patch(
                "jobspy.jobs_table.get_company_career_page_company_match_keys",
                return_value={"acme"},
            ):
                with patch(
                    "jobspy.jobs_table._bulk_upsert_jobs",
                    side_effect=fake_bulk_upsert,
                ):
                    summary = jobs_table.populate_jobs_table_from_file(
                        json_path,
                        mark_configured_company_job_board_duplicates=True,
                    )
        finally:
            json_path.unlink(missing_ok=True)

        self.assertEqual(summary["marked_duplicate_jobs"], 1)
        self.assertEqual(captured_include_flag, [True])
        duplicate_by_url = {
            record["job_url"]: record["is_duplicate"]
            for record in captured_records
        }
        self.assertTrue(
            duplicate_by_url["https://www.linkedin.com/jobs/view/1001"]
        )
        self.assertFalse(
            duplicate_by_url["https://www.linkedin.com/jobs/view/1002"]
        )
        self.assertFalse(
            duplicate_by_url[
                "https://jobs.apple.com/en-il/details/200666549-0865/software-engineer"
            ]
        )

    def test_build_job_record_normalizes_apple_rows(self) -> None:
        record = jobs_table._build_job_record(
            {
                "site": "apple",
                "title": "Software Engineer",
                "company": "Apple",
                "location": "Herzliya, Tel Aviv District, Israel",
                "date_posted": "2026-06-03",
                "job_url": "https://jobs.apple.com/en-il/details/200666549-0865/software-engineer-test-automation?team=SFTWR",
                "apply_url": "https://jobs.apple.com/en-il/details/200666549-0865/software-engineer-test-automation?team=SFTWR",
                "description": "Build reliable services",
                "job_function": "Software and Services",
                "id": "200666549-0865",
            }
        )

        self.assertIsNotNone(record)
        self.assertEqual(record["source"], "apple")
        self.assertEqual(record["external_id"], "200666549-0865")
        self.assertEqual(
            record["job_url"],
            "https://jobs.apple.com/en-il/details/200666549-0865/software-engineer-test-automation",
        )
        self.assertEqual(record["company_id"], "jobs.apple.com")
        self.assertEqual(record["sector"], "Software and Services")

    def test_build_job_record_normalizes_microsoft_rows(self) -> None:
        record = jobs_table._build_job_record(
            {
                "site": "microsoft",
                "title": "Software Engineer",
                "company": "Microsoft",
                "location": "Herzliya, Tel Aviv District, Israel",
                "date_posted": "2026-06-03",
                "job_url": "https://apply.careers.microsoft.com/careers/job/1970393556851805",
                "apply_url": "https://apply.careers.microsoft.com/careers/job/1970393556851805",
                "company_url": "https://apply.careers.microsoft.com/careers",
                "description": "Build cloud services",
                "id": "200032828",
            }
        )

        self.assertIsNotNone(record)
        self.assertEqual(record["source"], "microsoft")
        self.assertEqual(record["external_id"], "200032828")
        self.assertEqual(record["company_id"], "apply.careers.microsoft.com")

    def test_build_job_record_normalizes_meta_rows(self) -> None:
        record = jobs_table._build_job_record(
            {
                "site": "meta",
                "title": "Software Engineer, ML",
                "company": "Meta",
                "location": "Tel Aviv, Israel",
                "date_posted": "2025-07-30",
                "job_url": "https://www.metacareers.com/jobs/24425919033670586/",
                "apply_url": "https://www.metacareers.com/jobs/24425919033670586/",
                "company_url": "https://www.metacareers.com",
                "description": "Build ML systems.",
                "job_function": "Software Engineering",
                "job_level": "Engineering",
                "id": "24425919033670586",
            }
        )

        self.assertIsNotNone(record)
        self.assertEqual(record["source"], "meta")
        self.assertEqual(record["external_id"], "24425919033670586")
        self.assertEqual(
            record["job_url"],
            "https://www.metacareers.com/jobs/24425919033670586/",
        )
        self.assertEqual(record["company_id"], "www.metacareers.com")
        self.assertEqual(record["sector"], "Software Engineering")


if __name__ == "__main__":
    unittest.main()
