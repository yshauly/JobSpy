from __future__ import annotations

from contextlib import redirect_stdout
import io
import unittest
from datetime import datetime
from unittest.mock import Mock, patch
import os

import jobspy.__main__ as cli
import pandas as pd
from jobspy.model import Country, GreenhouseScrapeMode, LinkedInScrapeMode


class SchedulerTests(unittest.TestCase):
    def test_scheduler_tick_runs_hourly_sites_and_three_hour_sites_on_0730(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(["--scheduler"])
        linkedin_schedule_args = cli._build_scheduler_linkedin_args(args)
        next_run_at = datetime(2026, 4, 5, 7, 30, tzinfo=cli.SCHEDULER_TIMEZONE)
        run_started_at = next_run_at

        linkedin_calls = []
        indeed_calls = []
        glassdoor_calls = []
        amdocs_calls = []
        apple_calls = []
        microsoft_calls = []
        marvell_calls = []
        redhat_calls = []
        varonis_calls = []
        comeet_calls = []
        greenhouse_calls = []
        publish_calls = []

        def fake_run_once(schedule_args):
            linkedin_calls.append(schedule_args)
            return None, {"inserted": 1}

        def fake_run_indeed_persist(schedule_args):
            indeed_calls.append(schedule_args)
            return None, {"inserted": 2}

        def fake_run_glassdoor_persist(schedule_args):
            glassdoor_calls.append(schedule_args)
            return None, {"inserted": 3}

        def fake_run_amdocs_persist(schedule_args):
            amdocs_calls.append(schedule_args)
            return None, {"inserted": 4}

        def fake_run_apple_persist(schedule_args):
            apple_calls.append(schedule_args)
            return None, {"inserted": 5}

        def fake_run_microsoft_persist(schedule_args):
            microsoft_calls.append(schedule_args)
            return None, {"inserted": 6}

        def fake_run_marvell_persist(schedule_args):
            marvell_calls.append(schedule_args)
            return None, {"inserted": 7}

        def fake_run_redhat_persist(schedule_args):
            redhat_calls.append(schedule_args)
            return None, {"inserted": 8}

        def fake_run_varonis_persist(schedule_args):
            varonis_calls.append(schedule_args)
            return None, {"inserted": 9}

        def fake_run_comeet_persist_all_israel(schedule_args):
            comeet_calls.append(schedule_args)
            return None, {"inserted": 10}

        def fake_run_greenhouse_persist(schedule_args):
            greenhouse_calls.append(schedule_args)
            return None, {"inserted": 11}

        def fake_publish_scrape_finished_event(publish_args, *, runs, quiet=False):
            publish_calls.append((publish_args, runs, quiet))

        with patch.object(
            cli,
            "_resolve_and_print_linkedin_auth_context",
            return_value=({}, "guest-only"),
        ) as mock_log_auth:
            with patch.object(cli, "run_once", side_effect=fake_run_once):
                with patch.object(
                    cli,
                    "run_indeed_persist",
                    side_effect=fake_run_indeed_persist,
                ):
                    with patch.object(
                        cli,
                        "run_glassdoor_persist",
                        side_effect=fake_run_glassdoor_persist,
                    ):
                        with patch.object(
                            cli,
                            "run_amdocs_persist",
                            side_effect=fake_run_amdocs_persist,
                        ):
                            with patch.object(
                                cli,
                                "run_apple_persist",
                                side_effect=fake_run_apple_persist,
                            ):
                                with patch.object(
                                    cli,
                                    "run_microsoft_persist",
                                    side_effect=fake_run_microsoft_persist,
                                ):
                                    with patch.object(
                                    cli,
                                    "run_marvell_persist",
                                    side_effect=fake_run_marvell_persist,
                                    ):
                                        with patch.object(
                                            cli,
                                            "run_redhat_persist",
                                            side_effect=fake_run_redhat_persist,
                                        ):
                                            with patch.object(
                                                cli,
                                                "run_varonis_persist",
                                                side_effect=fake_run_varonis_persist,
                                            ):
                                                with patch.object(
                                                    cli,
                                                    "run_comeet_persist_all_israel",
                                                    side_effect=fake_run_comeet_persist_all_israel,
                                                ):
                                                    with patch.object(
                                                        cli,
                                                        "run_greenhouse_persist",
                                                        side_effect=fake_run_greenhouse_persist,
                                                    ):
                                                        with patch.object(
                                                            cli,
                                                            "_publish_scrape_finished_event",
                                                            side_effect=fake_publish_scrape_finished_event,
                                                        ):
                                                            (
                                                                tick_succeeded,
                                                                updated_last_successful_run_date,
                                                            ) = cli._run_scheduler_tick(
                                                                args,
                                                                linkedin_schedule_args,
                                                                next_run_at=next_run_at,
                                                                run_started_at=run_started_at,
                                                                last_successful_run_date=None,
                                                            )

        self.assertTrue(tick_succeeded)
        self.assertEqual(updated_last_successful_run_date, run_started_at.date())
        mock_log_auth.assert_called_once_with(
            linkedin_schedule_args,
            context="scheduler-tick",
        )

        self.assertEqual(len(linkedin_calls), 1)
        self.assertEqual(len(indeed_calls), 1)
        self.assertEqual(len(glassdoor_calls), 1)
        self.assertEqual(len(amdocs_calls), 1)
        self.assertEqual(len(apple_calls), 1)
        self.assertEqual(len(microsoft_calls), 1)
        self.assertEqual(len(marvell_calls), 1)
        self.assertEqual(len(redhat_calls), 1)
        self.assertEqual(len(varonis_calls), 1)
        self.assertEqual(len(comeet_calls), 1)
        self.assertEqual(len(greenhouse_calls), 1)

        linkedin_args = linkedin_calls[0]
        self.assertEqual(
            linkedin_args.execution_mode,
            LinkedInScrapeMode.UNTIL_LAST_PAGE.value,
        )
        self.assertEqual(
            linkedin_args.num_of_min,
            cli.FIRST_SCHEDULER_INTERVAL_MINUTES,
        )
        self.assertEqual(
            linkedin_args.linkedin_geo_id,
            cli.DEFAULT_LINKEDIN_ISRAEL_GEO_ID,
        )
        self.assertTrue(linkedin_args.save_db)
        self.assertTrue(linkedin_args.fetch_description)

        indeed_args = indeed_calls[0]
        self.assertIsNone(indeed_args.search_term)
        self.assertEqual(indeed_args.location, "Israel")
        self.assertEqual(indeed_args.country_indeed, "Israel")
        self.assertEqual(indeed_args.hours_old, 24)
        self.assertTrue(indeed_args.save_db)

        glassdoor_args = glassdoor_calls[0]
        self.assertIsNone(glassdoor_args.search_term)
        self.assertEqual(glassdoor_args.location, "Israel")
        self.assertEqual(glassdoor_args.country_indeed, "Israel")
        self.assertEqual(
            glassdoor_args.hours_old,
            cli.DEFAULT_GLASSDOOR_FROM_AGE_DAYS * 24,
        )
        self.assertTrue(glassdoor_args.save_db)

        amdocs_args = amdocs_calls[0]
        self.assertIsNone(amdocs_args.search_term)
        self.assertTrue(amdocs_args.save_db)
        self.assertEqual(
            amdocs_args.amdocs_base_url,
            cli.DEFAULT_AMDOCS_BASE_URL,
        )

        apple_args = apple_calls[0]
        self.assertIsNone(apple_args.search_term)
        self.assertTrue(apple_args.save_db)
        self.assertEqual(
            apple_args.apple_search_url,
            cli.DEFAULT_APPLE_SEARCH_URL,
        )

        microsoft_args = microsoft_calls[0]
        self.assertIsNone(microsoft_args.search_term)
        self.assertTrue(microsoft_args.save_db)
        self.assertEqual(
            microsoft_args.microsoft_base_url,
            cli.DEFAULT_MICROSOFT_BASE_URL,
        )

        marvell_args = marvell_calls[0]
        self.assertIsNone(marvell_args.search_term)
        self.assertTrue(marvell_args.save_db)
        self.assertEqual(
            marvell_args.marvell_base_url,
            cli.DEFAULT_MARVELL_BASE_URL,
        )

        redhat_args = redhat_calls[0]
        self.assertIsNone(redhat_args.search_term)
        self.assertTrue(redhat_args.save_db)
        self.assertEqual(
            redhat_args.redhat_base_url,
            cli.DEFAULT_REDHAT_BASE_URL,
        )

        varonis_args = varonis_calls[0]
        self.assertIsNone(varonis_args.search_term)
        self.assertTrue(varonis_args.save_db)
        self.assertEqual(
            varonis_args.varonis_base_url,
            cli.DEFAULT_VARONIS_BASE_URL,
        )

        comeet_args = comeet_calls[0]
        self.assertIsNone(comeet_args.search_term)
        self.assertTrue(comeet_args.save_db)

        greenhouse_args = greenhouse_calls[0]
        self.assertIsNone(greenhouse_args.search_term)
        self.assertEqual(greenhouse_args.location, "Israel")
        self.assertEqual(greenhouse_args.country_indeed, "Israel")
        self.assertEqual(
            greenhouse_args.greenhouse_cookie_file,
            str(cli.DEFAULT_GREENHOUSE_COOKIE_FILE),
        )
        self.assertTrue(greenhouse_args.save_db)

        self.assertEqual(len(publish_calls), 1)
        publish_args, runs, quiet = publish_calls[0]
        self.assertIs(publish_args, args)
        self.assertTrue(quiet)
        self.assertEqual(
            [run["site"] for run in runs],
            [
                "linkedin",
                "indeed",
                "glassdoor",
                "amdocs",
                "apple",
                "microsoft",
                "marvell",
                "redhat",
                "varonis",
                "comeet",
                "greenhouse",
            ],
        )

    def test_scheduler_tick_prints_site_level_logs_on_success_path(self) -> None:
        args = cli.build_parser().parse_args(["--scheduler"])
        linkedin_schedule_args = cli._build_scheduler_linkedin_args(args)
        next_run_at = datetime(2026, 4, 5, 8, 30, tzinfo=cli.SCHEDULER_TIMEZONE)
        run_started_at = next_run_at

        def make_noisy_runner(site_name: str):
            def fake_runner(schedule_args):
                print(f"{site_name} noisy log")
                return pd.DataFrame([{"site": site_name, "job_url": f"https://example.com/{site_name}"}]), {
                    "rows_in_file": 1,
                    "inserted": 0,
                    "updated": 1,
                    "skipped_invalid": 0,
                    "skipped_duplicate_input": 0,
                    "failed": 0,
                }

            return fake_runner

        def fake_auth_context(schedule_args, *, context):
            print("auth noisy log")
            return {}, "guest-only"

        def fake_publish_event(payload):
            print("publish noisy log")

        with patch.object(
            cli,
            "_resolve_and_print_linkedin_auth_context",
            side_effect=fake_auth_context,
        ):
            with patch.object(cli, "run_once", side_effect=make_noisy_runner("linkedin")):
                with patch.object(
                    cli,
                    "run_indeed_persist",
                    side_effect=make_noisy_runner("indeed"),
                ):
                    with patch.object(
                        cli,
                        "run_glassdoor_persist",
                        side_effect=make_noisy_runner("glassdoor"),
                    ):
                        with patch.object(
                            cli,
                            "run_amdocs_persist",
                            side_effect=make_noisy_runner("amdocs"),
                        ):
                            with patch.object(
                                cli,
                                "run_apple_persist",
                                side_effect=make_noisy_runner("apple"),
                            ):
                                with patch.object(
                                    cli,
                                    "run_microsoft_persist",
                                    side_effect=make_noisy_runner("microsoft"),
                                ):
                                    with patch.object(
                                        cli,
                                        "run_marvell_persist",
                                        side_effect=make_noisy_runner("marvell"),
                                    ):
                                        with patch.object(
                                            cli,
                                            "run_redhat_persist",
                                            side_effect=make_noisy_runner("redhat"),
                                        ):
                                            with patch.object(
                                                cli,
                                                "run_varonis_persist",
                                                side_effect=make_noisy_runner("varonis"),
                                            ):
                                                with patch(
                                                    "jobspy.event_publisher.publish_scrape_finished_event",
                                                    side_effect=fake_publish_event,
                                                ):
                                                    stdout = io.StringIO()
                                                    with redirect_stdout(stdout):
                                                        tick_succeeded, _ = cli._run_scheduler_tick(
                                                            args,
                                                            linkedin_schedule_args,
                                                            next_run_at=next_run_at,
                                                            run_started_at=run_started_at,
                                                            last_successful_run_date=None,
                                                        )

        output = stdout.getvalue()
        self.assertTrue(tick_succeeded)
        self.assertIn("Scheduler tick started", output)
        self.assertIn("three_hour_sites=no", output)
        self.assertIn("Running scheduled LinkedIn scrape", output)
        self.assertIn("LinkedIn scheduler summary:", output)
        self.assertIn("Running scheduled Indeed scrape", output)
        self.assertIn("Indeed scheduler summary:", output)
        self.assertIn("Running scheduled Glassdoor scrape", output)
        self.assertIn("Glassdoor scheduler summary:", output)
        self.assertIn("Running scheduled Amdocs scrape", output)
        self.assertIn("Amdocs scheduler summary:", output)
        self.assertIn("Running scheduled Apple scrape", output)
        self.assertIn("Apple scheduler summary:", output)
        self.assertIn("Running scheduled Microsoft scrape", output)
        self.assertIn("Microsoft scheduler summary:", output)
        self.assertIn("Running scheduled Marvell scrape", output)
        self.assertIn("Marvell scheduler summary:", output)
        self.assertIn("Running scheduled Red Hat scrape", output)
        self.assertIn("Red Hat scheduler summary:", output)
        self.assertIn("Running scheduled Varonis scrape", output)
        self.assertIn("Varonis scheduler summary:", output)
        self.assertIn(
            "Skipping scheduled Comeet and Greenhouse runs until the next 3-hour tick",
            output,
        )
        self.assertIn("Scheduler tick completed successfully", output)
        self.assertNotIn("auth noisy log", output)
        self.assertNotIn("linkedin noisy log", output)
        self.assertNotIn("indeed noisy log", output)
        self.assertNotIn("glassdoor noisy log", output)
        self.assertNotIn("amdocs noisy log", output)
        self.assertNotIn("apple noisy log", output)
        self.assertNotIn("microsoft noisy log", output)
        self.assertNotIn("marvell noisy log", output)
        self.assertNotIn("redhat noisy log", output)
        self.assertNotIn("publish noisy log", output)

    def test_scheduler_num_of_min_uses_last_day_only_for_scheduled_0730(self) -> None:
        self.assertEqual(
            cli._get_scheduler_num_of_min(
                datetime(2026, 4, 5, 7, 30, tzinfo=cli.SCHEDULER_TIMEZONE)
            ),
            cli.FIRST_SCHEDULER_INTERVAL_MINUTES,
        )
        self.assertEqual(
            cli._get_scheduler_num_of_min(
                datetime(2026, 4, 5, 12, 30, tzinfo=cli.SCHEDULER_TIMEZONE)
            ),
            cli.MIN_LINKEDIN_SCHEDULER_INTERVAL_MINUTES,
        )

    def test_three_hour_scheduler_sites_are_anchored_to_0730(self) -> None:
        self.assertTrue(
            cli._should_run_three_hour_scheduler_sites(
                datetime(2026, 4, 5, 7, 30, tzinfo=cli.SCHEDULER_TIMEZONE)
            )
        )
        self.assertTrue(
            cli._should_run_three_hour_scheduler_sites(
                datetime(2026, 4, 5, 10, 30, tzinfo=cli.SCHEDULER_TIMEZONE)
            )
        )
        self.assertFalse(
            cli._should_run_three_hour_scheduler_sites(
                datetime(2026, 4, 5, 8, 30, tzinfo=cli.SCHEDULER_TIMEZONE)
            )
        )
        self.assertFalse(
            cli._should_run_three_hour_scheduler_sites(
                datetime(2026, 4, 5, 12, 30, tzinfo=cli.SCHEDULER_TIMEZONE)
            )
        )

    def test_company_career_pages_scheduler_tick_runs_priority_flow(self) -> None:
        args = cli.build_parser().parse_args(["--company-career-pages"])
        schedule_args = cli._build_company_career_pages_scheduler_args(args)
        next_run_at = datetime(2026, 4, 5, 7, 30, tzinfo=cli.SCHEDULER_TIMEZONE)
        run_started_at = next_run_at
        fake_jobs = pd.DataFrame(
            [
                {"site": "linkedin", "job_url": "https://www.linkedin.com/jobs/view/1"},
                {"site": "workday", "job_url": "https://acme.example/jobs/1"},
            ]
        )
        publish_calls = []

        def fake_publish_scrape_finished_event(publish_args, *, runs, quiet=False):
            publish_calls.append((publish_args, runs, quiet))

        with patch.object(
            cli,
            "run_company_career_pages_priority",
            return_value=(fake_jobs, {"inserted": 2, "updated": 0}),
        ) as mock_run:
            with patch.object(
                cli,
                "_publish_scrape_finished_event",
                side_effect=fake_publish_scrape_finished_event,
            ):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    tick_succeeded, updated_last_successful_run_date = (
                        cli._run_company_career_pages_scheduler_tick(
                            args,
                            schedule_args,
                            next_run_at=next_run_at,
                            run_started_at=run_started_at,
                            last_successful_run_date=None,
                        )
                    )

        output = stdout.getvalue()
        self.assertTrue(tick_succeeded)
        self.assertEqual(updated_last_successful_run_date, run_started_at.date())
        self.assertEqual(
            schedule_args.execution_mode,
            LinkedInScrapeMode.UNTIL_LAST_PAGE.value,
        )
        self.assertEqual(
            schedule_args.num_of_min,
            cli.FIRST_SCHEDULER_INTERVAL_MINUTES,
        )
        self.assertTrue(schedule_args.scheduler)
        self.assertTrue(schedule_args.save_db)
        self.assertTrue(schedule_args.fetch_description)
        mock_run.assert_called_once_with(schedule_args)
        self.assertEqual(len(publish_calls), 1)
        publish_args, runs, quiet = publish_calls[0]
        self.assertIs(publish_args, args)
        self.assertTrue(quiet)
        self.assertEqual(runs[0]["site"], "company_career_pages")
        self.assertEqual(runs[0]["mode"], "priority-config")
        self.assertEqual(runs[0]["jobs_retrieved"], 2)
        self.assertIn("Company career-page scheduler tick started", output)
        self.assertIn(
            "Running scheduled configured company career-page priority scrape",
            output,
        )
        self.assertIn("Company Career Pages scheduler summary:", output)
        self.assertIn(
            "Company career-page scheduler tick completed successfully",
            output,
        )

    def test_company_career_pages_scheduler_seeds_defaults_before_first_sleep(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(["--company-career-pages"])
        calls = []

        def fake_ensure_company_career_pages_table(*, seed_defaults=False):
            calls.append(("seed", seed_defaults))

        def fake_sleep(seconds):
            calls.append(("sleep", seconds))
            raise KeyboardInterrupt

        with patch(
            "jobspy.jobs_table.ensure_company_career_pages_table",
            side_effect=fake_ensure_company_career_pages_table,
        ):
            with patch.object(cli.time, "sleep", side_effect=fake_sleep):
                with patch("builtins.print"):
                    with self.assertRaises(KeyboardInterrupt):
                        cli.run_company_career_pages_scheduler(args)

        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(calls[0], ("seed", True))
        self.assertEqual(calls[1][0], "sleep")


class MainFlowTests(unittest.TestCase):
    def test_run_once_scrapes_linkedin_and_redhat_together(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            args = cli.build_parser().parse_args(["--no-save-db"])
        scrape_calls = []
        saved_outputs = []
        fake_jobs = pd.DataFrame(
            [
                {
                    "site": "linkedin",
                    "title": "Backend Engineer",
                    "company": "Acme",
                    "location": "Tel Aviv, Israel",
                    "date_posted": "2026-04-28",
                    "job_url": "https://www.linkedin.com/jobs/view/1",
                    "description": "LinkedIn job",
                },
                {
                    "site": "redhat",
                    "title": "Senior Software Engineer",
                    "company": "Red Hat",
                    "location": "Raanana, Israel",
                    "date_posted": "2026-04-28",
                    "job_url": "https://redhat.wd5.myworkdayjobs.com/Jobs/job/Raanana/job-1",
                    "description": "Red Hat job",
                },
            ]
        )

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        def fake_save_jobs_to_json(output_path, jobs):
            saved_outputs.append((output_path, jobs))

        with patch.object(cli, "load_linkedin_builtin_cookies", return_value={}):
            with patch.object(cli, "load_linkedin_chromium_cookies", return_value=({}, None)):
                with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
                    with patch.object(cli, "save_jobs_to_json", side_effect=fake_save_jobs_to_json):
                        with patch("builtins.print"):
                            jobs, db_summary = cli.run_once(args)

        self.assertTrue(jobs.equals(fake_jobs))
        self.assertIsNone(db_summary)
        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], ["linkedin", "redhat"])
        self.assertEqual(scrape_calls[0]["redhat_base_url"], cli.DEFAULT_REDHAT_BASE_URL)
        self.assertEqual(
            scrape_calls[0]["linkedin_geo_id"],
            cli.DEFAULT_LINKEDIN_ISRAEL_GEO_ID,
        )
        self.assertEqual(scrape_calls[0]["results_wanted"], args.results)
        self.assertEqual(scrape_calls[0]["verbose"], 0)
        self.assertEqual(scrape_calls[0]["linkedin_auth_cookies"], {})
        self.assertEqual(len(saved_outputs), 1)
        self.assertTrue(saved_outputs[0][1].equals(fake_jobs))

    def test_run_once_enables_progress_logging_for_until_last_page(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            args = cli.build_parser().parse_args(
                [
                    "--execution-mode",
                    LinkedInScrapeMode.UNTIL_LAST_PAGE.value,
                    "--num-of-min",
                    "60",
                    "--no-save-db",
                ]
            )
        scrape_calls = []
        saved_outputs = []
        fake_jobs = pd.DataFrame(
            [
                {
                    "site": "linkedin",
                    "title": "Backend Engineer",
                    "company": "Acme",
                    "location": "Tel Aviv, Israel",
                    "date_posted": "2026-04-28",
                    "job_url": "https://www.linkedin.com/jobs/view/1",
                    "description": "LinkedIn job",
                }
            ]
        )

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        def fake_save_jobs_to_json(output_path, jobs):
            saved_outputs.append((output_path, jobs))

        with patch.object(cli, "load_linkedin_builtin_cookies", return_value={}):
            with patch.object(cli, "load_linkedin_chromium_cookies", return_value=({}, None)):
                with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
                    with patch.object(cli, "save_jobs_to_json", side_effect=fake_save_jobs_to_json):
                        with patch("builtins.print"):
                            jobs, db_summary = cli.run_once(args)

        self.assertTrue(jobs.equals(fake_jobs))
        self.assertIsNone(db_summary)
        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], ["linkedin", "redhat"])
        self.assertEqual(
            scrape_calls[0]["linkedin_geo_id"],
            cli.DEFAULT_LINKEDIN_ISRAEL_GEO_ID,
        )
        self.assertEqual(scrape_calls[0]["num_of_min"], 60)
        self.assertEqual(scrape_calls[0]["verbose"], 2)
        self.assertEqual(scrape_calls[0]["linkedin_auth_cookies"], {})
        self.assertEqual(len(saved_outputs), 1)
        self.assertTrue(saved_outputs[0][1].equals(fake_jobs))

    def test_run_once_forwards_linkedin_page_delay_configuration(self) -> None:
        args = cli.build_parser().parse_args(
            [
                "--linkedin-page-delay-min",
                "0.5",
                "--linkedin-page-delay-max",
                "1.5",
                "--no-save-db",
            ]
        )
        scrape_calls = []
        fake_jobs = pd.DataFrame(
            [
                {
                    "site": "linkedin",
                    "title": "Backend Engineer",
                    "company": "Acme",
                    "location": "Tel Aviv, Israel",
                    "date_posted": "2026-04-28",
                    "job_url": "https://www.linkedin.com/jobs/view/1",
                    "description": "LinkedIn job",
                }
            ]
        )

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            with patch.object(cli, "save_jobs_to_json"):
                with patch("builtins.print"):
                    jobs, db_summary = cli.run_once(args)

        self.assertTrue(jobs.equals(fake_jobs))
        self.assertIsNone(db_summary)
        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["linkedin_page_delay_min"], 0.5)
        self.assertEqual(scrape_calls[0]["linkedin_page_delay_max"], 1.5)

    def test_run_once_prints_only_db_summary_while_saving_and_populating(self) -> None:
        args = cli.build_parser().parse_args([])
        scrape_calls = []
        saved_outputs = []
        populate_calls = []
        fake_jobs = pd.DataFrame(
            [
                {
                    "site": "linkedin",
                    "title": "Backend Engineer",
                    "company": "Acme",
                    "location": "Tel Aviv, Israel",
                    "date_posted": "2026-04-28",
                    "job_url": "https://www.linkedin.com/jobs/view/1",
                    "description": "LinkedIn job",
                },
                {
                    "site": "redhat",
                    "title": "Senior Software Engineer",
                    "company": "Red Hat",
                    "location": "Raanana, Israel",
                    "date_posted": "2026-04-28",
                    "job_url": "https://redhat.wd5.myworkdayjobs.com/Jobs/job/Raanana/job-1",
                    "description": "Red Hat job",
                },
            ]
        )

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        def fake_save_jobs_to_json(output_path, jobs):
            saved_outputs.append((output_path, jobs))

        def fake_populate_jobs_table_from_file(output_path):
            populate_calls.append(output_path)
            return {"inserted": 2, "updated": 0}

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            with patch.object(cli, "save_jobs_to_json", side_effect=fake_save_jobs_to_json):
                with patch(
                    "jobspy.jobs_table.populate_jobs_table_from_file",
                    side_effect=fake_populate_jobs_table_from_file,
                ):
                    with patch("builtins.print") as mock_print:
                        jobs, db_summary = cli.run_once(args)

        self.assertTrue(jobs.equals(fake_jobs))
        self.assertEqual(db_summary, {"inserted": 2, "updated": 0})
        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(len(saved_outputs), 1)
        self.assertEqual(len(populate_calls), 1)
        mock_print.assert_called_once_with("DB upsert summary: inserted=2 updated=0")

    def test_main_default_flow_publishes_linkedin_and_redhat_runs(self) -> None:
        args = cli.build_parser().parse_args([])
        fake_jobs = pd.DataFrame(
            [
                {"site": "linkedin", "job_url": "https://www.linkedin.com/jobs/view/1"},
                {"site": "linkedin", "job_url": "https://www.linkedin.com/jobs/view/2"},
                {"site": "redhat", "job_url": "https://redhat.wd5.myworkdayjobs.com/Jobs/job/Raanana/job-1"},
            ]
        )
        publish_calls = []

        class FakeParser:
            def parse_args(self):
                return args

        def fake_publish(publish_args, *, runs):
            publish_calls.append((publish_args, runs))

        with patch.object(cli, "build_parser", return_value=FakeParser()):
            with patch.object(cli, "run_once", return_value=(fake_jobs, {"inserted": 3})):
                with patch.object(
                    cli,
                    "_publish_scrape_finished_event",
                    side_effect=fake_publish,
                ):
                    cli.main()

        self.assertEqual(len(publish_calls), 1)
        publish_args, runs = publish_calls[0]
        self.assertIs(publish_args, args)
        self.assertEqual([run["site"] for run in runs], ["linkedin", "redhat"])
        self.assertEqual(runs[0]["jobs_retrieved"], 2)
        self.assertEqual(runs[1]["jobs_retrieved"], 1)

    def test_scrape_company_career_page_row_maps_single_config_row(self) -> None:
        args = cli.build_parser().parse_args(["--company-career-pages", "--no-save-db"])
        company_record = {
            "id": 12,
            "company_key": "acme",
            "company_name": "Acme",
            "scraper_site": "workday",
            "career_page_url": "https://acme.wd1.myworkdayjobs.com/acme",
            "search_term": None,
            "location": "Israel",
            "country_indeed": "Israel",
            "results_wanted": 0,
            "description_format": "markdown",
            "description_limit": None,
            "request_timeout": 60,
            "extra_params": {"workday_debug_trace": False},
        }
        fake_jobs = pd.DataFrame(
            [
                {
                    "site": "workday",
                    "title": "Backend Engineer",
                    "company": "Acme",
                    "job_url": "https://acme.example/jobs/1",
                }
            ]
        )
        scrape_calls = []

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            with patch("builtins.print"):
                jobs, summary = cli._scrape_company_career_page_row(
                    company_record,
                    args,
                )

        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], "workday")
        self.assertEqual(
            scrape_calls[0]["workday_company_url"],
            "https://acme.wd1.myworkdayjobs.com/acme",
        )
        self.assertEqual(scrape_calls[0]["results_wanted"], 0)
        self.assertFalse(scrape_calls[0]["workday_debug_trace"])
        self.assertEqual(summary["jobs"], 1)
        self.assertEqual(jobs["direct_company_career_page_key"].tolist(), ["acme"])
        self.assertEqual(jobs["direct_company_career_page_id"].tolist(), [12])

    def test_scrape_company_career_page_row_maps_amdocs_alias_to_eightfold(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(["--company-career-pages", "--no-save-db"])
        company_record = {
            "id": 13,
            "company_key": "amdocs",
            "company_name": "Amdocs",
            "scraper_site": "amdocs",
            "career_page_url": "https://jobs.amdocs.com/careers",
            "search_term": None,
            "location": None,
            "country_indeed": "Israel",
            "results_wanted": 0,
            "description_format": "markdown",
            "description_limit": None,
            "request_timeout": 60,
            "extra_params": {"eightfold_debug_trace": False},
        }
        fake_jobs = pd.DataFrame(
            [
                {
                    "site": "eightfold",
                    "title": "Backend Engineer",
                    "company": "Amdocs",
                    "job_url": "https://amdocs.example/jobs/1",
                }
            ]
        )
        scrape_calls = []

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            with patch("builtins.print"):
                jobs, summary = cli._scrape_company_career_page_row(
                    company_record,
                    args,
                )

        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], "eightfold")
        self.assertEqual(
            scrape_calls[0]["eightfold_company_url"],
            "https://jobs.amdocs.com/careers",
        )
        self.assertFalse(scrape_calls[0]["eightfold_debug_trace"])
        self.assertEqual(summary["jobs"], 1)
        self.assertEqual(jobs["direct_company_career_page_key"].tolist(), ["amdocs"])

    def test_scrape_company_career_page_row_maps_nvidia_alias_to_eightfold(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(["--company-career-pages", "--no-save-db"])
        company_record = {
            "id": 14,
            "company_key": "nvidia",
            "company_name": "NVIDIA",
            "scraper_site": "nvidia",
            "career_page_url": (
                "https://jobs.nvidia.com/careers"
                "?start=0&location=Israel&pid=893395263607"
                "&sort_by=distance&filter_include_remote=0"
            ),
            "search_term": None,
            "location": None,
            "country_indeed": "Israel",
            "results_wanted": 0,
            "description_format": "markdown",
            "description_limit": None,
            "request_timeout": 60,
            "extra_params": {},
        }
        fake_jobs = pd.DataFrame(
            [
                {
                    "site": "eightfold",
                    "title": "Senior Software Engineer",
                    "company": "NVIDIA",
                    "job_url": "https://jobs.nvidia.com/careers/job/893395263607",
                }
            ]
        )
        scrape_calls = []

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            with patch("builtins.print"):
                jobs, summary = cli._scrape_company_career_page_row(
                    company_record,
                    args,
                )

        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], "eightfold")
        self.assertEqual(
            scrape_calls[0]["eightfold_company_url"],
            (
                "https://jobs.nvidia.com/careers"
                "?start=0&location=Israel&pid=893395263607"
                "&sort_by=distance&filter_include_remote=0"
            ),
        )
        self.assertEqual(summary["jobs"], 1)
        self.assertEqual(jobs["direct_company_career_page_key"].tolist(), ["nvidia"])

    def test_scrape_company_career_page_row_maps_json_feed_config(self) -> None:
        args = cli.build_parser().parse_args(["--company-career-pages", "--no-save-db"])
        company_record = {
            "id": 15,
            "company_key": "elbit",
            "company_name": "Elbit Systems Israel",
            "scraper_site": "json_feed",
            "career_page_url": "https://elbitsystemscareer.com/cron/jobs.json",
            "search_term": None,
            "location": "Israel",
            "country_indeed": "Israel",
            "results_wanted": 0,
            "description_format": "markdown",
            "description_limit": None,
            "request_timeout": 60,
            "extra_params": {
                "json_feed_config": {
                    "field_paths": {"id": "jobId", "title": "jobTitle"},
                    "templates": {
                        "job_url": "https://elbitsystemscareer.com/job/?jid={jobId}",
                    },
                }
            },
        }
        fake_jobs = pd.DataFrame(
            [
                {
                    "site": "json_feed",
                    "title": "Systems Engineer",
                    "company": "Elbit Systems Israel",
                    "job_url": "https://elbitsystemscareer.com/job/?jid=19702",
                }
            ]
        )
        scrape_calls = []

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            with patch("builtins.print"):
                jobs, summary = cli._scrape_company_career_page_row(
                    company_record,
                    args,
                )

        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], "json_feed")
        self.assertEqual(
            scrape_calls[0]["json_feed_url"],
            "https://elbitsystemscareer.com/cron/jobs.json",
        )
        self.assertEqual(
            scrape_calls[0]["json_feed_config"]["field_paths"]["title"],
            "jobTitle",
        )
        self.assertEqual(summary["jobs"], 1)
        self.assertEqual(jobs["direct_company_career_page_key"].tolist(), ["elbit"])

    def test_scrape_company_career_page_row_maps_nice_alias_to_json_feed(self) -> None:
        args = cli.build_parser().parse_args(["--company-career-pages", "--no-save-db"])
        company_record = {
            "id": 16,
            "company_key": "nice",
            "company_name": "NICE",
            "scraper_site": "nice",
            "career_page_url": "https://www.nice.com/careers/apply",
            "search_term": None,
            "location": "Israel",
            "country_indeed": "Israel",
            "results_wanted": 0,
            "description_format": "markdown",
            "description_limit": None,
            "request_timeout": 60,
            "extra_params": {
                "json_feed_config": {
                    "headers": {"Accept": "application/json"},
                }
            },
        }
        fake_jobs = pd.DataFrame(
            [
                {
                    "site": "json_feed",
                    "title": "Software Engineer",
                    "company": "NICE",
                    "job_url": "https://boards.eu.greenhouse.io/nice/jobs/123",
                }
            ]
        )
        scrape_calls = []

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            with patch("builtins.print"):
                jobs, summary = cli._scrape_company_career_page_row(
                    company_record,
                    args,
                )

        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], "json_feed")
        self.assertEqual(
            scrape_calls[0]["json_feed_url"],
            cli.NICE_GREENHOUSE_JOBS_URL,
        )
        self.assertEqual(
            scrape_calls[0]["json_feed_config"]["field_paths"]["title"],
            "title",
        )
        self.assertEqual(
            scrape_calls[0]["json_feed_config"]["headers"],
            {"Accept": "application/json"},
        )
        self.assertEqual(summary["jobs"], 1)
        self.assertEqual(jobs["direct_company_career_page_key"].tolist(), ["nice"])

    def test_run_company_career_pages_priority_combines_and_marks_on_import(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(["--company-career-pages"])
        company_records = [
            {
                "id": 12,
                "company_key": "acme",
                "company_name": "Acme",
                "scraper_site": "workday",
                "career_page_url": "https://acme.wd1.myworkdayjobs.com/acme",
                "search_term": None,
                "location": "Israel",
                "country_indeed": "Israel",
                "results_wanted": 0,
                "description_format": "markdown",
                "description_limit": None,
                "request_timeout": 60,
                "extra_params": {},
            }
        ]
        board_jobs_by_site = {
            site: pd.DataFrame(
                [
                    {
                        "site": site,
                        "title": f"{site.title()} Engineer",
                        "company": "Acme",
                        "location": "Israel",
                        "job_url": f"https://example.com/{site}/jobs/1",
                    }
                ]
            )
            for site in cli.COMPANY_CAREER_PAGE_JOB_BOARD_SITES
        }
        direct_jobs = pd.DataFrame(
            [
                {
                    "site": "workday",
                    "title": "Backend Engineer",
                    "company": "Acme",
                    "location": "Israel",
                    "job_url": "https://acme.example/jobs/1",
                }
            ]
        )
        scrape_calls = []
        saved_outputs = []
        populate_calls = []

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            site_name = kwargs["site_name"]
            if site_name == "workday":
                return direct_jobs
            return board_jobs_by_site[site_name]

        def fake_save_jobs_to_json(output_path, jobs):
            saved_outputs.append((output_path, jobs))

        def fake_populate_jobs_table_from_file(output_path, **kwargs):
            populate_calls.append((output_path, kwargs))
            return {"inserted": 5, "updated": 0, "marked_duplicate_jobs": 4}

        with patch(
            "jobspy.jobs_table.list_company_career_pages",
            return_value=company_records,
        ) as mock_list_company_career_pages:
            with patch(
                "jobspy.jobs_table.populate_jobs_table_from_file",
                side_effect=fake_populate_jobs_table_from_file,
            ):
                with patch.object(
                    cli,
                    "_build_linkedin_auth_context",
                    return_value=({}, "guest-only"),
                ) as mock_linkedin_auth:
                    with patch(
                        "jobspy.jobs_table.list_company_comeet_job_urls",
                        return_value=[
                            {
                                "company_name": "Acme",
                                "comeet_base_url": "https://www.comeet.com/jobs/acme/AA.001",
                            }
                        ],
                    ):
                        with patch.object(
                            cli,
                            "_build_greenhouse_auth_cookies",
                            return_value={
                                "_session_id": "session",
                                "MYGREENHOUSE-XSRF-TOKEN": "token",
                            },
                        ):
                            with patch.object(
                                cli,
                                "scrape_jobs",
                                side_effect=fake_scrape_jobs,
                            ):
                                with patch.object(
                                    cli,
                                    "save_jobs_to_json",
                                    side_effect=fake_save_jobs_to_json,
                                ):
                                    with patch("builtins.print"):
                                        jobs, db_summary = (
                                            cli.run_company_career_pages_priority(args)
                                        )

        self.assertEqual(len(scrape_calls), 5)
        mock_linkedin_auth.assert_not_called()
        mock_list_company_career_pages.assert_called_once_with(seed_defaults=True)
        self.assertEqual(
            [call["site_name"] for call in scrape_calls],
            ["workday", "indeed", "glassdoor", "comeet", "greenhouse"],
        )
        self.assertEqual(len(jobs), 5)
        self.assertEqual(db_summary["marked_duplicate_jobs"], 4)
        self.assertEqual(len(saved_outputs), 1)
        self.assertEqual(len(populate_calls), 1)
        self.assertTrue(
            populate_calls[0][1]["mark_configured_company_job_board_duplicates"]
        )
        direct_rows = jobs[jobs["site"] == "workday"]
        self.assertEqual(
            direct_rows["direct_company_career_page_key"].tolist(),
            ["acme"],
        )

    def test_run_company_career_pages_table_only_scrapes_rows_without_boards(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(["--company-career-pages-table-only"])
        company_records = [
            {
                "id": 12,
                "company_key": "acme",
                "company_name": "Acme",
                "scraper_site": "workday",
                "career_page_url": "https://acme.wd1.myworkdayjobs.com/acme",
                "search_term": None,
                "location": "Israel",
                "country_indeed": "Israel",
                "results_wanted": 0,
                "description_format": "markdown",
                "description_limit": None,
                "request_timeout": 60,
                "extra_params": {},
            }
        ]
        direct_jobs = pd.DataFrame(
            [
                {
                    "site": "workday",
                    "title": "Backend Engineer",
                    "company": "Acme",
                    "location": "Israel",
                    "job_url": "https://acme.example/jobs/1",
                },
                {
                    "site": "workday",
                    "title": "Frontend Engineer",
                    "company": "Acme",
                    "location": "Israel",
                    "job_url": "https://acme.example/jobs/2",
                },
            ]
        )
        scrape_calls = []
        saved_outputs = []

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return direct_jobs

        def fake_save_jobs_to_json(output_path, jobs):
            saved_outputs.append((output_path, jobs))

        def fake_populate_jobs_table_from_file(output_path):
            return {
                "inserted": 1,
                "inserted_job_urls": ["https://acme.example/jobs/1"],
                "updated": 1,
                "updated_external_ids": [],
                "updated_job_urls": ["https://acme.example/jobs/2"],
                "parsed_jobs_activated": 0,
                "deleted_duplicate_rows": 0,
                "failed": 0,
            }

        with patch(
            "jobspy.jobs_table.list_company_career_pages",
            return_value=company_records,
        ) as mock_list_company_career_pages:
            with patch(
                "jobspy.jobs_table.populate_jobs_table_from_file",
                side_effect=fake_populate_jobs_table_from_file,
            ):
                with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
                    with patch.object(
                        cli,
                        "save_jobs_to_json",
                        side_effect=fake_save_jobs_to_json,
                    ):
                        with redirect_stdout(io.StringIO()) as output:
                            jobs, db_summary = (
                                cli.run_company_career_pages_table_only_once(args)
                            )

        mock_list_company_career_pages.assert_called_once_with(seed_defaults=True)
        self.assertEqual([call["site_name"] for call in scrape_calls], ["workday"])
        self.assertEqual(len(saved_outputs), 1)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs["source"].tolist(), ["Acme", "Acme"])
        self.assertEqual(db_summary["inserted"], 1)
        self.assertIn("Acme: new_jobs=1 scraped_jobs=2", output.getvalue())

    def test_main_dispatches_company_career_pages_scheduler(self) -> None:
        args = cli.build_parser().parse_args(["--company-career-pages"])

        class FakeParser:
            def parse_args(self):
                return args

        with patch.object(cli, "build_parser", return_value=FakeParser()):
            with patch.object(
                cli,
                "_resolve_and_print_linkedin_auth_context",
                return_value=({}, "guest-only"),
            ) as mock_log_auth:
                with patch.object(
                    cli,
                    "run_company_career_pages_scheduler",
                    return_value=None,
                ) as mock_scheduler:
                    cli.main()

        mock_log_auth.assert_not_called()
        mock_scheduler.assert_called_once_with(args)

    def test_table_only_scheduler_runs_immediately_then_sleeps_two_hours(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(["--company-career-pages-table-only"])
        fake_jobs = pd.DataFrame(
            [{"site": "workday", "job_url": "https://acme.example/jobs/1"}]
        )
        run_calls = []
        sleep_calls = []

        def fake_run_table_only_once(schedule_args):
            run_calls.append(schedule_args)
            return fake_jobs, {"inserted": 1, "inserted_job_urls": []}

        def fake_sleep(seconds):
            sleep_calls.append(seconds)
            raise KeyboardInterrupt()

        with patch("jobspy.jobs_table.ensure_company_career_pages_table") as mock_ensure:
            with patch.object(
                cli,
                "run_company_career_pages_table_only_once",
                side_effect=fake_run_table_only_once,
            ):
                with patch.object(cli, "_publish_scrape_finished_event"):
                    with patch.object(cli.time, "sleep", side_effect=fake_sleep):
                        with patch("builtins.print"):
                            with self.assertRaises(KeyboardInterrupt):
                                cli.run_company_career_pages_table_only_scheduler(args)

        mock_ensure.assert_called_once_with(seed_defaults=True)
        self.assertEqual(len(run_calls), 1)
        self.assertTrue(run_calls[0].company_career_pages_table_only)
        self.assertTrue(run_calls[0].scheduler)
        self.assertEqual(len(sleep_calls), 1)
        self.assertAlmostEqual(
            sleep_calls[0],
            cli.COMPANY_CAREER_PAGES_TABLE_ONLY_INTERVAL_HOURS * 60 * 60,
            delta=1,
        )

    def test_main_dispatches_company_career_pages_table_only_scheduler(self) -> None:
        args = cli.build_parser().parse_args(["--company-career-pages-table-only"])

        class FakeParser:
            def parse_args(self):
                return args

        with patch.object(cli, "build_parser", return_value=FakeParser()):
            with patch.object(
                cli,
                "_resolve_and_print_linkedin_auth_context",
                return_value=({}, "guest-only"),
            ) as mock_log_auth:
                with patch.object(
                    cli,
                    "run_company_career_pages_table_only_scheduler",
                    return_value=None,
                ) as mock_scheduler:
                    cli.main()

        mock_log_auth.assert_not_called()
        mock_scheduler.assert_called_once_with(args)

    def test_run_company_career_pages_now_runs_priority_once_and_publishes(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(["--company-career-pages-now"])
        fake_jobs = pd.DataFrame(
            [
                {"site": "linkedin", "job_url": "https://www.linkedin.com/jobs/view/1"},
                {"site": "comeet", "job_url": "https://www.comeet.com/jobs/acme/AA.001/job/1"},
            ]
        )
        priority_calls = []
        publish_calls = []

        def fake_run_company_career_pages_priority(run_args):
            priority_calls.append(run_args)
            return fake_jobs, {"inserted": 2, "updated": 0}

        def fake_publish(publish_args, *, runs):
            publish_calls.append((publish_args, runs))

        with patch.object(
            cli,
            "run_company_career_pages_priority",
            side_effect=fake_run_company_career_pages_priority,
        ):
            with patch.object(
                cli,
                "_publish_scrape_finished_event",
                side_effect=fake_publish,
            ):
                with patch("builtins.print"):
                    jobs, db_summary = cli.run_company_career_pages_now(args)

        self.assertIs(jobs, fake_jobs)
        self.assertEqual(db_summary, {"inserted": 2, "updated": 0})
        self.assertEqual(len(priority_calls), 1)
        run_args = priority_calls[0]
        self.assertFalse(run_args.scheduler)
        self.assertFalse(run_args.company_career_pages)
        self.assertTrue(run_args.company_career_pages_now)
        self.assertTrue(run_args.save_db)
        self.assertTrue(run_args.fetch_description)
        self.assertEqual(
            run_args.execution_mode,
            LinkedInScrapeMode.UNTIL_LAST_PAGE.value,
        )
        self.assertEqual(run_args.num_of_min, cli.FIRST_SCHEDULER_INTERVAL_MINUTES)
        self.assertEqual(len(publish_calls), 1)
        publish_args, runs = publish_calls[0]
        self.assertIs(publish_args, args)
        self.assertEqual(runs[0]["site"], "company_career_pages")
        self.assertFalse(runs[0]["scheduler"])
        self.assertEqual(runs[0]["jobs_retrieved"], 2)

    def test_main_dispatches_company_career_pages_now_without_scheduler(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(["--company-career-pages-now"])

        class FakeParser:
            def parse_args(self):
                return args

        with patch.object(cli, "build_parser", return_value=FakeParser()):
            with patch.object(
                cli,
                "_resolve_and_print_linkedin_auth_context",
                return_value=({}, "guest-only"),
            ) as mock_log_auth:
                with patch.object(
                    cli,
                    "run_company_career_pages_now",
                    return_value=(None, None),
                ) as mock_now:
                    with patch.object(cli, "run_company_career_pages_scheduler") as mock_scheduler:
                        cli.main()

        mock_log_auth.assert_not_called()
        mock_now.assert_called_once_with(args)
        mock_scheduler.assert_not_called()

    def test_company_career_pages_now_rejects_scheduler_flag(self) -> None:
        args = cli.build_parser().parse_args(
            ["--company-career-pages-now", "--scheduler"]
        )

        class FakeParser:
            def parse_args(self):
                return args

        with patch.object(cli, "build_parser", return_value=FakeParser()):
            with self.assertRaisesRegex(
                ValueError,
                "--company-career-pages-now cannot be combined with --scheduler",
            ):
                cli.main()

    def test_company_career_pages_table_only_rejects_scheduler_flag(self) -> None:
        args = cli.build_parser().parse_args(
            ["--company-career-pages-table-only", "--scheduler"]
        )

        class FakeParser:
            def parse_args(self):
                return args

        with patch.object(cli, "build_parser", return_value=FakeParser()):
            with self.assertRaisesRegex(
                ValueError,
                "--company-career-pages-table-only cannot be combined with --scheduler",
            ):
                cli.main()


class ComeetCliTests(unittest.TestCase):
    def test_run_comeet_persist_all_india_prints_links_without_persisting(self) -> None:
        args = cli.build_parser().parse_args(["--comeet-persist-all-india"])
        company_records = [
            {
                "company_name": "Acme",
                "comeet_base_url": "https://www.comeet.com/jobs/acme/AA.001",
            }
        ]
        collected_links = [
            ("Acme", "https://www.comeet.com/jobs/acme/AA.001/platform-engineer/1"),
            ("Acme", "https://www.comeet.com/jobs/acme/AA.001/data-engineer/2"),
        ]
        summary = {
            "companies": 1,
            "companies_with_jobs": 1,
            "failed": 0,
            "job_links": 2,
        }

        with patch(
            "jobspy.jobs_table.list_company_comeet_job_urls",
            return_value=company_records,
        ):
            with patch.object(
                cli,
                "_collect_comeet_country_jobs",
                return_value=(None, collected_links, summary),
            ) as mock_collect:
                with patch("builtins.print") as mock_print:
                    jobs, db_summary = cli.run_comeet_persist_all_india(args)

        self.assertIsNone(jobs)
        self.assertEqual(db_summary, summary)
        mock_collect.assert_called_once_with(
            company_records,
            country_indeed="India",
        )
        printed_text = "\n".join(
            " ".join(str(part) for part in print_call.args)
            for print_call in mock_print.call_args_list
        )
        self.assertIn("Starting Comeet India link-print run", printed_text)
        self.assertIn("India job links:", printed_text)
        self.assertIn(collected_links[0][1], printed_text)
        self.assertIn(collected_links[1][1], printed_text)

    def test_main_dispatches_comeet_persist_all_india_without_publish(self) -> None:
        args = cli.build_parser().parse_args(["--comeet-persist-all-india"])

        class FakeParser:
            def parse_args(self):
                return args

        with patch.object(cli, "build_parser", return_value=FakeParser()):
            with patch.object(
                cli,
                "run_comeet_persist_all_india",
                return_value=(None, {"job_links": 1}),
            ) as mock_run:
                with patch.object(
                    cli,
                    "_publish_scrape_finished_event",
                ) as mock_publish:
                    with patch.object(cli, "run_once") as mock_run_once:
                        cli.main()

        mock_run.assert_called_once_with(args)
        mock_publish.assert_not_called()
        mock_run_once.assert_not_called()

    def test_validate_exclusive_cli_modes_rejects_india_with_other_mode(self) -> None:
        args = cli.build_parser().parse_args(
            ["--comeet-persist-all-india", "--indeed-persist"]
        )

        with self.assertRaises(ValueError):
            cli._validate_exclusive_cli_modes(args)


class LinkedInIndiaCliTests(unittest.TestCase):
    def test_run_linkedin_scrape_india_uses_linkedin_only_without_persistence(
        self,
    ) -> None:
        with patch.dict(os.environ, {}, clear=True):
            args = cli.build_parser().parse_args(["--linkedin-scrape-india"])
        scrape_calls = []
        fake_jobs = pd.DataFrame(
            [
                {
                    "site": "linkedin",
                    "title": "Software Engineer",
                    "company": "Acme",
                    "location": "Bengaluru, India",
                    "date_posted": "2026-05-27",
                    "job_url": "https://www.linkedin.com/jobs/view/1",
                    "description": "LinkedIn India job",
                }
            ]
        )

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        with patch.object(cli, "load_linkedin_builtin_cookies", return_value={}):
            with patch.object(cli, "load_linkedin_chromium_cookies", return_value=({}, None)):
                with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
                    with patch.object(
                        cli,
                        "_hydrate_linkedin_jobs_with_descriptions",
                        return_value=(
                            fake_jobs,
                            {"requested": 1, "hydrated": 1, "failed": 0},
                        ),
                    ) as mock_hydrate:
                        with patch.object(cli, "save_jobs_to_json") as mock_save_jobs_to_json:
                            with patch.object(cli, "_print_console_safe"):
                                jobs, db_summary = cli.run_linkedin_scrape_india(args)

        self.assertTrue(jobs.equals(fake_jobs))
        self.assertIsNone(db_summary)
        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], "linkedin")
        self.assertEqual(scrape_calls[0]["location"], "India")
        self.assertEqual(scrape_calls[0]["country_indeed"], "India")
        self.assertEqual(
            scrape_calls[0]["linkedin_geo_id"],
            cli.DEFAULT_LINKEDIN_INDIA_GEO_ID,
        )
        self.assertEqual(
            scrape_calls[0]["linkedin_execution_mode"],
            LinkedInScrapeMode.UNTIL_LAST_PAGE,
        )
        self.assertEqual(scrape_calls[0]["num_of_min"], 60)
        self.assertIsNone(scrape_calls[0]["hours_old"])
        self.assertEqual(scrape_calls[0]["verbose"], 2)
        self.assertEqual(scrape_calls[0]["description_limit"], 0)
        self.assertFalse(scrape_calls[0]["linkedin_fetch_description"])
        self.assertEqual(scrape_calls[0]["linkedin_auth_cookies"], {})
        mock_hydrate.assert_called_once()
        mock_save_jobs_to_json.assert_not_called()

    def test_main_dispatches_linkedin_scrape_india_without_publish(self) -> None:
        args = cli.build_parser().parse_args(["--linkedin-scrape-india"])

        class FakeParser:
            def parse_args(self):
                return args

        with patch.object(cli, "build_parser", return_value=FakeParser()):
            with patch.object(
                cli,
                "run_linkedin_scrape_india",
                return_value=(None, None),
            ) as mock_run:
                with patch.object(
                    cli,
                    "_publish_scrape_finished_event",
                ) as mock_publish:
                    with patch.object(cli, "run_once") as mock_run_once:
                        cli.main()

        mock_run.assert_called_once_with(args)
        mock_publish.assert_not_called()
        mock_run_once.assert_not_called()

    def test_validate_exclusive_cli_modes_rejects_linkedin_india_with_other_mode(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(
            ["--linkedin-scrape-india", "--indeed-persist"]
        )

        with self.assertRaises(ValueError):
            cli._validate_exclusive_cli_modes(args)

    def test_scrape_linkedin_india_shard_uses_metadata_only_configuration(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            args = cli.build_parser().parse_args(["--linkedin-scrape-india-sharded"])
        scrape_calls = []
        fake_jobs = pd.DataFrame(
            [
                {
                    "site": "linkedin",
                    "title": "Software Engineer",
                    "company": "Acme",
                    "location": "Mumbai, Maharashtra, India",
                    "date_posted": "2026-05-27",
                    "job_url": "https://www.linkedin.com/jobs/view/1",
                }
            ]
        )
        shard = {
            "name": "mumbai",
            "location": "Mumbai, Maharashtra, India",
            "linkedin_geo_id": None,
            "is_remote": False,
        }

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        with patch.object(cli, "load_linkedin_builtin_cookies", return_value={}):
            with patch.object(cli, "load_linkedin_chromium_cookies", return_value=({}, None)):
                with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
                    jobs, summary = cli._scrape_linkedin_india_shard(
                        shard,
                        args=args,
                    )

        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], "linkedin")
        self.assertEqual(scrape_calls[0]["location"], shard["location"])
        self.assertEqual(scrape_calls[0]["country_indeed"], "India")
        self.assertFalse(scrape_calls[0]["linkedin_fetch_description"])
        self.assertEqual(scrape_calls[0]["description_limit"], 0)
        self.assertEqual(
            scrape_calls[0]["linkedin_execution_mode"],
            LinkedInScrapeMode.UNTIL_LAST_PAGE,
        )
        self.assertEqual(scrape_calls[0]["num_of_min"], 60)
        self.assertEqual(scrape_calls[0]["verbose"], 0)
        self.assertEqual(scrape_calls[0]["linkedin_auth_cookies"], {})
        self.assertIn("search_shard", jobs.columns)
        self.assertEqual(jobs["search_shard"].tolist(), ["mumbai"])
        self.assertEqual(summary["name"], "mumbai")
        self.assertEqual(summary["jobs"], 1)

    def test_run_linkedin_scrape_india_sharded_dedupes_merged_jobs(self) -> None:
        args = cli.build_parser().parse_args(["--linkedin-scrape-india-sharded"])
        shards = [
            {
                "name": "india-catch-all",
                "location": "India",
                "linkedin_geo_id": cli.DEFAULT_LINKEDIN_INDIA_GEO_ID,
                "is_remote": False,
            },
            {
                "name": "bengaluru",
                "location": "Bengaluru, Karnataka, India",
                "linkedin_geo_id": None,
                "is_remote": False,
            },
            {
                "name": "india-remote",
                "location": "India",
                "linkedin_geo_id": cli.DEFAULT_LINKEDIN_INDIA_GEO_ID,
                "is_remote": True,
            },
        ]
        shard_frames = {
            "india-catch-all": pd.DataFrame(
                [
                    {
                        "site": "linkedin",
                        "title": "Job 1",
                        "company": "Acme",
                        "location": "India",
                        "date_posted": "2026-05-27",
                        "job_url": "https://www.linkedin.com/jobs/view/1",
                        "search_shard": "india-catch-all",
                    },
                    {
                        "site": "linkedin",
                        "title": "Job 2",
                        "company": "Acme",
                        "location": "India",
                        "date_posted": "2026-05-27",
                        "job_url": "https://www.linkedin.com/jobs/view/2",
                        "search_shard": "india-catch-all",
                    },
                ]
            ),
            "bengaluru": pd.DataFrame(
                [
                    {
                        "site": "linkedin",
                        "title": "Job 2 duplicate",
                        "company": "Acme",
                        "location": "Bengaluru, Karnataka, India",
                        "date_posted": "2026-05-27",
                        "job_url": "https://www.linkedin.com/jobs/view/2",
                        "search_shard": "bengaluru",
                    },
                    {
                        "site": "linkedin",
                        "title": "Job 3",
                        "company": "Acme",
                        "location": "Bengaluru, Karnataka, India",
                        "date_posted": "2026-05-27",
                        "job_url": "https://www.linkedin.com/jobs/view/3",
                        "search_shard": "bengaluru",
                    },
                ]
            ),
            "india-remote": pd.DataFrame(),
        }

        def fake_scrape_shard(shard, *, args):
            shard_jobs = shard_frames[shard["name"]]
            return shard_jobs, {
                "name": shard["name"],
                "location": shard["location"],
                "is_remote": shard["is_remote"],
                "jobs": 0 if shard_jobs.empty else len(shard_jobs),
                "elapsed_seconds": 1.25,
            }

        with patch.object(cli, "_get_linkedin_india_shards", return_value=shards):
            with patch.object(
                cli,
                "_scrape_linkedin_india_shard",
                side_effect=fake_scrape_shard,
            ):
                with patch.object(
                    cli,
                    "_hydrate_linkedin_jobs_with_descriptions",
                    side_effect=lambda jobs, **kwargs: (
                        jobs.assign(
                            description=[
                                "desc 1",
                                "desc 2",
                                "desc 3",
                            ]
                        ),
                        {"requested": 3, "hydrated": 3, "failed": 0},
                    ),
                ) as mock_hydrate:
                    with patch.object(cli, "_print_console_safe"):
                        jobs, summary = cli.run_linkedin_scrape_india_sharded(args)

        self.assertEqual(len(jobs), 3)
        self.assertEqual(
            set(jobs["job_url"].tolist()),
            {
                "https://www.linkedin.com/jobs/view/1",
                "https://www.linkedin.com/jobs/view/2",
                "https://www.linkedin.com/jobs/view/3",
            },
        )
        self.assertEqual(summary["shards"], 3)
        self.assertEqual(summary["shards_with_jobs"], 2)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["raw_rows"], 4)
        self.assertEqual(summary["unique_rows"], 3)
        self.assertEqual(summary["duplicates_removed"], 1)
        self.assertEqual(summary["descriptions_requested"], 3)
        self.assertEqual(summary["descriptions_hydrated"], 3)
        self.assertEqual(summary["description_failures"], 0)
        mock_hydrate.assert_called_once()

    def test_hydrate_linkedin_description_batch_keeps_apply_urls_and_ignores_logo(
        self,
    ) -> None:
        job_url = "https://www.linkedin.com/jobs/view/1"
        scraper = Mock()
        scraper._normalize_linkedin_job_url.return_value = job_url
        scraper._extract_job_id.return_value = "1"
        scraper._get_job_details.return_value = {
            "description": "Role description",
            "job_url": job_url,
            "apply_url": "https://www.linkedin.com/jobs/view/1/apply",
            "job_url_direct": "https://company.example.com/jobs/1/apply",
            "applications_count": 7,
            "job_level": "Senior",
            "company_industry": "Software",
            "company_logo": "https://cdn.example.com/logo.png",
            "job_function": "Engineering",
        }

        with patch.object(
            cli,
            "_build_linkedin_description_scraper",
            return_value=scraper,
        ):
            updates, summary = cli._hydrate_linkedin_description_batch([(0, job_url)])

        self.assertEqual(
            updates,
            [
                (
                    0,
                    {
                        "description": "Role description",
                        "job_url": job_url,
                        "apply_url": "https://www.linkedin.com/jobs/view/1/apply",
                        "job_url_direct": "https://company.example.com/jobs/1/apply",
                        "applications_count": 7,
                        "job_level": "senior",
                        "company_industry": "Software",
                        "job_function": "Engineering",
                    },
                )
            ],
        )
        self.assertEqual(summary, {"hydrated": 1, "failed": 0})

    def test_main_dispatches_linkedin_scrape_india_sharded_without_publish(self) -> None:
        args = cli.build_parser().parse_args(["--linkedin-scrape-india-sharded"])

        class FakeParser:
            def parse_args(self):
                return args

        with patch.object(cli, "build_parser", return_value=FakeParser()):
            with patch.object(
                cli,
                "run_linkedin_scrape_india_sharded",
                return_value=(None, None),
            ) as mock_run:
                with patch.object(
                    cli,
                    "_publish_scrape_finished_event",
                ) as mock_publish:
                    with patch.object(cli, "run_once") as mock_run_once:
                        cli.main()

        mock_run.assert_called_once_with(args)
        mock_publish.assert_not_called()
        mock_run_once.assert_not_called()

    def test_validate_exclusive_cli_modes_rejects_linkedin_india_sharded_with_other_mode(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(
            ["--linkedin-scrape-india-sharded", "--indeed-persist"]
        )

        with self.assertRaises(ValueError):
            cli._validate_exclusive_cli_modes(args)

    def test_run_linkedin_persist_india_sharded_saves_and_populates(self) -> None:
        args = cli.build_parser().parse_args(["--linkedin-persist-india-sharded"])
        fake_jobs = pd.DataFrame(
            [
                {
                    "site": "linkedin",
                    "title": "Job 1",
                    "company": "Acme",
                    "location": "India",
                    "date_posted": "2026-05-27",
                    "job_url": "https://www.linkedin.com/jobs/view/1",
                    "description": "desc 1",
                }
            ]
        )
        saved_outputs = []
        populate_calls = []

        def fake_save_jobs_to_json(output_path, jobs):
            saved_outputs.append((output_path, jobs))

        def fake_populate_jobs_table_from_file(output_path):
            populate_calls.append(output_path)
            return {"inserted": 1, "updated": 0}

        with patch.object(
            cli,
            "run_linkedin_scrape_india_sharded",
            return_value=(fake_jobs, {"unique_rows": 1}),
        ) as mock_run:
            with patch.object(cli, "save_jobs_to_json", side_effect=fake_save_jobs_to_json):
                with patch(
                    "jobspy.jobs_table.populate_jobs_table_from_file",
                    side_effect=fake_populate_jobs_table_from_file,
                ):
                    with patch("builtins.print") as mock_print:
                        jobs, db_summary = cli.run_linkedin_persist_india_sharded(args)

        self.assertTrue(jobs.equals(fake_jobs))
        self.assertEqual(db_summary, {"inserted": 1, "updated": 0})
        mock_run.assert_called_once()
        sharded_args = mock_run.call_args.args[0]
        self.assertIsNot(sharded_args, args)
        self.assertTrue(sharded_args.suppress_preview)
        self.assertEqual(len(saved_outputs), 1)
        self.assertTrue(saved_outputs[0][1].equals(fake_jobs))
        self.assertEqual(len(populate_calls), 1)
        mock_print.assert_called_once_with("DB upsert summary: inserted=1 updated=0")

    def test_main_dispatches_linkedin_persist_india_sharded_and_publishes(self) -> None:
        args = cli.build_parser().parse_args(["--linkedin-persist-india-sharded"])
        fake_jobs = pd.DataFrame(
            [
                {
                    "site": "linkedin",
                    "job_url": "https://www.linkedin.com/jobs/view/1",
                }
            ]
        )
        publish_calls = []

        class FakeParser:
            def parse_args(self):
                return args

        def fake_publish(publish_args, *, runs):
            publish_calls.append((publish_args, runs))

        with patch.object(cli, "build_parser", return_value=FakeParser()):
            with patch.object(
                cli,
                "run_linkedin_persist_india_sharded",
                return_value=(fake_jobs, {"inserted": 1}),
            ):
                with patch.object(
                    cli,
                    "_publish_scrape_finished_event",
                    side_effect=fake_publish,
                ):
                    cli.main()

        self.assertEqual(len(publish_calls), 1)
        publish_args, runs = publish_calls[0]
        self.assertIs(publish_args, args)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["site"], "linkedin")
        self.assertEqual(runs[0]["mode"], "persist-india-sharded")
        self.assertEqual(runs[0]["jobs_retrieved"], 1)
        self.assertTrue(runs[0]["persisted"])

    def test_validate_exclusive_cli_modes_rejects_linkedin_persist_india_sharded_with_other_mode(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(
            ["--linkedin-persist-india-sharded", "--indeed-persist"]
        )

        with self.assertRaises(ValueError):
            cli._validate_exclusive_cli_modes(args)


class GreenhouseCliTests(unittest.TestCase):
    def test_build_greenhouse_auth_cookies_from_header(self) -> None:
        args = cli.build_parser().parse_args(
            [
                "--greenhouse-debug-search",
                "--greenhouse-cookie-header",
                (
                    "Cookie: _session_id=session-123; "
                    "MYGREENHOUSE-XSRF-TOKEN=token-456; Secure; Path=/"
                ),
            ]
        )

        cookies = cli._build_greenhouse_auth_cookies(args)

        self.assertEqual(cookies["_session_id"], "session-123")
        self.assertEqual(cookies["MYGREENHOUSE-XSRF-TOKEN"], "token-456")
        self.assertEqual(
            cli._resolve_greenhouse_xsrf_token(args, cookies),
            "token-456",
        )

    def test_explicit_greenhouse_xsrf_token_overrides_cookie_value(self) -> None:
        args = cli.build_parser().parse_args(
            [
                "--greenhouse-debug-search",
                "--greenhouse-cookie",
                "_session_id=session-123",
                "--greenhouse-cookie",
                "MYGREENHOUSE-XSRF-TOKEN=token-from-cookie",
                "--greenhouse-xsrf-token",
                "token-from-flag",
            ]
        )

        cookies = cli._build_greenhouse_auth_cookies(args)

        self.assertEqual(
            cli._resolve_greenhouse_xsrf_token(args, cookies),
            "token-from-flag",
        )

    def test_run_greenhouse_persist_uses_until_last_page_and_persists(self) -> None:
        args = cli.build_parser().parse_args(
            [
                "--greenhouse-persist",
                "--greenhouse-cookie",
                "_session_id=session-123",
                "--greenhouse-cookie",
                "MYGREENHOUSE-XSRF-TOKEN=token-456",
                "--output",
                "greenhouse_jobs.json",
            ]
        )

        scrape_calls = []
        populate_calls = []

        class FakeJobs:
            empty = False

            def __len__(self) -> int:
                return 2

            @property
            def columns(self):
                return ["title", "company", "location", "date_posted", "job_url", "apply_url"]

            def __getitem__(self, key):
                return self

            def head(self, count):
                return self

            def to_string(self, index=False):
                return "fake greenhouse preview"

        fake_jobs = FakeJobs()

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        def fake_save_jobs_to_json(output_path, jobs):
            self.assertEqual(jobs, fake_jobs)

        def fake_populate_jobs_table_from_file(output_path):
            populate_calls.append(output_path)
            return {"inserted": 2, "updated": 0}

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            with patch.object(cli, "save_jobs_to_json", side_effect=fake_save_jobs_to_json):
                with patch("jobspy.jobs_table.populate_jobs_table_from_file", side_effect=fake_populate_jobs_table_from_file):
                    with patch("builtins.print") as mock_print:
                        jobs, db_summary = cli.run_greenhouse_persist(args)

        self.assertIs(jobs, fake_jobs)
        self.assertEqual(db_summary, {"inserted": 2, "updated": 0})
        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(
            scrape_calls[0]["greenhouse_execution_mode"],
            GreenhouseScrapeMode.UNTIL_LAST_PAGE,
        )
        self.assertIsNone(scrape_calls[0]["description_limit"])
        self.assertEqual(scrape_calls[0]["results_wanted"], 1)
        self.assertEqual(len(populate_calls), 1)
        mock_print.assert_any_call("DB upsert summary: inserted=2 updated=0")


class LinkedInProfileCliTests(unittest.TestCase):
    def test_run_once_dispatches_profile_inspection(self) -> None:
        args = cli.build_parser().parse_args(
            [
                "--execution-mode",
                LinkedInScrapeMode.INSPECT_SINGLE_PROFILE.value,
                "--profile-url",
                "https://www.linkedin.com/in/shauly-yonay",
            ]
        )

        with patch.object(
            cli,
            "run_single_profile_inspect",
            return_value=({"profile_fetch": {"status_code": 200}}, None),
        ) as mock_run_single_profile_inspect:
            inspection, db_summary = cli.run_once(args)

        self.assertEqual(inspection, {"profile_fetch": {"status_code": 200}})
        self.assertIsNone(db_summary)
        mock_run_single_profile_inspect.assert_called_once_with(args)

    def test_run_single_profile_inspect_uses_guest_mode(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            args = cli.build_parser().parse_args(
                [
                    "--execution-mode",
                    LinkedInScrapeMode.INSPECT_SINGLE_PROFILE.value,
                    "--profile-url",
                    "https://www.linkedin.com/in/shauly-yonay",
                ]
            )
        fake_profile_fetch = {
            "requested_url": "https://www.linkedin.com/in/shauly-yonay",
            "response_url": "https://www.linkedin.com/in/shauly-yonay",
            "status_code": 200,
            "auth": {"enabled": True, "cookie_names": ["JSESSIONID", "li_at"]},
            "extracted": {"profile_slug": "shauly-yonay"},
            "sections": {
                "summary": "Profile summary",
                "about": "Profile summary",
                "skills": ["Python"],
                "experience": [],
                "education": [],
                "languages": [],
            },
            "signals": {"page_variant": "profile"},
        }

        with patch("jobspy.linkedin.profile.LinkedInProfileInspector") as mock_inspector_class:
            mock_inspector_class.return_value.inspect_profile.return_value = (
                fake_profile_fetch
            )
            with patch.object(cli, "load_linkedin_builtin_cookies", return_value={}):
                with patch.object(cli, "load_linkedin_chromium_cookies", return_value=({}, None)):
                    with patch("builtins.print"):
                        inspection, db_summary = cli.run_single_profile_inspect(args)

        self.assertEqual(inspection["profile_fetch"], fake_profile_fetch)
        self.assertEqual(inspection["auth_source"], "guest-only")
        self.assertEqual(
            inspection["summary"]["profile_slug"],
            "shauly-yonay",
        )
        self.assertEqual(
            inspection["sections"],
            {
                "summary": "Profile summary",
                "about": "Profile summary",
                "skills": ["Python"],
                "experience": [],
                "education": [],
                "languages": [],
            },
        )
        self.assertIsNone(db_summary)
        mock_inspector_class.assert_called_once_with(auth_cookies={})
        mock_inspector_class.return_value.inspect_profile.assert_called_once_with(
            "https://www.linkedin.com/in/shauly-yonay",
            include_raw_html=False,
        )

    def test_run_single_profile_inspect_prints_raw_html_when_requested(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            args = cli.build_parser().parse_args(
                [
                    "--execution-mode",
                    LinkedInScrapeMode.INSPECT_SINGLE_PROFILE.value,
                    "--profile-url",
                    "https://www.linkedin.com/in/shauly-yonay",
                    "--print-html",
                ]
            )
        fake_profile_fetch = {
            "requested_url": "https://www.linkedin.com/in/shauly-yonay",
            "response_url": "https://www.linkedin.com/in/shauly-yonay",
            "status_code": 200,
            "auth": {"enabled": True, "cookie_names": ["JSESSIONID", "li_at"]},
            "extracted": {"profile_slug": "shauly-yonay"},
            "sections": {
                "summary": "Profile summary",
                "about": "Profile summary",
                "skills": [],
                "experience": [],
                "education": [],
                "languages": [],
            },
            "signals": {"page_variant": "profile"},
            "raw_html": "<html>profile</html>",
        }

        with patch("jobspy.linkedin.profile.LinkedInProfileInspector") as mock_inspector_class:
            mock_inspector_class.return_value.inspect_profile.return_value = (
                fake_profile_fetch
            )
            with patch.object(cli, "load_linkedin_builtin_cookies", return_value={}):
                with patch.object(cli, "load_linkedin_chromium_cookies", return_value=({}, None)):
                    with patch("builtins.print") as mock_print:
                        inspection, db_summary = cli.run_single_profile_inspect(args)

        self.assertNotIn("raw_html", inspection["profile_fetch"])
        self.assertIsNone(db_summary)
        self.assertEqual(inspection["auth_source"], "guest-only")
        mock_inspector_class.return_value.inspect_profile.assert_called_once_with(
            "https://www.linkedin.com/in/shauly-yonay",
            include_raw_html=True,
        )
        mock_print.assert_any_call("<html>profile</html>")


class LinkedInAuthCookieTests(unittest.TestCase):
    def test_format_linkedin_auth_cookies_includes_values(self) -> None:
        self.assertEqual(
            cli._format_linkedin_auth_cookies(
                {
                    "li_at": "session-cookie",
                    "JSESSIONID": '"ajax:test"',
                }
            ),
            'JSESSIONID="ajax:test", li_at=session-cookie',
        )
        self.assertEqual(cli._format_linkedin_auth_cookies({}), "disabled")

    def test_resolve_linkedin_geo_id_defaults_for_israel_location(self) -> None:
        args = cli.build_parser().parse_args([])

        self.assertEqual(
            cli._resolve_linkedin_geo_id(args),
            cli.DEFAULT_LINKEDIN_ISRAEL_GEO_ID,
        )

    def test_resolve_linkedin_geo_id_uses_explicit_override(self) -> None:
        args = cli.build_parser().parse_args(
            [
                "--location",
                "Center District, Israel",
                "--linkedin-geo-id",
                "123456",
            ]
        )

        self.assertEqual(cli._resolve_linkedin_geo_id(args), 123456)

    def test_resolve_linkedin_geo_id_is_none_for_non_default_location(self) -> None:
        args = cli.build_parser().parse_args(
            [
                "--location",
                "Center District, Israel",
            ]
        )

        self.assertIsNone(cli._resolve_linkedin_geo_id(args))

    def test_main_rejects_invalid_linkedin_page_delay_range(self) -> None:
        args = cli.build_parser().parse_args(
            [
                "--linkedin-page-delay-min",
                "2.0",
                "--linkedin-page-delay-max",
                "1.0",
            ]
        )

        class FakeParser:
            def parse_args(self):
                return args

        with patch.object(cli, "build_parser", return_value=FakeParser()):
            with self.assertRaisesRegex(
                ValueError,
                "--linkedin-page-delay-min cannot be greater than --linkedin-page-delay-max",
            ):
                cli.main()

    def test_build_linkedin_auth_context_prefers_explicit_cookies(
        self,
    ) -> None:
        with patch.dict(os.environ, {}, clear=True):
            args = cli.build_parser().parse_args(
                [
                    "--linkedin-cookie",
                    "li_at=explicit-li-at",
                    "--linkedin-cookie",
                    'JSESSIONID="ajax:explicit"',
                ]
            )

        with patch.object(cli, "load_linkedin_chromium_cookies", return_value=({}, None)):
            cookies, auth_source = cli._build_linkedin_auth_context(args)

        self.assertEqual(
            cookies,
            {
                "li_at": "explicit-li-at",
                "JSESSIONID": '"ajax:explicit"',
            },
        )
        self.assertEqual(auth_source, "explicit")

    def test_build_linkedin_auth_context_returns_hardcoded_when_no_cookies_exist(
        self,
    ) -> None:
        with patch.dict(os.environ, {}, clear=True):
            args = cli.build_parser().parse_args([])

        with patch.object(
            cli,
            "load_linkedin_builtin_cookies",
            return_value={
                "li_at": "hardcoded-li-at",
                'JSESSIONID': '"ajax:hardcoded"',
            },
        ):
            cookies, auth_source = cli._build_linkedin_auth_context(args)

        self.assertEqual(
            cookies,
            {
                "li_at": "hardcoded-li-at",
                'JSESSIONID': '"ajax:hardcoded"',
            },
        )
        self.assertEqual(auth_source, "hardcoded")

    def test_build_linkedin_auth_context_returns_guest_only_when_every_source_is_empty(
        self,
    ) -> None:
        with patch.dict(os.environ, {}, clear=True):
            args = cli.build_parser().parse_args([])

        with patch.object(cli, "load_linkedin_builtin_cookies", return_value={}):
            with patch.object(cli, "load_linkedin_chromium_cookies", return_value=({}, None)):
                cookies, auth_source = cli._build_linkedin_auth_context(args)

        self.assertEqual(cookies, {})
        self.assertEqual(auth_source, "guest-only")

    def test_main_prints_linkedin_auth_at_process_startup_for_default_flow(
        self,
    ) -> None:
        args = cli.build_parser().parse_args([])
        fake_jobs = pd.DataFrame([{"site": "linkedin", "job_url": "https://www.linkedin.com/jobs/view/1"}])

        class FakeParser:
            def parse_args(self):
                return args

        with patch.object(cli, "build_parser", return_value=FakeParser()):
            with patch.object(
                cli,
                "_resolve_and_print_linkedin_auth_context",
                return_value=({}, "guest-only"),
            ) as mock_log_auth:
                with patch.object(cli, "run_once", return_value=(fake_jobs, None)):
                    with patch.object(cli, "_publish_scrape_finished_event"):
                        cli.main()

        mock_log_auth.assert_called_once_with(
            args,
            context="process-startup",
        )

    def test_main_skips_linkedin_auth_startup_logging_for_greenhouse_only_flow(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(["--greenhouse-debug-search"])

        class FakeParser:
            def parse_args(self):
                return args

        with patch.object(cli, "build_parser", return_value=FakeParser()):
            with patch.object(
                cli,
                "_resolve_and_print_linkedin_auth_context",
            ) as mock_log_auth:
                with patch.object(cli, "run_greenhouse_debug_search") as mock_run:
                    cli.main()

        mock_log_auth.assert_not_called()
        mock_run.assert_called_once_with(args)

    def test_main_skips_linkedin_auth_startup_logging_for_apple_only_flow(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(["--apple-persist"])

        class FakeParser:
            def parse_args(self):
                return args

        with patch.object(cli, "build_parser", return_value=FakeParser()):
            with patch.object(
                cli,
                "_resolve_and_print_linkedin_auth_context",
            ) as mock_log_auth:
                with patch.object(
                    cli,
                    "run_apple_persist",
                    return_value=(pd.DataFrame(), None),
                ) as mock_run:
                    with patch.object(cli, "_publish_scrape_finished_event"):
                        cli.main()

        mock_log_auth.assert_not_called()
        mock_run.assert_called_once_with(args)

    def test_main_skips_linkedin_auth_startup_logging_for_google_careers_only_flow(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(["--google-careers-persist"])

        class FakeParser:
            def parse_args(self):
                return args

        with patch.object(cli, "build_parser", return_value=FakeParser()):
            with patch.object(
                cli,
                "_resolve_and_print_linkedin_auth_context",
            ) as mock_log_auth:
                with patch.object(
                    cli,
                    "run_google_careers_persist",
                    return_value=(pd.DataFrame(), None),
                ) as mock_run:
                    with patch.object(cli, "_publish_scrape_finished_event"):
                        cli.main()

        mock_log_auth.assert_not_called()
        mock_run.assert_called_once_with(args)


class AmdocsCliTests(unittest.TestCase):
    def test_run_amdocs_test_scrape_uses_eightfold_site(self) -> None:
        args = cli.build_parser().parse_args(["--amdocs-test-scrape"])
        scrape_calls = []

        class FakeJobs:
            empty = False

            def __len__(self) -> int:
                return 2

            @property
            def columns(self):
                return [
                    "title",
                    "company",
                    "location",
                    "date_posted",
                    "listing_type",
                    "is_remote",
                    "job_url",
                    "description",
                ]

            def __getitem__(self, key):
                return self

            def head(self, count):
                return self

            def to_string(self, index=False):
                return "fake amdocs preview"

            def to_json(self, orient="records", date_format="iso", force_ascii=False):
                return (
                    '[{"title":"Architect","company":"Amdocs",'
                    '"location":"Ra\'anana, Center District, Israel",'
                    '"job_url":"https://jobs.amdocs.com/careers/job/1",'
                    '"description":"Hello"}]'
                )

        fake_jobs = FakeJobs()

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            jobs, db_summary = cli.run_amdocs_test_scrape(args)

        self.assertIs(jobs, fake_jobs)
        self.assertIsNone(db_summary)
        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], "eightfold")
        self.assertEqual(
            scrape_calls[0]["eightfold_company_url"],
            cli.DEFAULT_AMDOCS_BASE_URL,
        )
        self.assertEqual(scrape_calls[0]["results_wanted"], args.results)
        self.assertEqual(scrape_calls[0]["description_limit"], 1)
        self.assertEqual(scrape_calls[0]["verbose"], 2)
        self.assertTrue(scrape_calls[0]["eightfold_debug_trace"])

    def test_run_amdocs_persist_uses_eightfold_site_and_persists(self) -> None:
        args = cli.build_parser().parse_args(
            [
                "--amdocs-persist",
                "--output",
                "amdocs_jobs.json",
            ]
        )

        scrape_calls = []
        populate_calls = []

        class FakeJobs:
            empty = False

            def __len__(self) -> int:
                return 2

            @property
            def columns(self):
                return [
                    "title",
                    "company",
                    "location",
                    "date_posted",
                    "listing_type",
                    "is_remote",
                    "job_url",
                ]

            def __getitem__(self, key):
                return self

            def head(self, count):
                return self

            def to_string(self, index=False):
                return "fake amdocs persist preview"

        fake_jobs = FakeJobs()

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        def fake_save_jobs_to_json(output_path, jobs):
            self.assertEqual(jobs, fake_jobs)

        def fake_populate_jobs_table_from_file(output_path):
            populate_calls.append(output_path)
            return {"inserted": 2, "updated": 0}

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            with patch.object(cli, "save_jobs_to_json", side_effect=fake_save_jobs_to_json):
                with patch(
                    "jobspy.jobs_table.populate_jobs_table_from_file",
                    side_effect=fake_populate_jobs_table_from_file,
                ):
                    with patch("builtins.print") as mock_print:
                        jobs, db_summary = cli.run_amdocs_persist(args)

        self.assertIs(jobs, fake_jobs)
        self.assertEqual(db_summary, {"inserted": 2, "updated": 0})
        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], "eightfold")
        self.assertEqual(
            scrape_calls[0]["eightfold_company_url"],
            cli.DEFAULT_AMDOCS_BASE_URL,
        )
        self.assertEqual(scrape_calls[0]["results_wanted"], args.results)
        self.assertIsNone(scrape_calls[0]["description_limit"])
        self.assertEqual(scrape_calls[0]["verbose"], 0)
        self.assertFalse(scrape_calls[0]["eightfold_debug_trace"])
        self.assertEqual(len(populate_calls), 1)
        mock_print.assert_any_call("DB upsert summary: inserted=2 updated=0")

    def test_main_dispatches_apple_persist_and_publishes(self) -> None:
        args = cli.build_parser().parse_args(["--apple-persist"])
        fake_jobs = pd.DataFrame(
            [
                {
                    "site": "apple",
                    "job_url": "https://jobs.apple.com/en-il/details/2001/software-engineer",
                }
            ]
        )
        publish_calls = []

        class FakeParser:
            def parse_args(self):
                return args

        def fake_publish(publish_args, *, runs):
            publish_calls.append((publish_args, runs))

        with patch.object(cli, "build_parser", return_value=FakeParser()):
            with patch.object(
                cli,
                "run_apple_persist",
                return_value=(fake_jobs, {"inserted": 1}),
            ):
                with patch.object(
                    cli,
                    "_publish_scrape_finished_event",
                    side_effect=fake_publish,
                ):
                    cli.main()

        self.assertEqual(len(publish_calls), 1)
        publish_args, runs = publish_calls[0]
        self.assertIs(publish_args, args)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["site"], "apple")
        self.assertEqual(runs[0]["platform"], "apple-careers")
        self.assertEqual(runs[0]["jobs_retrieved"], 1)
        self.assertTrue(runs[0]["persisted"])


class AppleCliTests(unittest.TestCase):
    def test_run_apple_persist_uses_apple_site_and_persists(self) -> None:
        args = cli.build_parser().parse_args(
            [
                "--apple-persist",
                "--output",
                "apple_jobs.json",
            ]
        )

        scrape_calls = []
        populate_calls = []

        class FakeJobs:
            empty = False

            def __len__(self) -> int:
                return 2

            @property
            def columns(self):
                return [
                    "title",
                    "company",
                    "location",
                    "date_posted",
                    "job_function",
                    "is_remote",
                    "job_url",
                ]

            def __getitem__(self, key):
                return self

            def head(self, count):
                return self

            def to_string(self, index=False):
                return "fake apple persist preview"

        fake_jobs = FakeJobs()

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        def fake_save_jobs_to_json(output_path, jobs):
            self.assertEqual(jobs, fake_jobs)

        def fake_populate_jobs_table_from_file(output_path):
            populate_calls.append(output_path)
            return {"inserted": 2, "updated": 0}

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            with patch.object(cli, "save_jobs_to_json", side_effect=fake_save_jobs_to_json):
                with patch(
                    "jobspy.jobs_table.populate_jobs_table_from_file",
                    side_effect=fake_populate_jobs_table_from_file,
                ):
                    with patch("builtins.print") as mock_print:
                        jobs, db_summary = cli.run_apple_persist(args)

        self.assertIs(jobs, fake_jobs)
        self.assertEqual(db_summary, {"inserted": 2, "updated": 0})
        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], "apple")
        self.assertEqual(
            scrape_calls[0]["apple_search_url"],
            cli.DEFAULT_APPLE_SEARCH_URL,
        )
        self.assertEqual(scrape_calls[0]["results_wanted"], args.results)
        self.assertIsNone(scrape_calls[0]["description_limit"])
        self.assertEqual(scrape_calls[0]["verbose"], 0)
        self.assertEqual(len(populate_calls), 1)
        mock_print.assert_any_call("DB upsert summary: inserted=2 updated=0")


