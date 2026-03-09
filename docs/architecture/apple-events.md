# Apple Events

**Key files:**

- `app/core/apple_events.py` — Core handler layer: `NSAppleEventManager` registration, param extraction, reply dispatch helpers, JSON serialization, `_call_on_main_thread` safety wrapper (~470 lines)
- `app/gui/main_window_mixins/apple_events_mixin.py` — Mixin bridge layer: 2 properties + 14 bridge methods called on the main thread (~190 lines)

**Bundle ID:** `com.kaymakcalan.app.greetingcards`

---

## Architecture

```
AppleScript / osascript
        │  tell application id "com.kaymakcalan.app.greetingcards"
        │  [command] [parameters]
        ▼
NSAppleEventManager  (macOS AE dispatcher — always main thread)
        │
        ▼
AppleEventHandler  (NSObject subclass — app/core/apple_events.py)
  ┌──────────────────────────────────────────────────────────┐
  │  handleXxx_reply_()  methods  (one per command)          │
  │    1. Extract params via _get_text_param / _get_int_...  │
  │    2. Validate, then delegate to a dispatch helper:      │
  │       • _reply_dict() — dict result → json.dumps + reply │
  │       • _reply_str()  — raw JSON string + reply          │
  │       Both call _call_on_main_thread and handle timeout. │
  └──────────────────────────────────────────────────────────┘
        │  (main-thread dispatch via injected callable if needed)
        ▼
AppleEventsMixin  (app/gui/main_window_mixins/apple_events_mixin.py)
  ┌─────────────────────────────────────────────────────────┐
  │  *_for_script() methods — run on main thread            │
  │  Read/mutate MainWindow state, call wx UI methods        │
  │  Return plain Python dicts (no wx or AE types)          │
  └─────────────────────────────────────────────────────────┘
```

---

## Initialization

Registration happens in `main.py` in two phases:

```python
# Phase 1 — before MainLoop: register all 14 GrCd handlers
_ae_handler = register_apple_event_handlers(window, main_thread_dispatch=wx.CallAfter)
assert _ae_handler is not None          # keeps reference alive (prevents GC)

# Phase 2 — deferred until after MainLoop starts
wx.CallAfter(register_quit_handler, _ae_handler)
```

**Why two phases?** wxPython re-installs its own `aevt/quit` handler during `MainLoop()` startup. Registering our quit handler via `wx.CallAfter` ensures it runs after `MainLoop` begins, so our handler overwrites wxPython's.

**`main_thread_dispatch` parameter:** The core layer (`app/core/apple_events.py`) must not import `wx`. Instead, the GUI layer injects its main-thread dispatcher (e.g. `wx.CallAfter`) via this keyword argument. The callable is stored module-wide and used by `_call_on_main_thread()` as a safety net for non-main-thread dispatch. Tests can pass `None` (the default) or a synchronous callable.

**`ScriptingTarget` protocol:** `AppleEventHandler` types its `_window` attribute as `ScriptingTarget` (`app/core/scripting_protocol.py`), a `typing.Protocol` listing the 2 properties + 14 methods the handler calls. This keeps `apple_events.py` in the core layer with zero GUI imports — no `TYPE_CHECKING` guard needed.

**Why keep `_ae_handler` in scope?** Python's GC would collect the `NSObject` subclass instance if nothing holds a reference. The `_ae_handler` local in `main()` keeps it alive for the process lifetime.

---

## Command Reference

All commands use event class `GrCd` except `quit` (class `aevt`). Reply is always a JSON string set on the direct object (`----`) of the reply descriptor.

