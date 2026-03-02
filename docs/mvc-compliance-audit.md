# MVC Compliance Audit

When asked to audit the codebase for MVC compliance, follow this methodology. The audit uses parallel agents in convergence passes to systematically check every layer boundary.

## Current Status

As of 2026-03-02, the codebase has **high MVC compliance** after multiple audit-guided refactoring cycles. Service facades (`CardService`, `RenameService`, `ProcessingService`, `AIService`, `ConfigService`, `FilterService`) mediate all GUI→Core communication. The GUI layer contains no direct store mutations, no direct database access, and delegates all business logic to services. Remaining findings are minor: type looseness in the database layer, a few stateless utility imports bypassing facades, and presentation text in AI error detail fields — all documented with inline comments and conscious trade-off rationale.

## What the Audit Checks

### Layer Rules

**Model / Core (`app/core/`, `app/models/`)**
- No display strings (user-facing text, formatted error messages for display)
- No GUI imports (`app.gui.*`)
- No presentation-shaped data (UI labels, color info, widget references)
- No GUI concepts in docstrings (`wx.CallAfter`, `MainWindow`, "GUI callers", "UI thread")
- Services return typed results (enums, dataclasses), not raw strings
- Services are complete facades — GUI should not need to bypass them

**View / GUI (`app/gui/`)**
- No direct core-internal imports (use service facades in `app/core/services/`)
- No business logic (domain rules, multi-step orchestration, validation algorithms)
- No direct data store ownership or queries
- Exception: direct imports of simple constants/enums from `app.core.constants` or `app.models.*` are LOW severity

**Services (`app/core/services/`)**
- Complete facades exposing everything GUI needs
- No presentation concerns
- Layer-agnostic docstrings (no GUI-framework mentions)
- Typed return values and parameters

**Models (`app/models/`)**
- No UI state or display-only methods
- Proper types (enums over Literal strings where practical)
- No dead fields

**Database (`app/core/database.py`)**
- No UI references in comments/docstrings
- Typed parameters matching model Literal/Enum types
- No display-shaped DTOs

**Test harnesses (`scripts/visual_test.py`)**
- Should use public APIs where possible
- Private API access should be annotated and minimized

### Severity Key

- **HIGH (H)** — Structural violations creating significant coupling (multi-step orchestration in GUI, direct store mutations from GUI, systematic cross-layer contamination)
- **MEDIUM (M)** — Cross-boundary leaks with contained scope (direct core-internal imports from GUI, display logic in core, business rules in view)
- **LOW (L)** — Minor issues, borderline cases, framework-forced patterns
- **STYLE (S)** — Not MVC violations, informational only

## Methodology: Multi-Pass Convergence

The audit runs in iterative passes with parallel agents. Each pass covers the full codebase from a different angle. Passes continue until a pass produces zero new findings (**convergence**).

### Pass 1 — Broad Sweep (3 parallel agents)

| Agent | Focus | Files |
|-------|-------|-------|
| A — GUI→Core boundary | Direct imports from `app.core.*` in GUI, business logic in view, orchestration in mixins | `app/gui/**/*.py` |
| B — Core purity | Display strings, GUI references, presentation data in core/services/pipeline | `app/core/**/*.py` |
| C — Models + cross-cutting | Model layer violations, type looseness, database coupling, test harness coupling | `app/models/*.py`, `app/core/database.py`, `scripts/visual_test.py` |

Each agent reads every file in its scope, checking:
1. **Import statements** — cross-layer imports that bypass service facades
2. **Method bodies** — business logic, domain rules, display string generation
3. **Docstrings/comments** — GUI-framework references in core, "for display" framing
4. **Type signatures** — raw `str` where typed alternatives exist
5. **Return values** — display strings vs. structured types

Each agent returns findings as a table with temporary IDs (A1, B1, C1, ...).

### Pass 2 — Deep Dive + Validation (2 parallel agents)

| Agent | Focus |
|-------|-------|
| D — GUI deep-dive | Method bodies in main_window, mixins, review_panel. Orchestration patterns (5+ step methods). Magic string APIs at service boundaries. Domain rules encoded in view rendering. Also validates/rejects Pass 1 GUI findings. |
| E — Core+Models deep-dive | Service facade completeness. Cross-layer error flow tracing (AI, PDF, rename). Naming pipeline. Dead code. Also validates/rejects Pass 1 Core/Model findings. |