class GoogleCareersCliTests(unittest.TestCase):
    def test_main_dispatches_google_careers_persist_and_publishes(self) -> None:
        args = cli.build_parser().parse_args(["--google-careers-persist"])
        fake_jobs = pd.DataFrame(
            [
                {
                    "site": "google_careers",
                    "job_url": (
                        "https://www.google.com/about/careers/applications/"
                        "jobs/results/123-software-engineer?q=&location=Israel&hl=en"
                    ),
                }
            ]
        )
        publish_calls = []

        class FakeParser:
            def parse_args(self):
                return args

        def fake_publish(publish_args, *, runs):
            publish_calls.append((publish_args, runs))

        with patch.object(cli, "build_parser", return_value=FakeParser()):
            with patch.object(
                cli,
                "run_google_careers_persist",
                return_value=(fake_jobs, {"inserted": 1}),
            ):
                with patch.object(
                    cli,
                    "_publish_scrape_finished_event",
                    side_effect=fake_publish,
                ):
                    cli.main()

        self.assertEqual(len(publish_calls), 1)
        publish_args, runs = publish_calls[0]
        self.assertIs(publish_args, args)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["site"], "google_careers")
        self.assertEqual(runs[0]["platform"], "google-careers")
        self.assertEqual(runs[0]["jobs_retrieved"], 1)
        self.assertTrue(runs[0]["persisted"])

    def test_run_google_careers_persist_uses_google_careers_site_and_persists(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(
            [
                "--google-careers-persist",
                "--output",
                "google_careers_jobs.json",
            ]
        )

        scrape_calls = []
        populate_calls = []

        class FakeJobs:
            empty = False

            def __len__(self) -> int:
                return 2

            @property
            def columns(self):
                return [
                    "title",
                    "company",
                    "location",
                    "date_posted",
                    "is_remote",
                    "job_url",
                    "apply_url",
                ]

            def __getitem__(self, key):
                return self

            def head(self, count):
                return self

            def to_string(self, index=False):
                return "fake google careers persist preview"

        fake_jobs = FakeJobs()

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        def fake_save_jobs_to_json(output_path, jobs):
            self.assertEqual(jobs, fake_jobs)

        def fake_populate_jobs_table_from_file(output_path):
            populate_calls.append(output_path)
            return {"inserted": 2, "updated": 0}

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            with patch.object(
                cli,
                "save_jobs_to_json",
                side_effect=fake_save_jobs_to_json,
            ):
                with patch(
                    "jobspy.jobs_table.populate_jobs_table_from_file",
                    side_effect=fake_populate_jobs_table_from_file,
                ):
                    with patch("builtins.print") as mock_print:
                        jobs, db_summary = cli.run_google_careers_persist(args)

        self.assertIs(jobs, fake_jobs)
        self.assertEqual(db_summary, {"inserted": 2, "updated": 0})
        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], "google_careers")
        self.assertEqual(
            scrape_calls[0]["google_careers_url"],
            cli.DEFAULT_GOOGLE_CAREERS_URL,
        )
        self.assertEqual(scrape_calls[0]["results_wanted"], args.results)
        self.assertIsNone(scrape_calls[0]["description_limit"])
        self.assertEqual(scrape_calls[0]["verbose"], 0)
        self.assertEqual(len(populate_calls), 1)
        mock_print.assert_any_call("DB upsert summary: inserted=2 updated=0")