| **Command**       | **Event Code** | **Parameters**                                                                     | **Response Shape**                                                 | **Unit Tests** | **Bridge Tests** | **Integration Tests** |
|-------------------|----------------|------------------------------------------------------------------------------------|--------------------------------------------------------------------|----------------|------------------|-----------------------|
| load paths        | `LdPa`         | direct: `list[str]` paths                                                          | `{success, count, error?}`                                         | —              | 3                | 3                     |
| get status        | `GtSt`         | (none)                                                                             | `{is_processing, is_analyzing, loaded_count, current_model, year}` | —              | 3                | 1                     |
| reload            | `RlCd`         | (none)                                                                             | `{success, changed, error?}`                                       | 2              | 1                | 2                     |
| clear all         | `ClAl`         | (none)                                                                             | `{success, error?}`                                                | 2              | 1                | 2                     |
| get card info     | `InCd`         | direct: filename `str`                                                             | full card object (see Schemas) or `{error}`                        | —              | 2                | 3                     |
| get loaded cards  | `LsCd`         | (none)                                                                             | `[card summary, …]`                                                | —              | 1                | 1                     |
| rename card       | `RnCd`         | direct: filename; `newN`: new name; `year`: year `str`?                            | `{success, old_path, new_path, error}`                             | 3              | 4                | 3                     |
| set card name     | `StNm`         | direct: filename; `newN`: name (`""` = clear)                                      | `{success, error?}`                                                | 2†             | 4                | 2                     |
| select candidate  | `SlCa`         | direct: filename; `rank`: 1-based `int`                                            | `{success, error?}`                                                | 2†             | 3                | 3                     |
| set remove family | `StRF`         | direct: filename; `newV`: `bool`                                                   | `{success, error?}`                                                | 2†             | 2                | 2                     |
| analyze cards     | `AnCd`         | direct: filename `str`? (omit = all)                                               | `{success, count, error?}`                                         | 2              | 4                | 2                     |
| clear AI results  | `ClAi`         | direct: filename `str`? (omit = all)                                               | `{success, count, error?}`                                         | 2              | 3                | 3                     |
| get models        | `GtMo`         | (none)                                                                             | `[model entry, …]` (see Schemas)                                   | 1              | —                | 3                     |
| set model         | `StMo`         | direct: model_id `str`                                                             | `{success, error?}`                                                | 2†             | —                | 3                     |
| quit              | `aevt/quit`    | (none)                                                                             | (closes app, no reply)                                             | —              | 1                | —                     |
| *infrastructure*  | —              | param extraction, reply helpers, serialization, registration, main-thread dispatch | —                                                                  | 21‡            | —                | —                     |
| **Total**         |                |                                                                                    |                                                                    | **49**         | **51**           | **25**                |

† counted within `TestHandlerParamValidation` (9 tests covering set card name, select candidate, set remove family, set model)

‡ `TestAeKeyword`(5) + `TestParamExtraction`(5) + `TestTextListParam`(3) + `TestReplyHelpers`(3) + `TestCardSerialization`(4) + `TestCallOnMainThread`(1); `TestRegistration`(5) covers all handlers collectively

Full JSON Schema (draft 2020-12): [`content/schemas/apple-events.schema.json`](../../content/schemas/apple-events.schema.json)

---

## JSON Schemas

Response shapes in brief:

| Shape           | Fields                                                                                                                                                                                            |
|-----------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `SimpleResult`  | `success` (bool), `error`? (string)                                                                                                                                                               |
| `CountResult`   | `success`, `count` (int ≥ 0), `error`?                                                                                                                                                            |
| `RenameResult`  | `success`, `old_path`, `new_path`, `error` (strings)                                                                                                                                              |
| `StatusResult`  | `is_processing`, `is_analyzing` (bools), `loaded_count` (int ≥ 0), `current_model`, `year` (strings)                                                                                              |
| `LoadResult`    | `success`, `count` (int ≥ 0), `error`?                                                                                                                                                            |
| `CandidateInfo` | `rank` (int ≥ 1), `id` (int), `name`, `method` (`"ocr"\|"ai"`), `confidence` (`"high"\|"medium"\|"low"`)                                                                                          |
| `CardInfo`      | `filename`, `file_hash`, `file_paths` (string[]), `family_name`, `confidence`, `method`, `manual_override`, `remove_family` (bool), `ai_analyzed` (bool), `candidates` (CandidateInfo[]), `error` |
| `CardSummary`   | `filename`, `file_hash`, `family_name`, `confidence`                                                                                                                                              |
| `ModelInfo`     | `model_id`, `label`, `description`, `speed`, `quality` (ints 1–5)                                                                                                                                 |

See the JSON Schema file for strict type definitions with `"additionalProperties": false`.

