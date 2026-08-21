from pathlib import Path

from agentscope.analytics.filters import AnalyticsFilter
from agentscope.extension.snapshot import build_extension_snapshot
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


def test_extension_snapshot_exposes_last_successful_collection(tmp_path: Path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO import_state(
                source, path, size, last_imported_at, status
            ) VALUES('codex', 'artifact-a', 123, '2026-08-19 16:25:00', 'complete')
            """
        )
        conn.execute(
            """
            INSERT INTO import_state(
                source, path, size, last_imported_at, status
            ) VALUES('kimi', 'artifact-b', 456, '2026-08-19 16:30:00', 'complete')
            """
        )

    snapshot = build_extension_snapshot(
        Repository(db),
        AnalyticsFilter(),
        period=None,
        database_path=db.path,
    )

    assert snapshot["freshness"] == {
        "last_imported_at": "2026-08-19 16:30:00",
        "artifacts_tracked": 2,
    }


def test_extension_snapshot_freshness_is_null_before_first_collection(tmp_path: Path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()

    snapshot = build_extension_snapshot(
        Repository(db),
        AnalyticsFilter(),
        period=None,
        database_path=db.path,
    )

    assert snapshot["freshness"] == {
        "last_imported_at": None,
        "artifacts_tracked": 0,
    }
