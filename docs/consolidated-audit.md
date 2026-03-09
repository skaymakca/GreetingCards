# Consolidated Parallel Audit Orchestration

When asked to run a "full audit", "consolidated audit", or "all audits", follow this methodology. It runs a shared pre-pass once, launches all three audits (code quality, coverage analysis, MVC compliance) as parallel agents, then consolidates findings into a unified report.

**Expected duration:** ~3–4 hours wall clock (pre-pass ~15 min, parallel audits ~2–3 hours, consolidation ~30 min).

## Overview

The three individual audit methodologies are:

| Audit            | Methodology Doc                                                     | Output Path                                            |
|------------------|---------------------------------------------------------------------|--------------------------------------------------------|
| Code Quality     | [`docs/code-quality-audit.md`](code-quality-audit.md)            | `_build/audit/{ts}-code-quality.md`                    |
| Coverage         | [`docs/coverage-analysis.md`](coverage-analysis.md)              | `_build/coverage/{cov_ts}/coverage-analysis.md`        |
| MVC Compliance   | [`docs/mvc-compliance-audit.md`](mvc-compliance-audit.md)        | `_build/audit/{ts}-mvc-compliance.md`                  |
| **Consolidated** | This doc                                                            | `_build/audit/{ts}-consolidated-audit.md`              |

Each audit is read-only (no source modifications), with non-overlapping output paths. This makes direct parallel agents the simplest and safest orchestration approach — no worktrees or isolation needed.

## Phase 1: Pre-Pass (Sequential, ~15 min)

The orchestrating session runs these steps sequentially and captures results. This avoids duplicating work across the three audit agents.

### Steps

1. **Generate shared timestamp** — `YYYYMMDDThhmm` format (e.g., `20260309T1422`). All audit output files use this timestamp.

2. **Create output directory:**
   ```bash
   mkdir -p _build/audit
   ```

3. **Run `make check`** — all static analysis (pyright, mypy, ruff check, ruff format, bandit). Record pass/fail and any diagnostics.

4. **Run `make test-everything`** — all tests (core, gui, scripts, integration) with coverage. Reports open in browser.
   - After completion, read the coverage directory timestamp from the `_build/coverage/latest` symlink:
     ```bash
     readlink _build/coverage/latest
     ```
   - Record the resolved `cov_ts` (e.g., `20260309T1430`) — the coverage agent needs this path.

5. **Run `make licenses-sync`** — check for license registry drift.
   - Inspect the diff: `git diff content/licenses/`
   - If there's a diff, record it as an LR finding for the code quality audit agent.
   - **Revert changes** — the audit is read-only:
     ```bash
     git checkout -- content/licenses/
     ```

6. **PyCharm inspections** (if JetBrains MCP is available) — run `mcp__jetbrains__get_file_problems` on all Python files in `main.py`, `app/**/*.py`, `scripts/*.py`. Record findings.
   - If MCP is unavailable, record "N/A — PyCharm not available" and continue.

7. **Capture pre-pass summary** — build a text block summarizing all results. This gets passed to each audit agent.

### Pre-Pass Summary Format

```
PRE-PASS RESULTS
================
Timestamp: {ts}
Branch: {branch}

make check:
  pyright: {pass/fail — N diagnostics}
  mypy: {pass/fail — N diagnostics}
  ruff check: {pass/fail — N diagnostics}
  ruff format: {pass/fail — N reformatted}
  bandit: {pass/fail — N issues}

Tests: {pass/fail — N passed, N failed}
Coverage directory: _build/coverage/{cov_ts}/

licenses-sync: {clean / N changes — details}

PyCharm: {N findings / N/A}
```

### Pre-Pass Failures

- If `make check` or tests fail, record the failures as findings and **proceed with audits**. Pre-pass failures are informational, not blockers.
- Only abort for **infrastructure failures** (e.g., `uv` not installed, missing dependencies, broken venv).

## Phase 2: Parallel Audits (3 Agents, ~2–3 hours)

Launch three general-purpose agents simultaneously. Each agent receives:
- The pre-pass summary (so it skips re-running static checks and tests)
- A reference to its methodology doc
- The shared timestamp for output file naming

