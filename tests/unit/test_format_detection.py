from agentscope.sources.format_detection import require_known_version


def test_supported_version_is_accepted():
    result = require_known_version("1", {"1"}, "claude_code")

    assert result.supported is True
    assert result.version == "1"
    assert result.diagnostic is None


def test_missing_version_is_rejected():
    result = require_known_version(None, {"1"}, "claude_code")

    assert result.supported is False
    assert result.version is None
    assert result.diagnostic == "claude_code missing format version"


def test_unknown_version_is_rejected_with_deterministic_diagnostic():
    result = require_known_version("9", {"1"}, "claude_code")

    assert result.supported is False
    assert result.version == "9"
    assert result.diagnostic == "claude_code unsupported format version: 9"