class MicrosoftCliTests(unittest.TestCase):
    def test_run_microsoft_persist_uses_microsoft_site_and_persists(self) -> None:
        args = cli.build_parser().parse_args(
            [
                "--microsoft-persist",
                "--output",
                "microsoft_jobs.json",
            ]
        )

        scrape_calls = []
        populate_calls = []

        class FakeJobs:
            empty = False

            def __len__(self) -> int:
                return 2

            @property
            def columns(self):
                return [
                    "title",
                    "company",
                    "location",
                    "date_posted",
                    "listing_type",
                    "is_remote",
                    "job_url",
                ]

            def __getitem__(self, key):
                return self

            def head(self, count):
                return self

            def to_string(self, index=False):
                return "fake microsoft persist preview"

        fake_jobs = FakeJobs()

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        def fake_save_jobs_to_json(output_path, jobs):
            self.assertEqual(jobs, fake_jobs)

        def fake_populate_jobs_table_from_file(output_path):
            populate_calls.append(output_path)
            return {"inserted": 2, "updated": 0}

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            with patch.object(cli, "save_jobs_to_json", side_effect=fake_save_jobs_to_json):
                with patch(
                    "jobspy.jobs_table.populate_jobs_table_from_file",
                    side_effect=fake_populate_jobs_table_from_file,
                ):
                    with patch("builtins.print") as mock_print:
                        jobs, db_summary = cli.run_microsoft_persist(args)

        self.assertIs(jobs, fake_jobs)
        self.assertEqual(db_summary, {"inserted": 2, "updated": 0})
        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], "microsoft")
        self.assertEqual(
            scrape_calls[0]["microsoft_base_url"],
            cli.DEFAULT_MICROSOFT_BASE_URL,
        )
        self.assertEqual(scrape_calls[0]["results_wanted"], args.results)
        self.assertIsNone(scrape_calls[0]["description_limit"])
        self.assertEqual(scrape_calls[0]["verbose"], 0)
        self.assertEqual(len(populate_calls), 1)
        mock_print.assert_any_call("DB upsert summary: inserted=2 updated=0")


