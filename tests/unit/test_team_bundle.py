import json

from agentscope.storage.database import Database
from agentscope.storage.repository import Repository
from agentscope.team.bundle import (
    TEAM_BUNDLE_SCHEMA,
    TEAM_BUNDLE_VERSION,
    build_team_bundle,
    canonical_bundle_payload,
    compute_bundle_id,
)


def empty_repo(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    return Repository(db)


def populated_repo(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    repo = Repository(db)
    with db.connect() as conn:
        conn.execute("INSERT INTO sources(name, type) VALUES('codex', 'agent')")
        source_id = conn.execute("SELECT id FROM sources WHERE name='codex'").fetchone()[0]
        conn.execute(
            "INSERT INTO projects(name, path) VALUES('demo', 'C:\\work\\demo')"
        )
        project_id = conn.execute("SELECT id FROM projects WHERE name='demo'").fetchone()[0]
        conn.execute("INSERT INTO models(provider, name) VALUES('openai', 'gpt-5.6-terra')")
        model_id = conn.execute("SELECT id FROM models WHERE name='gpt-5.6-terra'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO users(stable_key, display_name, provider, identity_confidence)
            VALUES('user-key-a', 'Dev A', 'local', 'inferred')
            """
        )
        user_id = conn.execute("SELECT id FROM users WHERE stable_key='user-key-a'").fetchone()[0]
        conn.execute(
            "INSERT INTO machines(stable_key, display_name, os) VALUES('machine-key-a', 'Notebook A', 'Windows')"
        )
        machine_id = conn.execute(
            "SELECT id FROM machines WHERE stable_key='machine-key-a'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO sessions(
                source_id, external_session_id, project_id, started_at, ended_at,
                provider, model_id, raw_file_path, metadata_json, user_id, machine_id
            ) VALUES(
                ?, 'session-a', ?, '2026-08-18T10:00:00Z', '2026-08-18T10:05:00Z',
                'openai', ?, 'C:\\work\\demo\\raw.jsonl',
                '{"secret":"ENV_SECRET"}', ?, ?
            )
            """,
            (source_id, project_id, model_id, user_id, machine_id),
        )
        session_id = conn.execute(
            "SELECT id FROM sessions WHERE external_session_id='session-a'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO messages(
                session_id, role, timestamp, content, metadata_json, event_key
            ) VALUES(
                ?, 'user', '2026-08-18T10:00:01Z',
                'PROMPT_SECRET SOURCE_CODE_SECRET', '{}', 'message-local-a'
            )
            """,
            (session_id,),
        )
        conn.execute(
            """
            INSERT INTO token_usage(
                session_id, timestamp, model_id, input_tokens, cached_input_tokens,
                output_tokens, total_tokens, event_key
            ) VALUES(
                ?, '2026-08-18T10:00:02Z', ?, 1000, 800, 200, 1200, 'token-local-a'
            )
            """,
            (session_id, model_id),
        )
        conn.execute("INSERT INTO tools(name, provider, category) VALUES('Read', 'codex', 'tool')")
        tool_id = conn.execute("SELECT id FROM tools WHERE name='Read'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO tool_calls(
                session_id, tool_id, external_call_id, timestamp, status,
                input_size, output_size, metadata_json, event_key
            ) VALUES(
                ?, ?, 'call-a', '2026-08-18T10:00:03Z', 'success',
                123, 45, '{"payload":"TOOL_PAYLOAD_SECRET"}', 'tool-local-a'
            )
            """,
            (session_id, tool_id),
        )
        conn.execute(
            """
            INSERT INTO costs(
                session_id, model_id, period_start, observed_cost_usd,
                total_savings_usd, pricing_source, event_key
            ) VALUES(
                ?, ?, '2026-08-18T10:00:00Z', 0.12, 0.03,
                'source-reported', 'cost-local-a'
            )
            """,
            (session_id, model_id),
        )
        conn.execute("INSERT INTO agents(name, type) VALUES('reviewer', 'subagent')")
        agent_id = conn.execute("SELECT id FROM agents WHERE name='reviewer'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO session_agents(session_id, agent_id, evidence_type)
            VALUES(?, ?, 'spawn_agent')
            """,
            (session_id, agent_id),
        )
        conn.execute("INSERT INTO optimizers(name, version) VALUES('headroom', '0.35.0')")
        optimizer_id = conn.execute("SELECT id FROM optimizers WHERE name='headroom'").fetchone()[0]
        conn.execute(
            """
            INSERT INTO optimizations(
                optimizer_id, session_id, timestamp, model_id,
                original_tokens, optimized_tokens, tokens_saved,
                compression_savings_usd, cache_savings_usd,
                correlation_confidence, metadata_json, event_key
            ) VALUES(
                ?, ?, '2026-08-18T10:00:04Z', ?, 1000, 900, 100,
                0.01, 0.02, 'high', '{"secret":"ENV_SECRET"}', 'opt-local-a'
            )
            """,
            (optimizer_id, session_id, model_id),
        )
    return repo


def test_team_bundle_has_versioned_envelope_and_stable_id(tmp_path):
    repo = empty_repo(tmp_path)

    first = build_team_bundle(repo, organization="Org", team="Backend")
    second = build_team_bundle(repo, organization="Org", team="Backend")

    assert TEAM_BUNDLE_SCHEMA == "agentscope-team-bundle"
    assert TEAM_BUNDLE_VERSION == 1
    assert first["schema"] == TEAM_BUNDLE_SCHEMA
    assert first["version"] == TEAM_BUNDLE_VERSION
    assert first["organization"] == "Org"
    assert first["team"] == "Backend"
    assert isinstance(first["records"], dict)
    assert first["bundle_id"] == second["bundle_id"]
    assert first["bundle_id"] == compute_bundle_id(canonical_bundle_payload(first))


def test_canonical_payload_ignores_generated_at_and_bundle_id_only(tmp_path):
    repo = empty_repo(tmp_path)
    bundle = build_team_bundle(repo)

    changed_ephemeral = dict(bundle)
    changed_ephemeral["generated_at"] = "2099-01-01T00:00:00Z"
    changed_ephemeral["bundle_id"] = "different"
    assert canonical_bundle_payload(bundle) == canonical_bundle_payload(changed_ephemeral)

    changed_data = dict(bundle)
    changed_data["team"] = "Different"
    assert canonical_bundle_payload(bundle) != canonical_bundle_payload(changed_data)


def test_team_bundle_exports_only_allow_listed_safe_metadata(tmp_path):
    bundle = build_team_bundle(populated_repo(tmp_path))
    serialized = json.dumps(bundle, ensure_ascii=False, sort_keys=True)
    normalized_serialized = serialized.replace("\\\\", "\\")

    for sentinel in [
        "PROMPT_SECRET",
        "SOURCE_CODE_SECRET",
        "TOOL_PAYLOAD_SECRET",
        "ENV_SECRET",
    ]:
        assert sentinel not in serialized
    assert r"C:\work\demo" not in normalized_serialized

    records = bundle["records"]
    assert records["users"][0]["stable_key"] == "user-key-a"
    assert records["machines"][0]["stable_key"] == "machine-key-a"
    assert records["sessions"][0]["project"] == "demo"
    assert records["sessions"][0]["source"] == "codex"
    assert records["token_usage"][0]["input_tokens"] == 1000
    assert records["costs"][0]["observed_cost_usd"] == 0.12
    assert records["tool_calls"][0]["tool"] == "Read"
    assert records["agents"][0]["agent"] == "reviewer"
    assert records["optimizations"][0]["optimizer"] == "headroom"

    event_keys = {
        records["token_usage"][0]["event_key"],
        records["costs"][0]["event_key"],
        records["tool_calls"][0]["event_key"],
        records["optimizations"][0]["event_key"],
    }
    assert len(event_keys) == 4
    assert "token-local-a" not in event_keys
