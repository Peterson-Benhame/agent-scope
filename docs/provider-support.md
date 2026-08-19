# AgentScope provider support

AgentScope uses explicit source adapters. Each adapter reads provider-owned local files in read-only mode and only advertises capabilities backed by a verified local format. Missing information remains unavailable/NULL; it is never guessed as zero.

## Current adapters

| Source | Default local data | Sessions | Messages | Tokens | Cache | Tools | Agents | Skills | Costs | Optimizations |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Codex | `~/.codex/sessions/**/rollout-*.jsonl` | yes | yes | yes | yes | yes | explicit evidence | explicit evidence | no | no |
| Headroom | `~/.headroom/proxy_savings.json`, `~/.headroom/*.jsonl` | no | no | optimizer metrics | yes | no | no | no | source-reported | yes |
| Claude Code | `~/.claude/projects/*/*.jsonl` | yes | yes | yes | yes | yes | no | no | no | no |
| GitHub Copilot CLI | `~/.copilot/session-state/*/events.jsonl` | yes | yes | yes | yes | yes | no | no | no | no |
| Kimi Code | `~/.kimi-code/session_index.jsonl` + referenced `state.json` | yes | no | no | no | no | no | no | no | no |
| Gemini CLI | `~/.gemini/tmp/*/chats/session-*.jsonl` | yes | yes | yes | yes | yes | no | no | no | no |

`yes` means the adapter can provide that field when the supported source record contains it. It does not mean every session contains the value.

## Format contracts

### Codex

The Codex adapter keeps the V1 rollout parser semantics and reads explicit `session_meta`, turn context, message, tool-call, token-count, agent and skill evidence. Encrypted reasoning is counted as opaque evidence only; AgentScope does not decrypt it.

### Headroom

Headroom remains an **Optimizer**, not an Agent. Lifetime snapshot metrics use replacement/upsert semantics instead of cumulative append semantics. Per-event optimizer data preserves correlation confidence.

### Claude Code

The current adapter accepts the verified JSONL transcript fingerprint used by the synthetic fixture: records with explicit `sessionId`, `user`/`assistant` type and `message` objects. Model, token/cache and tool-use data are read only from explicit assistant-message fields. Unknown transcript structures are reported as unsupported rather than parsed heuristically.

Claude cache-read and cache-creation tokens are kept as separate normalized cache fields. For cross-provider analytics, normalized input tokens include the provider's base input plus explicit cache-read/cache-write input components.

### GitHub Copilot CLI

The current adapter reads the versioned `events.jsonl` session-state history. It imports explicit session/message/model/usage/tool data. Copilot credit/multiplier-style cost fields are **not USD billing amounts** and are not written to `observed_cost_usd`.

### Kimi Code

The current Kimi adapter intentionally supports only the documented session index and `state.json` metadata needed to identify session ID, work directory and timestamps.

AgentScope does **not** parse `wire.jsonl` in this version because a stable wire-event schema was not adopted for this adapter. `lastPrompt` is also not imported. Therefore Kimi token/model/tool values remain unavailable rather than inferred from unverified records.

### Gemini CLI

The current Gemini adapter reads the current JSONL conversation record: metadata contains `sessionId`, `projectHash`, `startTime`/`lastUpdated`; user/Gemini message records can contain explicit `model`, `tokens` and `toolCalls`. Legacy session formats are not guessed by this adapter.

## Configuration

All registered adapters are enabled by default. Restrict collection with `AGENTSCOPE_SOURCES`:

```powershell
$env:AGENTSCOPE_SOURCES = "codex,claude_code,github_copilot"
agentscope collect
```

Supported source names:

```text
codex
headroom
claude_code
github_copilot
kimi
gemini
```

Provider root overrides:

```text
AGENTSCOPE_CODEX_HOME
AGENTSCOPE_HEADROOM_HOME
AGENTSCOPE_CLAUDE_HOME
AGENTSCOPE_COPILOT_HOME
AGENTSCOPE_KIMI_HOME
AGENTSCOPE_GEMINI_HOME
```

`COPILOT_HOME` is also honored as the provider-native Copilot root fallback. `KIMI_CODE_HOME` is honored as the provider-native Kimi root fallback.

## Unsupported or changed formats

If a source exists but the adapter cannot verify its local structure, discovery returns a diagnostic and does not ingest the records. `agentscope status` and `agentscope collect` surface these diagnostics. A supported source failing during collection is isolated from other adapters and produces an import error without rolling back successful imports from unrelated providers.

## Privacy

Provider adapters may persist normalized message content in the local SQLite database because local analytics can reconstruct source histories. The database must therefore be treated as sensitive.

Safe reports/exports exclude full message bodies and tool payloads by default. The later Team Bundle layer is stricter: it uses an allow-list and must never export prompts, responses, source code, tool payloads, raw provider files, environment variables or secrets.