class MarvellCliTests(unittest.TestCase):
    def test_run_marvell_israel_test_scrape_uses_workday_site(self) -> None:
        args = cli.build_parser().parse_args(["--marvell-israel-test-scrape"])
        scrape_calls = []

        class FakeJobs:
            empty = False

            def __len__(self) -> int:
                return 2

            @property
            def columns(self):
                return [
                    "title",
                    "company",
                    "location",
                    "date_posted",
                    "job_type",
                    "is_remote",
                    "job_url",
                ]

            def __getitem__(self, key):
                return self

            def head(self, count):
                return self

            def to_string(self, index=False):
                return "fake marvell preview"

            def to_json(self, orient="records", date_format="iso", force_ascii=False):
                return (
                    '[{"title":"Principal Hardware Board Design Engineer",'
                    '"company":"Marvell",'
                    '"location":"Yokneam, Israel",'
                    '"job_url":"https://marvell.wd1.myworkdayjobs.com/MarvellCareers/job/Yokneam/Principal-Hardware-System-Design-Engineer_2503821"}]'
                )

        fake_jobs = FakeJobs()

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            jobs, db_summary = cli.run_marvell_israel_test_scrape(args)

        self.assertIs(jobs, fake_jobs)
        self.assertIsNone(db_summary)
        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], "workday")
        self.assertEqual(
            scrape_calls[0]["workday_company_url"],
            cli.DEFAULT_MARVELL_BASE_URL,
        )
        self.assertEqual(scrape_calls[0]["results_wanted"], args.results)
        self.assertIsNone(scrape_calls[0]["description_limit"])
        self.assertEqual(scrape_calls[0]["verbose"], 2)
        self.assertTrue(scrape_calls[0]["workday_debug_trace"])

    def test_run_marvell_persist_uses_workday_site_and_persists(self) -> None:
        args = cli.build_parser().parse_args(
            [
                "--marvell-persist",
                "--output",
                "marvell_jobs.json",
            ]
        )

        scrape_calls = []
        populate_calls = []

        class FakeJobs:
            empty = False

            def __len__(self) -> int:
                return 2

            @property
            def columns(self):
                return [
                    "title",
                    "company",
                    "location",
                    "date_posted",
                    "job_type",
                    "is_remote",
                    "job_url",
                ]

            def __getitem__(self, key):
                return self

            def head(self, count):
                return self

            def to_string(self, index=False):
                return "fake marvell persist preview"

        fake_jobs = FakeJobs()

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        def fake_save_jobs_to_json(output_path, jobs):
            self.assertEqual(jobs, fake_jobs)

        def fake_populate_jobs_table_from_file(output_path):
            populate_calls.append(output_path)
            return {"inserted": 2, "updated": 0}

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            with patch.object(cli, "save_jobs_to_json", side_effect=fake_save_jobs_to_json):
                with patch(
                    "jobspy.jobs_table.populate_jobs_table_from_file",
                    side_effect=fake_populate_jobs_table_from_file,
                ):
                    with patch("builtins.print") as mock_print:
                        jobs, db_summary = cli.run_marvell_persist(args)

        self.assertIs(jobs, fake_jobs)
        self.assertEqual(db_summary, {"inserted": 2, "updated": 0})
        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], "workday")
        self.assertEqual(
            scrape_calls[0]["workday_company_url"],
            cli.DEFAULT_MARVELL_BASE_URL,
        )
        self.assertEqual(scrape_calls[0]["results_wanted"], args.results)
        self.assertIsNone(scrape_calls[0]["description_limit"])
        self.assertEqual(scrape_calls[0]["verbose"], 0)
        self.assertFalse(scrape_calls[0]["workday_debug_trace"])
        self.assertEqual(len(populate_calls), 1)
        mock_print.assert_any_call("DB upsert summary: inserted=2 updated=0")