### Agent Prompts

**Agent 1 — Code Quality Audit:**

> You are running a code quality audit for the Greeting Cards project. Follow the methodology in `docs/code-quality-audit.md`.
>
> IMPORTANT: The pre-pass has already been completed. Skip the "Pre-Pass — Automated Baseline" section entirely. Start at "Pass 1 — Broad Sweep" and proceed from there.
>
> Pre-pass results to include in your findings file:
> {pre-pass summary}
>
> Write your findings to `_build/audit/{ts}-code-quality.md`.
> Use timestamp `{ts}` in the file header.
>
> Read the methodology doc first, then execute the multi-pass convergence process.

**Agent 2 — Coverage Analysis:**

> You are running a coverage analysis for the Greeting Cards project. Follow the methodology in `docs/coverage-analysis.md`.
>
> IMPORTANT: Coverage data has already been generated. The coverage directory is `_build/coverage/{cov_ts}/`. Do NOT re-run tests or generate new coverage data. Use the existing HTML report and status.json.
>
> Pre-pass results for context:
> {pre-pass summary}
>
> Write your analysis to `_build/coverage/{cov_ts}/coverage-analysis.md`.
>
> Read the methodology doc first, then analyze the coverage data and produce the coverage analysis document.

**Agent 3 — MVC Compliance Audit:**

> You are running an MVC compliance audit for the Greeting Cards project. Follow the methodology in `docs/mvc-compliance-audit.md`.
>
> IMPORTANT: Static checks have already been run in a pre-pass. Start at "Pass 1 — Broad Sweep" and proceed from there.
>
> Pre-pass results for context:
> {pre-pass summary}
>
> Write your findings to `_build/audit/{ts}-mvc-compliance.md`.
> Use timestamp `{ts}` in the file header.
>
> Read the methodology doc first, then execute the multi-pass convergence process.

### Agent Nesting

Each audit agent may internally launch sub-agents (e.g., the code quality audit launches 4 parallel agents in Pass 1). This creates 2 levels of nesting (orchestrator → audit agent → sub-agents).

If nesting issues arise (e.g., agent depth limits), the audit agents should fall back to running their internal passes sequentially rather than with parallel sub-agents. Note this in the audit output.

## Phase 3: Consolidation (~30 min)

After all three agents complete, the orchestrating session:

1. **Read all three output files:**
   - `_build/audit/{ts}-code-quality.md`
   - `_build/coverage/{cov_ts}/coverage-analysis.md`
   - `_build/audit/{ts}-mvc-compliance.md`

2. **Identify cross-cutting findings** — issues that appear across multiple audit dimensions:
   - A code quality bug that's also an MVC violation
   - A low-coverage file that also has code quality findings
   - An MVC boundary leak in a file with missing tests
   - Repeated code that also represents an MVC abstraction gap

3. **Build unified remediation roadmap** — prioritize by effort and impact across all three audits.

4. **Write consolidated report** to `_build/audit/{ts}-consolidated-audit.md` using the template below.

## Consolidated Report Template

````markdown
# Consolidated Audit Report

**Date:** YYYY-MM-DD
**Branch:** {branch}
**Shared timestamp:** {ts}

## Individual Reports

| Audit          | Report Path                                         | Status    |
|----------------|-----------------------------------------------------|-----------|
| Code Quality   | `_build/audit/{ts}-code-quality.md`                 | Converged |
| Coverage       | `_build/coverage/{cov_ts}/coverage-analysis.md`     | Complete  |
| MVC Compliance | `_build/audit/{ts}-mvc-compliance.md`               | Converged |

---

## Executive Summary

3–5 sentences summarizing the overall health of the codebase across all three dimensions. Highlight the most significant findings and the highest-priority remediation areas.

---

## Shared Pre-Pass Results

| Tool         | Issues | Notes |
|--------------|--------|-------|
| pyright      | 0      | —     |
| mypy         | 0      | —     |
| ruff check   | 0      | —     |
| ruff format  | 0      | —     |
| bandit       | 0      | —     |
| PyCharm      | 0      | N/A   |
| pytest       | all pass | —   |
| licenses-sync | clean  | —    |

