# Database Concurrency & Constraint Issues

Identified 2026-02-24 during console output review. **All issues resolved** — see fixes below.

## 1. Race condition in `add_candidate` (UNIQUE constraint violation) — RESOLVED

**File:** `app/core/database.py` — `add_candidate()`

**Problem:** The check-then-insert pattern isn't atomic across concurrent threads. The `UniqueConstraint("file_hash", "family_name", "method")` rejected the second insert.

**Fix:** Added `IntegrityError` catch on `session.flush()`. On conflict, the session rolls back and queries for the existing row, returning its ID.

## 2. Dangling foreign key in `reprocess_candidates_from_raw` — RESOLVED

**File:** `app/core/database.py` — `reprocess_candidates_from_raw()`

**Problem:** Deleted all candidates in one session scope while `card.selected_candidate_id` still referenced a now-deleted row.

**Fix:** Consolidated into a single `_session_scope` transaction. `card.selected_candidate_id` is set to `None` and flushed before candidates are deleted. New candidates are added via `_add_candidate_inline()` (no nested sessions). Auto-selection happens at the end of the same transaction.

## 3. Similar dangling FK in `clear_ai_results` — RESOLVED

**File:** `app/core/database.py` — `clear_ai_results()`

**Problem:** Deleted AI candidates while `card.selected_candidate_id` might still reference one.

**Fix:** Affected cards' `selected_candidate_id` is set to `None` and flushed *before* the `DELETE` on AI candidates. OCR re-selection happens afterward in the same transaction.

## 4. Nested/fragmented session scopes — RESOLVED

**File:** `app/core/database.py` — `reprocess_candidates_from_raw()`

**Problem:** Used three separate `_session_scope` blocks and called `add_candidate()` (which opens its own session) from within them — multiple independent transactions for what should be one atomic operation.

**Fix:** Refactored to a single `_session_scope`. Introduced `_add_candidate_inline(session, ...)` helper that performs cleaning/formatting and adds candidates within a caller-provided session (no new session scope). The public `add_candidate()` retains its own session management for external callers.
