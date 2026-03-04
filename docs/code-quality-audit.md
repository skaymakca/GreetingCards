# Code Quality Audit

When asked to audit the codebase, follow this methodology. The audit uses a batch pre-pass for automated tools, then parallel agents in convergence passes to systematically review every file.

## What to Look For

Check for these categories across all files in `app/`, `tests/`, and `scripts/`.

### Categories

| Code | Category                      | Description                                                                                                                                                                                           |
|------|-------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| MT   | Missing tests                 | Public methods/functions without tests, untested error paths, shallow happy-path-only coverage                                                                                                        |
| UC   | Unused code                   | Dead imports, unreachable code paths, unused functions/variables                                                                                                                                      |
| TA   | Type annotations              | Functions missing `-> None` or return types, untyped parameters                                                                                                                                       |
| RC   | Repeated code                 | Duplicate logic across files that should be extracted to shared helpers                                                                                                                               |
| UP   | Unpythonic patterns           | `dict.__init__(self)` instead of `super().__init__()`, `lambda: Path()` instead of `Path`, `count == 0` instead of `not count`, etc.                                                                 |
| MC   | Magic constants               | Hardcoded strings, pixel values, colors, or numbers that should be named constants                                                                                                                    |
| HC   | Hardcoded colors              | `wx.Colour(...)` literals that duplicate values in `app/gui/styles.py`                                                                                                                                |
| PL   | Print instead of logging      | `print()` calls that should use `logging.getLogger(__name__)`                                                                                                                                         |
| IL   | Incomplete logic              | Missing else branches, unhandled empty/None cases, no input validation                                                                                                                                |
| BL   | Bugs and logic errors         | Race conditions, off-by-one errors, unbounded loops, case-sensitivity mismatches, stale state after mutations, silent exception swallowing that hides real failures                                    |
| SM   | Stale Makefile                | Targets referencing outdated paths, wrong Python versions, missing new entry points, or commands that no longer match the project structure                                                            |
| LR   | License registry gaps         | Run `make licenses-sync`, then check `content/licenses/registry.toml` for: missing license text files, empty homepage URLs, "Unknown" license types, platform-specific packages for the exclude list  |
| RL   | Redundant license config      | `content/licenses/config.toml` `[[package]]` entries that only exist when they override auto-discovered values. Remove entries where `display` matches `name` and no other fields are set             |

### Severity Key

- **HIGH (H)** — Bugs, logic errors, race conditions, security issues — things that cause incorrect behavior
- **MEDIUM (M)** — Structural issues with contained scope — repeated code, incomplete logic, missing validation
- **LOW (L)** — Minor issues, style concerns, small gaps — magic constants, missing annotations, unpythonic patterns
- **STYLE (S)** — Informational only, not actionable defects

## Static Analysis

Run the full static analysis suite and verify zero issues across all tools:

```bash
make check   # runs all of the below in sequence
```

| Tool        | Command                                                   | Scope                                                 | Expected             |
|-------------|-----------------------------------------------------------|-------------------------------------------------------|----------------------|
| pyright     | `pyright app/ scripts/ main.py`                           | Type checking (structural)                            | 0 errors, 0 warnings |
| mypy        | `uv run mypy app/ scripts/ main.py`                       | Type checking (nominal, SQLAlchemy plugin)            | 0 errors             |
| ruff check  | `uv run ruff check app/ scripts/ tests/ main.py`          | Linting (pyflakes, pycodestyle, isort, bugbear, etc.) | 0 errors             |
| ruff format | `uv run ruff format --check app/ scripts/ tests/ main.py` | Formatting                                            | 0 reformatted        |
| bandit      | `uv run bandit -r app/ scripts/ -c pyproject.toml`        | Security scan                                         | 0 issues             |

For each diagnostic, determine whether to:
- **Fix the code** — if the checker found a real bug or a type that should be tightened
- **Add a suppression comment** (`# type: ignore[code]` or `# pyright: ignore[code]`) — if the diagnostic is a false positive or an intentional pattern (e.g. `sys._MEIPASS`, wxPython stubs)

**Before applying any suppression comments**, summarize every suppression to the user with:
1. The file, line, and diagnostic code
2. What the checker is complaining about
3. Why suppression (rather than a fix) is the right call

Wait for user approval before adding suppressions. The user may decide to fix the code, file an upstream bug, or handle it differently.

## PyCharm Inspections

Always attempt to run PyCharm inspections on all Python files in `main.py`, `app/**/*.py`, and `scripts/*.py` via the JetBrains MCP server. See the "PyCharm Inspections (MCP)" section in `CLAUDE.md` for details.

If the MCP server is unavailable (PyCharm not running, plugin not installed, tool calls fail), note the reason in the audit report and continue — do not fail the overall audit.

## Methodology: Multi-Pass Convergence