class RedHatCliTests(unittest.TestCase):
    def test_run_redhat_test_scrape_uses_redhat_site_without_persistence(self) -> None:
        args = cli.build_parser().parse_args(["--redhat-test-scrape"])
        scrape_calls = []

        class FakeJobs:
            empty = False

            def __len__(self) -> int:
                return 1

            @property
            def columns(self):
                return [
                    "title",
                    "company",
                    "location",
                    "date_posted",
                    "job_type",
                    "is_remote",
                    "job_url",
                ]

            def __getitem__(self, key):
                return self

            def head(self, count):
                return self

            def to_string(self, index=False):
                return "fake redhat preview"

            def to_json(self, orient="records", date_format="iso", force_ascii=False):
                return (
                    '[{"title":"Senior Software Engineer","company":"Red Hat",'
                    '"location":"Raanana, Israel",'
                    '"job_url":"https://redhat.wd5.myworkdayjobs.com/job/Raanana/job-1"}]'
                )

        fake_jobs = FakeJobs()

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            jobs, db_summary = cli.run_redhat_test_scrape(args)

        self.assertIs(jobs, fake_jobs)
        self.assertIsNone(db_summary)
        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], "redhat")
        self.assertEqual(
            scrape_calls[0]["redhat_base_url"],
            cli.DEFAULT_REDHAT_BASE_URL,
        )
        self.assertEqual(scrape_calls[0]["results_wanted"], 1)
        self.assertEqual(scrape_calls[0]["description_limit"], 1)
        self.assertEqual(scrape_calls[0]["verbose"], 2)
        self.assertTrue(scrape_calls[0]["redhat_debug_trace"])

    def test_run_redhat_persist_uses_redhat_site_and_persists_all(self) -> None:
        args = cli.build_parser().parse_args(
            [
                "--redhat-persist",
                "--output",
                "redhat_jobs.json",
            ]
        )

        scrape_calls = []
        populate_calls = []

        class FakeJobs:
            empty = False

            def __len__(self) -> int:
                return 4

            @property
            def columns(self):
                return [
                    "title",
                    "company",
                    "location",
                    "date_posted",
                    "job_type",
                    "is_remote",
                    "job_url",
                ]

            def __getitem__(self, key):
                return self

            def head(self, count):
                return self

            def to_string(self, index=False):
                return "fake redhat persist preview"

        fake_jobs = FakeJobs()

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        def fake_save_jobs_to_json(output_path, jobs):
            self.assertEqual(jobs, fake_jobs)

        def fake_populate_jobs_table_from_file(output_path):
            populate_calls.append(output_path)
            return {"inserted": 4, "updated": 0}

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            with patch.object(cli, "save_jobs_to_json", side_effect=fake_save_jobs_to_json):
                with patch(
                    "jobspy.jobs_table.populate_jobs_table_from_file",
                    side_effect=fake_populate_jobs_table_from_file,
                ):
                    with patch.object(cli, "_print_console_safe") as mock_preview:
                        with patch("builtins.print") as mock_print:
                            jobs, db_summary = cli.run_redhat_persist(args)

        self.assertIs(jobs, fake_jobs)
        self.assertEqual(db_summary, {"inserted": 4, "updated": 0})
        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], "redhat")
        self.assertEqual(
            scrape_calls[0]["redhat_base_url"],
            cli.DEFAULT_REDHAT_BASE_URL,
        )
        self.assertEqual(scrape_calls[0]["results_wanted"], 0)
        self.assertIsNone(scrape_calls[0]["description_limit"])
        self.assertEqual(scrape_calls[0]["verbose"], 0)
        self.assertFalse(scrape_calls[0]["redhat_debug_trace"])
        self.assertEqual(len(populate_calls), 1)
        mock_preview.assert_not_called()
        mock_print.assert_any_call("DB upsert summary: inserted=4 updated=0")


