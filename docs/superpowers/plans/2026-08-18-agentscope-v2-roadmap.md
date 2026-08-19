# AgentScope V2 Implementation Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved AgentScope V2 multi-source/team-analytics architecture through ordered, independently verifiable increments.

**Architecture:** Implement A–G in dependency order. Each increment has its own plan, test cycle, commits, and review gate. Later increments consume stable interfaces from earlier ones rather than bypassing them.

**Tech Stack:** Python 3.11+, Typer, SQLite, pytest, standard-library JSON/CSV/HTML.

**Spec:** `docs/superpowers/specs/2026-08-18-multi-source-team-analytics-design.md`

## Global Constraints

- Local-first and read-only provider sources.
- Unknown monetary/capability data remains unavailable/NULL.
- Safe metadata reporting by default.
- No central server/API in this phase.
- TDD for every increment.
- Existing V1 databases and Codex/Headroom semantics remain compatible.
- Fresh `python -m pytest -q` verification before each increment is claimed complete.

---

## Ordered execution

- [ ] **Increment A — Analytics/report foundation**
  - Plan: `docs/superpowers/plans/2026-08-18-analytics-report-v2.md`
  - Delivers shared filters, date aliases, pt-BR formatting, comparison, CLI/report/export filtering.

- [ ] **Increment B — Data quality hardening**
  - Plan: `docs/superpowers/plans/2026-08-18-data-quality-hardening.md`
  - Delivers skill/model/agent false-positive correction and quality metrics.

- [ ] **Increment C — Source adapter framework**
  - Plan: `docs/superpowers/plans/2026-08-18-source-adapter-framework.md`
  - Delivers `SourceAdapter`, capabilities, registry, Codex/Headroom migration, provider-neutral progress.

- [ ] **Increment D — User/machine identity**
  - Plan: `docs/superpowers/plans/2026-08-18-user-machine-identity.md`
  - Delivers additive DB migration, stable identity/confidence, session association, analytics dimensions.

- [ ] **Increment E — New provider adapters**
  - Plan: `docs/superpowers/plans/2026-08-18-provider-adapters.md`
  - Delivers Claude Code, GitHub Copilot, Kimi, Gemini adapters only for verified fixture-backed formats.

- [ ] **Increment F — Team Bundle**
  - Plan: `docs/superpowers/plans/2026-08-18-team-bundle.md`
  - Delivers deterministic sanitized export, validation, provenance, idempotent import, CLI flow.

- [ ] **Increment G — Team analytics/report**
  - Plan: `docs/superpowers/plans/2026-08-18-team-analytics-report.md`
  - Delivers team aggregation, per-user/project/source/model/machine metrics, optional budget projection, end-to-end team report.

## Dependency rules

1. B may follow A without depending on D/E/F/G.
2. C must finish before E.
3. D must finish before F/G because team identity depends on stable user/machine keys.
4. E may be implemented after C and can proceed before F, but all provider adapters must pass before full V2 acceptance.
5. F depends on A, C, and D contracts; G depends on F.
6. Do not begin G until team bundle idempotency/privacy tests are green.

## Final acceptance

- [ ] V1 database migrates without data loss/duplication.
- [ ] All six registered sources work according to verified capability contracts.
- [ ] Report filters and pt-BR money/number formatting are correct.
- [ ] False-positive skill/model/agent regression tests pass.
- [ ] User and machine are separate and confidence is explicit.
- [ ] Team bundle privacy sentinel test passes.
- [ ] Reimport does not change totals.
- [ ] Team report aggregates by required dimensions without labeling token volume as productivity.
- [ ] `python -m pytest -q` passes.
- [ ] GitHub Actions passes on supported Python versions.
- [ ] README/provider/team docs are current.
