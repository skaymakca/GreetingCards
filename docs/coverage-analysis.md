# Coverage Analysis

How to run a detailed coverage analysis and document the results. Used standalone or as a follow-up to a [code quality audit](code-quality-audit.md) that identified coverage gaps.

## How to Run

```bash
# Full default suite (core + gui + scripts) with coverage
make test T="default --cov"

# Single scope
make test T="scripts --cov"

# Everything including integration tests, open in browser
make test T="all --cov --open"
```

This creates a timestamped directory under `_build/coverage/YYYYMMDDThhmm/` containing:

```
_build/coverage/20260303T1654/
├── htmlcov/              # Flat HTML report (pytest-cov)
│   ├── index.html        # Summary page
│   └── status.json       # Machine-readable coverage data
├── htmlcov-grouped/      # Hierarchical view (via genhtml + lcov, if available)
│   └── index.html
└── coverage.lcov         # LCOV format (intermediate for genhtml)
```

A `latest` symlink is updated to point to the most recent run.

Open `_build/coverage/latest/htmlcov/index.html` in a browser. The grouped view (`htmlcov-grouped/`) organizes files by directory hierarchy. The `status.json` file in `htmlcov/` contains machine-readable per-file coverage data — useful for scripted comparisons.

## Coverage Analysis

Review the coverage report and produce a `coverage-analysis.md` in the coverage run directory (`_build/coverage/<timestamp>/coverage-analysis.md`). This document has two parts: an overall landscape summary, then a gap analysis with exclusions, per-file targets, and specific tests to write.

### Steps

1. **Summarize the landscape** — narrative overview of where coverage stands, followed by tables grouping files by coverage tier. Call out which areas are strong and which have gaps.
2. **Identify untestable code** — files that can never have unit tests (benchmarks requiring real hardware/data, interactive GUI harnesses, config files executed by external tools with injected globals, entry-point trampolines). These become `[tool.coverage.run] omit` entries in `pyproject.toml`.
3. **Identify testable gaps** — files with low coverage that contain testable logic (pure functions, argument parsing, branching logic, error paths).
4. **Set per-file targets** — realistic coverage percentages based on what's mockable. Not everything reaches 100% — platform API calls, async orchestration loops, and subprocess wrappers often have a ceiling.
5. **Design tests** — for each targeted file, list specific tests with what they cover and what mocking is needed.

### Coverage Analysis Template

````markdown
# [Module] Coverage Analysis

**Coverage run:** `_build/coverage/<timestamp>/`
**Current coverage:** X% (covered/total lines)

Narrative summary of the coverage landscape — what areas are well-covered, where the significant gaps are, and what's driving the overall number. Note any patterns (e.g., "CLI argument parsing is consistently tested, but async orchestration paths are not").

---

## Coverage Landscape

Every file in the module, grouped by coverage tier.

### Tier: 100% Coverage

| File | Lines |
|---|---|
| `path/to/file.py` | N |

### Tier: 90–99% Coverage

| File | Coverage | Uncovered Lines |
|---|---|---|
| `path/to/file.py` | X% (covered/total) | N |

### Tier: 70–89% Coverage

| File | Coverage | Uncovered Lines | Notes |
|---|---|---|---|
| `path/to/file.py` | X% (covered/total) | N | What's uncovered and why |

### Tier: Below 70%

| File | Coverage | Uncovered Lines | Notes |
|---|---|---|---|
| `path/to/file.py` | X% (covered/total) | N | What's uncovered and why |

---

## Gap Analysis

### Proposed Exclusions

Files to add to `[tool.coverage.run] omit` in `pyproject.toml`. Only genuinely untestable code.

```toml
[tool.coverage.run]
omit = [
    # Reason for each exclusion
    "path/to/file.py",
]
```

**Lines removed from tracking:** ~N

### Targeted Tests

#### `path/to/file.py` (current% → ~target%)