class VaronisCliTests(unittest.TestCase):
    def test_run_varonis_test_scrape_uses_varonis_site_without_persistence(self) -> None:
        args = cli.build_parser().parse_args(["--varonis-test-scrape"])
        scrape_calls = []

        class FakeJobs:
            empty = False

            def __len__(self) -> int:
                return 1

            @property
            def columns(self):
                return [
                    "title",
                    "company",
                    "location",
                    "job_function",
                    "listing_type",
                    "job_url",
                    "apply_url",
                    "description",
                ]

            def __getitem__(self, key):
                return self

            def head(self, count):
                return self

            def to_string(self, index=False):
                return "fake varonis preview"

            def to_json(self, orient="records", date_format="iso", force_ascii=False):
                return (
                    '[{"title":"Low Level Engineer","company":"Varonis",'
                    '"location":"Herzliya, Israel",'
                    '"job_url":"https://jobs.jobvite.com/careers/varonis/job/1"}]'
                )

        fake_jobs = FakeJobs()

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            jobs, db_summary = cli.run_varonis_test_scrape(args)

        self.assertIs(jobs, fake_jobs)
        self.assertIsNone(db_summary)
        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], "varonis")
        self.assertEqual(
            scrape_calls[0]["varonis_base_url"],
            cli.DEFAULT_VARONIS_BASE_URL,
        )
        self.assertEqual(scrape_calls[0]["results_wanted"], 1)
        self.assertEqual(scrape_calls[0]["description_limit"], 1)
        self.assertEqual(scrape_calls[0]["verbose"], 2)
        self.assertTrue(scrape_calls[0]["varonis_debug_trace"])

    def test_run_varonis_persist_uses_varonis_site_and_persists(self) -> None:
        args = cli.build_parser().parse_args(
            [
                "--varonis-persist",
                "--output",
                "varonis_jobs.json",
            ]
        )

        scrape_calls = []
        populate_calls = []

        class FakeJobs:
            empty = False

            def __len__(self) -> int:
                return 2

            @property
            def columns(self):
                return [
                    "title",
                    "company",
                    "location",
                    "job_function",
                    "listing_type",
                    "job_url",
                ]

            def __getitem__(self, key):
                return self

            def head(self, count):
                return self

            def to_string(self, index=False):
                return "fake varonis persist preview"

        fake_jobs = FakeJobs()

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        def fake_save_jobs_to_json(output_path, jobs):
            self.assertEqual(jobs, fake_jobs)

        def fake_populate_jobs_table_from_file(output_path):
            populate_calls.append(output_path)
            return {"inserted": 2, "updated": 0}

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            with patch.object(
                cli,
                "save_jobs_to_json",
                side_effect=fake_save_jobs_to_json,
            ):
                with patch(
                    "jobspy.jobs_table.populate_jobs_table_from_file",
                    side_effect=fake_populate_jobs_table_from_file,
                ):
                    with patch("builtins.print") as mock_print:
                        jobs, db_summary = cli.run_varonis_persist(args)

        self.assertIs(jobs, fake_jobs)
        self.assertEqual(db_summary, {"inserted": 2, "updated": 0})
        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["site_name"], "varonis")
        self.assertEqual(
            scrape_calls[0]["varonis_base_url"],
            cli.DEFAULT_VARONIS_BASE_URL,
        )
        self.assertEqual(scrape_calls[0]["results_wanted"], 0)
        self.assertIsNone(scrape_calls[0]["description_limit"])
        self.assertEqual(scrape_calls[0]["verbose"], 0)
        self.assertFalse(scrape_calls[0]["varonis_debug_trace"])
        self.assertEqual(len(populate_calls), 1)
        mock_print.assert_any_call("DB upsert summary: inserted=2 updated=0")