The audit runs in iterative passes. A batch pre-pass captures automated tool output, then parallel agents review the codebase from different angles. Passes continue until a pass produces zero new findings (**convergence**).

### Pre-Pass — Automated Baseline (batch, not agents)

Run these and capture output as reference material for agent passes:

1. `make check` — all static analysis diagnostics
2. PyCharm inspections — via JetBrains MCP on all Python files
3. `uv run pytest tests/ -x` — test results and coverage
4. `make licenses-sync` — license registry state

Tool-reported issues become pre-pass findings (category TA, UC, etc.) in the findings table. Agents in subsequent passes should not re-report what tools already caught.

### Pass 1 — Broad Sweep (4 parallel general-purpose agents)

| Agent | Scope                                        | Focus                                                         |
|-------|----------------------------------------------|---------------------------------------------------------------|
| A     | `app/core/**/*.py`                           | All 13 categories within core modules                         |
| B     | `app/gui/**/*.py`                            | All 13 categories within GUI modules                          |
| C     | `app/models/*.py`, `scripts/*.py`, `main.py` | All 13 categories within models, scripts, entry point         |
| D     | `tests/**/*.py`                              | Coverage gaps (compare test files against source modules), MT  |

Each agent reads every file in its scope, checking:
1. **Import statements** — unused imports, circular dependencies
2. **Method bodies** — bugs, logic errors, race conditions, incomplete logic
3. **Type signatures** — missing annotations, loose types
4. **Constants and literals** — magic values, hardcoded colors
5. **Patterns** — unpythonic idioms, repeated code within scope
6. **Test coverage** — (Agent D) map source modules to test files, identify gaps

Each agent returns findings as a table with temporary IDs (A1, B1, C1, D1, ...).

### Interphase Consolidation Rules

After each pass:
1. **Deduplicate** — merge findings that describe the same issue from different agents
2. **Cross-reference pre-pass** — drop findings already reported by automated tools
3. **Adjust severity** — if a finding is confirmed with new context, upgrade or downgrade
4. **Strike rejected findings** — mark with ~~strikethrough~~ and note the rejection reason
5. **Assign final IDs** — sequential within severity (H1, M1, L1, S1)
6. **Update pass log** — record agent count, new findings, adjustments

### Pass 2 — Deep Dive + Validation (2–3 parallel agents)

| Agent | Focus                                                                                                                          |
|-------|--------------------------------------------------------------------------------------------------------------------------------|
| E     | **Cross-cutting**: repeated code across areas, inter-module coupling, shared pattern violations. Validates/rejects A, B, C.    |
| F     | **Bugs + logic**: trace error flows, race conditions, edge cases adjacent to Pass 1 hits. Validates/rejects BL/IL findings.    |
| G     | **Test coverage** (if D found gaps): map untested paths discovered by E and F. Validates/rejects D's findings. Optional.       |

Pass 2 agents receive the Pass 1 findings list. For each, they state **CONFIRMED** or **REJECTED** with reasoning. They also look for new findings in areas adjacent to Pass 1 hits.

### Pass 3+ — Convergence (1 agent)

One agent sweeps areas not specifically covered or lightly touched in prior passes:
- Makefile targets and project configuration (SM)
- License registry and config (LR, RL)
- Infrastructure files not in agent scopes
- Inter-module patterns missed by area-scoped agents
- Dead code across module boundaries

If this pass finds zero new findings, the audit is **converged**. Otherwise, repeat with targeted agents until convergence.

## Output

All findings go into `.local/audits/YYYYMMDDThhmm-code-quality.md` (timestamp of when the audit started). After convergence, group related findings into **clusters** — sets of findings that share a root cause or would be fixed together.

### Presentation Guidelines

- **HIGH and MEDIUM findings**: List individually in full detail tables (one row per finding). These are significant enough to warrant individual attention.
- **LOW findings**: Group by theme in a summary table. Each row is a theme (e.g., "Magic constants in GUI", "Missing type annotations in scripts") with a count and representative examples — not one row per finding.
- **STYLE findings**: Group by theme, same as LOW.
- **Missing Tests**: Separate table listing coverage gaps.
- **Clusters**: Present as a single table, not prose sections. Each row is a cluster with columns for name, included findings, root cause, fix approach, and priority.
- **Assessment**: After findings and clusters, write a prose section evaluating overall codebase quality, common themes across findings, and prioritized remediation recommendations.

### Findings File Template

Use this template for the findings file:

````markdown
# Code Quality Audit — [Title]

**Date:** YYYY-MM-DD
**Branch:** [branch name]
**Methodology:** Multi-pass convergence audit (batch pre-pass + agent passes)

## Severity Key
- **HIGH (H)** — Bugs, logic errors, race conditions, security issues
- **MEDIUM (M)** — Structural issues with contained scope
- **LOW (L)** — Minor issues, style concerns, small gaps
- **STYLE (S)** — Informational only