---

## Cross-Cutting Findings

Issues that span multiple audit dimensions. Each row shows which audits flagged (or are adjacent to) the finding.

| # | File(s) | Code Quality | Coverage | MVC | Description | Severity |
|---|---------|:---:|:---:|:---:|-------------|----------|
| 1 | `path/to/file.py` | H3 | Low (42%) | M2 | Description of the cross-cutting issue | High |

---

## Per-Audit Summaries

### Code Quality

**Findings:** xH + xM + xL + xS = N total
**Convergence:** N passes

Top clusters:
1. [Cluster name] — N findings — [brief description]
2. [Cluster name] — N findings — [brief description]

→ Full details: `_build/audit/{ts}-code-quality.md`

### Coverage

**Overall coverage:** X% (N/M lines)
**Files below 70%:** N

Key gaps:
1. `path/to/file.py` — X% — [what's untested]
2. `path/to/file.py` — X% — [what's untested]

→ Full details: `_build/coverage/{cov_ts}/coverage-analysis.md`

### MVC Compliance

**Findings:** xH + xM + xL + xS = N total
**Convergence:** N passes

Top clusters:
1. [Cluster name] — N findings — [brief description]
2. [Cluster name] — N findings — [brief description]

→ Full details: `_build/audit/{ts}-mvc-compliance.md`

---

## Unified Remediation Roadmap

### Immediate (quick wins, high impact)

| # | Action | Addresses | Effort | Impact |
|---|--------|-----------|--------|--------|
| 1 | Description | CQ-H1, MVC-M2 | Low | High |

### Short-Term (focused effort, clear payoff)

| # | Action | Addresses | Effort | Impact |
|---|--------|-----------|--------|--------|
| 2 | Description | CQ-M3, Cov-gap1 | Medium | Medium |

### Strategic (larger refactors, systemic improvements)

| # | Action | Addresses | Effort | Impact |
|---|--------|-----------|--------|--------|
| 3 | Description | CQ-Cluster2, MVC-Cluster1 | High | High |

---

## Methodology Notes

- **Shared timestamp:** {ts}
- **Coverage timestamp:** {cov_ts}
- **Code Quality passes:** N (converged)
- **MVC passes:** N (converged)
- **Agent nesting:** 2 levels (orchestrator → audit agent → sub-agents)
- **Pre-pass tools:** pyright, mypy, ruff, bandit, PyCharm, pytest, licenses-sync
````

## Edge Cases

### Coverage Timestamp Mismatch

Coverage data gets its own timestamp from `scripts/run_tests.py`, which may differ from the shared audit timestamp. The orchestrator reads `_build/coverage/latest` to get the actual coverage directory path and passes it to the coverage agent. Both timestamps appear in the consolidated report for traceability.

### PyCharm Unavailable

If the JetBrains MCP server is not available, record "N/A" in the pre-pass results table and skip PyCharm inspections. The audit proceeds normally — PyCharm findings are supplementary, not required.

### Pre-Pass Failures

Static check or test failures are recorded as findings but do not block the audit. The audit agents receive the failure information and may reference it. Only infrastructure failures (broken tooling, missing dependencies) should abort the process.

### Agent Nesting Limits

If parallel sub-agents within an audit agent fail due to nesting depth limits, the audit agent should fall back to running its internal passes sequentially. This is slower but produces identical results. The pass log should note the fallback.

## How to Run

1. Run `make audit-prepass` (executes `make check` then `make test-everything`)
2. Run `make licenses-sync`, inspect diff, record LR findings, revert with `git checkout -- content/licenses/`
3. Run PyCharm inspections via MCP (if available)
4. Capture the coverage directory path from `_build/coverage/latest`
5. Build the pre-pass summary text
6. Launch 3 parallel agents with the prompts from Phase 2
7. Wait for all agents to complete
8. Read all three output files
9. Identify cross-cutting findings
10. Write the consolidated report to `_build/audit/{ts}-consolidated-audit.md`