class GlassdoorCliTests(unittest.TestCase):
    def test_country_supports_glassdoor_for_israel(self) -> None:
        self.assertEqual(
            Country.from_string("Israel").get_glassdoor_url(),
            "https://www.glassdoor.com/",
        )
        self.assertTrue(cli._country_supports_glassdoor("Israel"))

    def test_run_glassdoor_debug_search_defaults_to_israel_without_keyword(self) -> None:
        args = cli.build_parser().parse_args(["--glassdoor-debug-search"])
        scrape_calls = []

        class FakeJobs:
            empty = False

            def __len__(self) -> int:
                return 1

            @property
            def columns(self):
                return [
                    "title",
                    "company",
                    "location",
                    "date_posted",
                    "job_url",
                    "description",
                ]

            def __getitem__(self, key):
                return self

            def to_string(self, index=False):
                return "fake glassdoor preview"

            def head(self, count):
                return self

            def to_json(self, orient="records", date_format="iso", force_ascii=False):
                return (
                    '[{"title":"Software Engineer","company":"Acme",'
                    '"location":"Tel Aviv","job_url":"https://example.com/job/1"}]'
                )

        fake_jobs = FakeJobs()

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            with patch("builtins.print"):
                jobs, db_summary = cli.run_glassdoor_debug_search(args)

        self.assertIs(jobs, fake_jobs)
        self.assertIsNone(db_summary)
        self.assertEqual(len(scrape_calls), 1)
        self.assertIsNone(scrape_calls[0]["search_term"])
        self.assertEqual(scrape_calls[0]["location"], "Israel")
        self.assertEqual(scrape_calls[0]["country_indeed"], "Israel")
        self.assertEqual(
            scrape_calls[0]["hours_old"],
            cli.DEFAULT_GLASSDOOR_FROM_AGE_DAYS * 24,
        )
        self.assertEqual(scrape_calls[0]["results_wanted"], 1)
        self.assertEqual(scrape_calls[0]["description_limit"], 1)
        self.assertEqual(scrape_calls[0]["verbose"], 2)

    def test_run_glassdoor_persist_uses_last_three_days_and_persists(self) -> None:
        args = cli.build_parser().parse_args(
            [
                "--glassdoor-persist",
                "--output",
                "glassdoor_jobs.json",
            ]
        )

        scrape_calls = []
        populate_calls = []

        class FakeJobs:
            empty = False

            def __len__(self) -> int:
                return 2

            @property
            def columns(self):
                return [
                    "title",
                    "company",
                    "location",
                    "date_posted",
                    "job_url",
                    "job_type",
                    "is_remote",
                ]

            def __getitem__(self, key):
                return self

            def head(self, count):
                return self

            def to_string(self, index=False):
                return "fake glassdoor preview"

        fake_jobs = FakeJobs()

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        def fake_save_jobs_to_json(output_path, jobs):
            self.assertEqual(jobs, fake_jobs)

        def fake_populate_jobs_table_from_file(output_path):
            populate_calls.append(output_path)
            return {"inserted": 2, "updated": 0}

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            with patch.object(cli, "save_jobs_to_json", side_effect=fake_save_jobs_to_json):
                with patch(
                    "jobspy.jobs_table.populate_jobs_table_from_file",
                    side_effect=fake_populate_jobs_table_from_file,
                ):
                    with patch("builtins.print") as mock_print:
                        jobs, db_summary = cli.run_glassdoor_persist(args)

        self.assertIs(jobs, fake_jobs)
        self.assertEqual(db_summary, {"inserted": 2, "updated": 0})
        self.assertEqual(len(scrape_calls), 1)
        self.assertIsNone(scrape_calls[0]["search_term"])
        self.assertEqual(scrape_calls[0]["location"], "Israel")
        self.assertEqual(scrape_calls[0]["country_indeed"], "Israel")
        self.assertEqual(
            scrape_calls[0]["hours_old"],
            cli.DEFAULT_GLASSDOOR_FROM_AGE_DAYS * 24,
        )
        self.assertEqual(scrape_calls[0]["results_wanted"], 1000)
        self.assertIsNone(scrape_calls[0]["description_limit"])
        self.assertEqual(scrape_calls[0]["verbose"], 2)
        self.assertEqual(len(populate_calls), 1)
        mock_print.assert_any_call("DB upsert summary: inserted=2 updated=0")

    def test_run_glassdoor_persist_one_limits_results_to_one(self) -> None:
        args = cli.build_parser().parse_args(
            ["--glassdoor-persist-one", "--no-save-db"]
        )
        scrape_calls = []

        class FakeJobs:
            empty = True

            def __len__(self) -> int:
                return 1

        fake_jobs = FakeJobs()

        def fake_scrape_jobs(**kwargs):
            scrape_calls.append(kwargs)
            return fake_jobs

        with patch.object(cli, "scrape_jobs", side_effect=fake_scrape_jobs):
            with patch.object(cli, "save_jobs_to_json"):
                jobs, db_summary = cli.run_glassdoor_persist(args, results_wanted=1)

        self.assertIs(jobs, fake_jobs)
        self.assertIsNone(db_summary)
        self.assertEqual(len(scrape_calls), 1)
        self.assertEqual(scrape_calls[0]["results_wanted"], 1)


if __name__ == "__main__":
    unittest.main()