## Category Key
| Code | Category |
|------|----------|
| MT | Missing tests | UC | Unused code | TA | Type annotations |
| RC | Repeated code | UP | Unpythonic patterns | MC | Magic constants |
| HC | Hardcoded colors | PL | Print→Logging | IL | Incomplete logic |
| BL | Bugs/Logic errors | SM | Stale Makefile | LR | License registry |
| RL | Redundant license config |

---

## Pre-Pass — Automated Tools

| Tool | Issues | Notes |
|------|--------|-------|
| pyright | 0 | — |
| mypy | 0 | — |
| ruff check | 0 | — |
| ruff format | 0 | — |
| bandit | 0 | — |
| PyCharm | 0 | — |
| pytest | all pass | — |

---

## Findings

### HIGH — Bugs, logic errors, security issues

| ID | Cat | File | Lines | Finding | Pass |
|----|-----|------|-------|---------|------|
| H1 | BL  | `path/to/file.py` | 42–50 | **Description.** Details. | P1 |

### MEDIUM — Structural issues

| ID | Cat | File | Lines | Finding | Pass |
|----|-----|------|-------|---------|------|
| M1 | RC  | `path/to/file.py` | 10 | **Description.** Details. | P1 |

### LOW — Minor issues (grouped by theme)

| Theme | IDs | Count | Examples |
|-------|-----|-------|----------|
| Magic constants in GUI | L1, L4, L8 | 3 | `panel.py:42` hardcoded 600px width; `dialog.py:15` literal color |
| Missing type annotations | L2, L5 | 2 | `helper.py:10` missing return type; `utils.py:22` untyped param |

### STYLE — Informational only (grouped by theme)

| Theme | IDs | Count | Examples |
|-------|-----|-------|----------|
| Unpythonic patterns | S1, S3 | 2 | `foo.py:10` uses `len(x) == 0` instead of `not x` |

### Missing Tests

| ID | Source File | Gap | Pass |
|----|------------|-----|------|
| T1 | `path/to/file.py` | No tests for error paths in `method_name()` | P1 |

---

## Clusters

| # | Name | Findings | Root Cause | Fix | Priority |
|---|------|----------|------------|-----|----------|
| 1 | [Cluster name] | H1, M2, L5 | Shared root cause description | Suggested approach | High / Medium / Low |

---

## Assessment

### Overall Quality

Prose evaluation of the codebase's overall health — architecture, consistency, test coverage, error handling patterns, and how the findings compare to what you'd expect for a project of this size and maturity.

### Common Themes

Recurring patterns observed across multiple findings or clusters. These are systemic tendencies rather than isolated issues (e.g., "error paths are under-tested throughout", "magic constants concentrate in GUI code").

### Remediation Recommendations

Prioritized list of recommended actions, ordered by impact. Group by effort level (quick wins vs. larger refactors) and note which clusters each recommendation addresses.

---

## Rejected Findings

Findings that were raised in earlier passes but rejected during consolidation. Keep for transparency.

| ID | Cat | Finding | Reason Rejected | Pass |
|----|-----|---------|-----------------|------|
| ~A1~ | BL | **Description.** | Reason for rejection. | P1→P2 |

---

## Pass Log

| Pass     | Agents  | New Findings                   | Notes               |
|----------|---------|--------------------------------|----------------------|
| Pre-pass | (batch) | xH + xM + xL + xS = N         | Automated tools      |
| P1       | A, B, C, D | xH + xM + xL + xS = N      | Broad sweep          |
| P2       | E, F, G | xH + xM + xL + xS = N         | Deep dive, validations |
| P3       | H       | 0 new findings                 | **CONVERGED**        |

**Status: CONVERGED after N passes**
**Active totals: xH + xM + xL + xS = N findings across N clusters**
````

## How to Run

1. Create the output directory if needed (`mkdir -p .local/audits`)
2. Create a fresh findings file from the template above at `.local/audits/YYYYMMDDThhmm-code-quality.md`
3. Run the Pre-Pass: `make check`, PyCharm inspections, `pytest`, `make licenses-sync` — record results
4. Launch Pass 1: four parallel general-purpose agents (A, B, C, D) with the scopes defined above
5. Consolidate Pass 1 findings, cross-reference against pre-pass output
6. Launch Pass 2: two or three parallel agents (E, F, G) — pass them the Pass 1 findings for validation
7. Consolidate Pass 2 findings, apply confirmations/rejections
8. Launch Pass 3: one convergence agent sweeping uncovered areas
9. If zero new findings → converged. Otherwise, repeat.
10. Build clusters from the final findings set
11. Update the pass log and final totals

**No code changes during the audit** — the findings file is the deliverable.

## Coverage Analysis

When the audit identifies coverage gaps (MT/T findings) and remediation adds tests, follow the methodology in [`docs/coverage-analysis.md`](coverage-analysis.md) to document the work with a before/after comparison.
