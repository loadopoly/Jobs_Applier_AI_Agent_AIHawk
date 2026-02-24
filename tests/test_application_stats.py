import json

from src.application_stats import ApplicationStatsService


def test_application_stats_empty_directory(tmp_path):
    stats = ApplicationStatsService(tmp_path / "job_applications").summarize()

    assert stats.total_jobs == 0
    assert stats.successes == 0
    assert stats.failures == 0
    assert stats.unknown == 0


def test_application_stats_counts_statuses(tmp_path):
    applications_dir = tmp_path / "job_applications"
    applications_dir.mkdir()

    success_dir = applications_dir / "1 - ACME Engineer"
    success_dir.mkdir()
    (success_dir / "job_application.json").write_text(
        json.dumps({"status": "applied"}),
        encoding="utf-8",
    )

    fail_dir = applications_dir / "2 - Beta Engineer"
    fail_dir.mkdir()
    (fail_dir / "job_application.json").write_text(
        json.dumps({"status": "failed"}),
        encoding="utf-8",
    )

    unknown_dir = applications_dir / "3 - Gamma Engineer"
    unknown_dir.mkdir()
    (unknown_dir / "job_application.json").write_text(
        json.dumps({"status": "pending review"}),
        encoding="utf-8",
    )

    stats = ApplicationStatsService(applications_dir).summarize()

    assert stats.total_jobs == 3
    assert stats.successes == 1
    assert stats.failures == 1
    assert stats.unknown == 1
