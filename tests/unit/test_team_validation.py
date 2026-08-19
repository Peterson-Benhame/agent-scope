import copy

import pytest

from agentscope.storage.database import Database
from agentscope.storage.repository import Repository
from agentscope.team.bundle import build_team_bundle
from agentscope.team.validation import TeamBundleValidationError, validate_team_bundle


def valid_bundle(tmp_path):
    db = Database(tmp_path / "agentscope.db")
    db.initialize()
    return build_team_bundle(Repository(db))


def test_accepts_valid_empty_bundle(tmp_path):
    validate_team_bundle(valid_bundle(tmp_path))


def test_rejects_wrong_schema_and_unsupported_version(tmp_path):
    bundle = valid_bundle(tmp_path)
    wrong_schema = copy.deepcopy(bundle)
    wrong_schema["schema"] = "other"
    wrong_version = copy.deepcopy(bundle)
    wrong_version["version"] = 99

    with pytest.raises(TeamBundleValidationError, match="schema"):
        validate_team_bundle(wrong_schema)
    with pytest.raises(TeamBundleValidationError, match="version"):
        validate_team_bundle(wrong_version)


def test_rejects_missing_stable_user_or_machine_key(tmp_path):
    bundle = valid_bundle(tmp_path)
    bundle["records"]["users"] = [{"stable_key": "", "display_name": "Dev"}]

    with pytest.raises(TeamBundleValidationError, match="stable_key"):
        validate_team_bundle(bundle)

    bundle = valid_bundle(tmp_path)
    bundle["records"]["machines"] = [{"display_name": "Notebook"}]
    with pytest.raises(TeamBundleValidationError, match="stable_key"):
        validate_team_bundle(bundle)


def test_rejects_malformed_numeric_metrics(tmp_path):
    bundle = valid_bundle(tmp_path)
    bundle["records"]["token_usage"] = [
        {
            "event_key": "token-key",
            "session_key": "session-key",
            "timestamp": "2026-08-18T10:00:00Z",
            "input_tokens": "1000",
        }
    ]

    with pytest.raises(TeamBundleValidationError, match="input_tokens"):
        validate_team_bundle(bundle)


def test_rejects_forbidden_content_or_payload_fields_anywhere(tmp_path):
    for forbidden in ["content", "messages", "payload", "raw_file_path"]:
        bundle = valid_bundle(tmp_path)
        bundle["records"]["sessions"] = [
            {
                "session_key": "session-key",
                "external_session_id": "s1",
                "source": "codex",
                forbidden: "SECRET",
            }
        ]
        with pytest.raises(TeamBundleValidationError, match=forbidden):
            validate_team_bundle(bundle)


def test_rejects_unknown_top_level_field_even_when_name_is_not_forbidden(tmp_path):
    bundle = valid_bundle(tmp_path)
    bundle["secret_data"] = "SHOULD_NOT_TRAVEL"

    with pytest.raises(TeamBundleValidationError, match="unexpected field"):
        validate_team_bundle(bundle)


def test_rejects_unknown_record_field_even_when_name_is_not_forbidden(tmp_path):
    bundle = valid_bundle(tmp_path)
    bundle["records"]["sessions"] = [
        {
            "session_key": "session-key",
            "external_session_id": "s1",
            "source": "codex",
            "custom_private_data": "SHOULD_NOT_TRAVEL",
        }
    ]

    with pytest.raises(TeamBundleValidationError, match="unexpected field"):
        validate_team_bundle(bundle)


def test_rejects_tampered_bundle_id(tmp_path):
    bundle = valid_bundle(tmp_path)
    bundle["bundle_id"] = "0" * 64

    with pytest.raises(TeamBundleValidationError, match="bundle_id"):
        validate_team_bundle(bundle)