---

## Threading & Main-Thread Safety

Apple Events are dispatched by macOS on the application's main run loop, which is the same thread wxPython uses. In practice, all `handle*_reply_` calls already arrive on the main thread — `_call_on_main_thread` is a safety net for the case where this ever changes.

```python
_main_thread_dispatch: Callable | None = None  # injected by register_apple_event_handlers()

def _call_on_main_thread[T](func: Callable[[], T]) -> T | None:
    if threading.current_thread() is threading.main_thread():
        return func()            # fast path — no overhead

    if _main_thread_dispatch is None:
        raise RuntimeError("No main-thread dispatcher registered")

    result_holder: list[T] = []
    done = threading.Event()
    def _wrapper():
        result_holder.append(func())
        done.set()
    _main_thread_dispatch(_wrapper)  # e.g. wx.CallAfter — injected, not imported
    if not done.wait(timeout=30):
        logger.error("_call_on_main_thread timed out after 30s")
        return None              # caller converts None → {"error": "timeout"}
    return result_holder[0] if result_holder else None
```

**Timeout:** 30 seconds. If the main thread doesn't respond (e.g. blocked modal dialog), the handler returns `{"error": "Main thread timeout"}` or `{"error": "timeout"}` depending on the command.

---

## Reply Dispatch Helpers

Most handler methods follow one of two patterns when calling the window delegate and replying to the caller. These are extracted into two static helper methods on `AppleEventHandler` to eliminate repetition:

### `_reply_dict(func, reply, *, timeout_error="Main thread timeout")`

For handlers whose window method returns a `dict`. Calls `_call_on_main_thread(func)`, then:
- **On success:** replies with `json.dumps(result)`.
- **On timeout (result is None):** replies with `json.dumps({"success": False, "error": timeout_error})`.

Used by: load paths, reload, clear all, rename card, set card name, select candidate, set remove family, analyze cards, clear AI results, set model.

The `timeout_error` keyword allows per-handler customization (e.g. rename card uses `"timeout"` instead of the default `"Main thread timeout"`).

### `_reply_str(func, reply, *, fallback="{}")`

For handlers whose inner function returns a pre-built JSON string. Calls `_call_on_main_thread(func)`, then:
- **On success:** replies with the raw string.
- **On timeout (result is None or empty):** replies with *fallback*.

Used by: get status (fallback `"{}"`), get card info (fallback `"{}"`), get loaded cards (fallback `"[]"`).

### Handlers that use neither helper

- **get models** — no window call, replies directly with `_ai_models_to_json()`.
- **quit** — no reply needed, calls `_call_on_main_thread` directly.

---

## Gotchas

### Deferred quit handler

`aevt/quit` is registered via `wx.CallAfter` *after* `MainLoop()` starts — not before. wxPython re-installs its own `aevt/quit` handler during `MainLoop()` initialization and would overwrite ours if we registered earlier. The `wx.CallAfter` call ensures our handler runs last and takes precedence.

The `_ae_handler` variable in `main()` must be held for the process lifetime. If nothing keeps a Python reference to the `NSObject` subclass instance, the garbage collector will destroy it and the handlers will stop working.

### No-wait async operations

`analyze cards` (`AnCd`) and `reload` (`RlCd`) start background operations and return immediately with `{"success": True, ...}`. They do **not** wait for the operation to complete. Callers must poll `get status` (`GtSt`) to determine when processing or analysis has finished.

### Bundle-only in practice

Apple Events routing requires a registered bundle ID. In dev mode (`uv run python main.py`) macOS typically does not route events to the process because there is no registered `.app` bundle with the expected `CFBundleIdentifier`. Test AE scripting against the built `dist/Greeting Cards.app`.

### Parameter codes

Parameter codes are 4-char big-endian integers encoded via `ae_keyword()`:

| Name          | Code         | Used by                    |
|---------------|--------------|----------------------------|
| direct object | `----`       | most commands              |
| `newN`        | new name     | rename card, set card name |
| `year`        | year string  | rename card                |
| `rank`        | 1-based rank | select candidate           |
| `newV`        | new value    | set remove family          |