Pass 2 agents receive the Pass 1 findings list. For each, they state **CONFIRMED** or **REJECTED** with reasoning. They also look for new findings in areas adjacent to Pass 1 hits.

### Pass 3+ — Convergence (1–2 agents)

One agent sweeps all areas NOT specifically covered in prior passes:
- GUI infrastructure (`appearance.py`, `styles.py`, `icons.py`, `utils.py`)
- Naming pipeline (`app/core/naming/`)
- Pipeline internals (`card_processor.py`, `rate_limit.py`)
- Content generators (`app/core/content/`)
- Entry point (`main.py`)
- Inter-service coupling
- Dead code / unused imports

If this pass finds zero new findings, the audit is **converged**. Otherwise, repeat with targeted agents until convergence.

### Consolidation Rules

After each pass:
1. **Deduplicate** — merge findings that describe the same violation from different agents
2. **Adjust severity** — if a finding is confirmed with new context, upgrade or downgrade
3. **Strike rejected findings** — mark with ~~strikethrough~~ and note the rejection reason
4. **Assign final IDs** — sequential within severity (H1, M1, L1, S1)
5. **Update pass log** — record agent count, new findings, adjustments

## Output

All findings go into `.claude/mvc-audit-findings.md`. After convergence, group related findings into **clusters** — sets of findings that share a root cause or would be fixed together.

### Findings File Template

Use this template for `.claude/mvc-audit-findings.md`:

````markdown
# MVC Compliance Audit — [Title]

**Date:** YYYY-MM-DD
**Branch:** [branch name]
**Methodology:** Multi-pass convergence audit

## Severity Key
- **HIGH (H)** — Structural violations creating significant coupling
- **MEDIUM (M)** — Cross-boundary leaks with contained scope
- **LOW (L)** — Minor issues, borderline cases, framework-forced patterns
- **STYLE (S)** — Not MVC violations, informational only

---

## Findings

### HIGH — Structural violations

| ID | File | Lines | Finding | Pass |
|----|------|-------|---------|------|
| H1 | `path/to/file.py` | 42–50 | **Description.** Details. | P1 |

### MEDIUM — Cross-boundary leaks

| ID | File | Lines | Finding | Pass |
|----|------|-------|---------|------|
| M1 | `path/to/file.py` | 10 | **Description.** Details. | P1 |

### LOW — Minor issues, borderline cases

| ID | File | Lines | Finding | Pass |
|----|------|-------|---------|------|
| L1 | `path/to/file.py` | 5 | **Description.** Details. | P1 |

### STYLE — Informational only

| ID | File | Lines | Finding | Pass |
|----|------|-------|---------|------|
| S1 | `path/to/file.py` | 99 | **Description.** Details. | P1 |

---

## Clusters

### Cluster 1: [Name]
**Findings:** H1, M2, L5
**Root cause:** Description of the shared root cause.
**Fix:** Suggested approach.

---

## Pass Log

| Pass | Agents | New Findings | Notes |
|------|--------|-------------|-------|
| P1   | A, B, C | xH + xM + xL + xS = N | Initial sweep |
| P2   | D, E    | xH + xM + xL + xS = N | Deep dive, validations |
| P3   | F       | 0 new findings | **CONVERGED** |

**Status: CONVERGED after N passes**
**Active totals: xH + xM + xL + xS = N findings across N clusters**
````

## How to Run

1. Clear or archive the previous `.claude/mvc-audit-findings.md` (old version is in git history)
2. Create a fresh findings file from the template above
3. Launch Pass 1: three parallel agents (A, B, C) with the scopes defined above
4. Consolidate Pass 1 findings into the file
5. Launch Pass 2: two parallel agents (D, E) — pass them the Pass 1 findings for validation
6. Consolidate Pass 2 findings, apply confirmations/rejections
7. Launch Pass 3: one convergence agent sweeping uncovered areas
8. If zero new findings → converged. Otherwise repeat.
9. Build clusters from the final findings set
10. Update the pass log and final totals

**No code changes during the audit** — the findings file is the deliverable.
