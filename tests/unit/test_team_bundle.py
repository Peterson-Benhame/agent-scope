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
