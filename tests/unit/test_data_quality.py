from agentscope.analytics.service import AnalyticsService
from agentscope.storage.database import Database
from agentscope.storage.repository import Repository


def test_data_quality_exposes_unknown_and_evidence_metrics(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)

    with db.connect() as conn:
        conn.execute(
            "INSERT INTO sources(name, type) VALUES('codex', 'agent-runtime')"
        )
        source_id = conn.execute(
            "SELECT id FROM sources WHERE name='codex'"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO models(provider, name) VALUES('openai', 'gpt-5.6-terra')"
        )
        model_id = conn.execute(
            "SELECT id FROM models WHERE name='gpt-5.6-terra'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(source_id, external_session_id, started_at, model_id)
            VALUES(?, 'known-session', '2026-08-18T10:00:00Z', ?)
            """,
            (source_id, model_id),
        )
        conn.execute(
            """
            INSERT INTO sessions(source_id, external_session_id, started_at)
            VALUES(?, 'unknown-session', '2026-08-18T11:00:00Z')
            """,
            (source_id,),
        )
        known_session = conn.execute(
            "SELECT id FROM sessions WHERE external_session_id='known-session'"
        ).fetchone()[0]
        unknown_session = conn.execute(
            "SELECT id FROM sessions WHERE external_session_id='unknown-session'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, model_id, input_tokens, event_key
            ) VALUES(?, '2026-08-18T10:01:00Z', ?, 100, 'known-token')
            """,
            (known_session, model_id),
        )
        conn.execute(
            """
            INSERT INTO token_usage(session_id, timestamp, input_tokens, event_key)
            VALUES(?, '2026-08-18T11:01:00Z', 50, 'unknown-token')
            """,
            (unknown_session,),
        )
        conn.execute(
            "INSERT INTO optimizers(name) VALUES('headroom')"
        )
        optimizer_id = conn.execute(
            "SELECT id FROM optimizers WHERE name='headroom'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO optimizations(
                optimizer_id, session_id, timestamp, correlation_confidence, event_key
            ) VALUES(?, ?, '2026-08-18T10:02:00Z', 'exact', 'optimization-exact')
            """,
            (optimizer_id, known_session),
        )
        conn.execute(
            """
            INSERT INTO optimizations(
                optimizer_id, timestamp, correlation_confidence, event_key
            ) VALUES(?, '2026-08-18T11:02:00Z', 'unknown', 'optimization-unknown')
            """,
            (optimizer_id,),
        )
        conn.execute(
            "INSERT INTO agents(name, type) VALUES('reviewer', 'subagent')"
        )
        agent_id = conn.execute(
            "SELECT id FROM agents WHERE name='reviewer'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO session_agents(session_id, agent_id, evidence_type)
            VALUES(?, ?, 'spawn_agent')
            """,
            (known_session, agent_id),
        )
        conn.execute(
            """
            INSERT INTO skills(name, source, version)
            VALUES('superpowers:brainstorming', 'codex', '')
            """
        )
        skill_id = conn.execute(
            "SELECT id FROM skills WHERE name='superpowers:brainstorming'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO session_skills(
                session_id, skill_id, usage_type, evidence_type
            ) VALUES(?, ?, 'invoked', 'assistant_announcement')
            """,
            (known_session, skill_id),
        )
        conn.execute(
            """
            INSERT INTO import_errors(source, file, error_type, error_message)
            VALUES('codex', 'broken.jsonl', 'JSONDecodeError', 'invalid json')
            """
        )

    quality = AnalyticsService(repo).data_quality()

    assert quality["import_errors"] == 1
    assert quality["unknown_model_sessions"] == 1
    assert round(quality["unknown_model_token_share"], 4) == round(50 / 150, 4)
    assert quality["optimization_confidence"] == {"exact": 1, "unknown": 1}
    assert quality["skill_evidence_rows"] == 1
    assert quality["agent_evidence_rows"] == 1


def test_unknown_model_share_is_unavailable_without_token_denominator(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)

    quality = AnalyticsService(repo).data_quality()

    assert quality["unknown_model_token_share"] is None