| Test | What It Covers |
|---|---|
| `test_descriptive_name` | Description of the logic path exercised |
| `test_error_case` | Description of the error path exercised |

**Mocking:** What needs to be mocked and why.

---

## Summary

| Part | Tests Added | Coverage Impact |
|---|---|---|
| Exclusion config | 0 | Removes ~N untestable lines from denominator |
| [Group name] | N | `file.py` X→Y%, `other.py` X→Y% |
| **Total** | **N tests** | Module coverage: X% → **~Y%** |

---

## Verification

1. `make check` — all static checks pass
2. `uv run pytest tests/[scope]/ -x` — all tests pass (existing + new)
3. `make test T="[scope] --cov"` — rerun coverage and verify:
   - Excluded files no longer appear in coverage report
   - Coverage percentage reflects the new baseline
````

## Remediation Report

After implementing the coverage analysis plan, document the results with a before/after comparison. Write it to `_build/coverage/<after-timestamp>/remediation-report.md` — the results directory of the run that reflects the completed work.

### Workflow

1. **Before run** — the coverage run that triggered the analysis (already exists)
2. **Implement** — add exclusions and write tests per the coverage analysis plan
3. **After run** — capture coverage with the new tests and exclusions
4. **Write report** — compare the two runs using the template below

### Remediation Report Template

````markdown
# [Module] Coverage Remediation Report

**Runs compared:**
- **Before:** `_build/coverage/<before-timestamp>/` — baseline before test additions
- **After:** `_build/coverage/<after-timestamp>/` — after exclusions + N new tests

---

## Phase 1: Targeted Files — Plan vs Actuals

Files that were explicitly targeted by the coverage analysis, plus the overall module.

| File | Before | After | Tests Added | Plan Target |
|---|---|---|---|---|
| **module/ overall** | **X%** (covered/total) | **Y%** (covered/total) | N | ~Z% |
| `path/to/file.py` | X% (covered/total) | Y% (covered/total) | N | ~Z% |

### Observations

- **Exceeded plan:** files that beat their targets and why
- **Below plan:** files that fell short and why (e.g., hard-to-mock dependencies)
- **Overall:** summary of aggregate result vs plan target

---

## Phase 2: Full Coverage Landscape

Every file in the module in the after run, grouped by coverage tier.

### Tier: 100% Coverage

| File | Lines | Status |
|---|---|---|
| `path/to/file.py` | N | Maintained / **New** / **Improved** (X→100%) |

### Tier: 90–99% Coverage

| File | Coverage | Uncovered Lines |
|---|---|---|
| `path/to/file.py` | X% (covered/total) | N |

### Tier: 70–89% Coverage

| File | Coverage | Uncovered Lines | Gap Analysis |
|---|---|---|---|
| `path/to/file.py` | X% (covered/total) | N | Why these lines remain uncovered |

### Tier: Below 70%

| File | Coverage | Uncovered Lines | Gap Analysis |
|---|---|---|---|
| `path/to/file.py` | X% (covered/total) | N | Why these lines remain uncovered |

---

## Recommendations

### Quick wins (low effort, high impact)

| # | File | Current | Action | Expected |
|---|---|---|---|---|
| 1 | `path/to/file.py` | X% | Description of what to do | ~Y% |

### Medium effort

| # | File | Current | Action | Expected |
|---|---|---|---|---|
| 2 | `path/to/file.py` | X% | Description of what to do | ~Y% |

### Not recommended (diminishing returns)

| File | Current | Why |
|---|---|---|
| `path/to/file.py` | X% | Remaining lines are [reason] |

---

## Summary

| Metric | Before | After | Delta |
|---|---|---|---|
| Files tracked | N | N | -N (excluded) |
| Lines tracked | N | N | -N (excluded) |
| Lines covered | N | N | +N |
| **Coverage** | **X%** | **Y%** | **+Zpp** |
| Files at 100% | N | N | +N |
| Files below 70% | N | N | -N |
| New tests added | — | N | — |
````
