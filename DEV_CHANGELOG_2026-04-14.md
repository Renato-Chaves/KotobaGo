# Development Change Log — 2026-04-14

This file records all changes implemented in the current working set before the next commit.

## Scope
- L4 lesson map implementation
- Lesson flow/quality fixes (examples, recognition, practice)
- Lesson progress/status wiring from backend to frontend

---

## 1) Backend changes

### [backend/routes/lessons.py](backend/routes/lessons.py)

#### Lessons list: progress metadata for map UI
- Added query param support: `user_id` via `Query(default=1)`.
- Extended `LessonOut` with:
  - `progress_status`
  - `active_session_id`
- `GET /lessons` now computes per-user per-lesson status by category:
  - `completed`
  - `active`
  - `available`
  - `locked`
- Returns the most recent active session ID per lesson when available.

#### Lesson token annotation improvements
- `_tokenize_lesson_text(...)` now accepts optional `lesson` context.
- Added `_annotate_lesson_targets(...)` second pass to mark grammar target tokens as `lesson_example`.
- Current grammar-target highlight for N1のN2 lessons marks `の`.

#### Deterministic examples handling (quality/stability)
- Added `_continue_examples_deterministic(...)`.
- Added `_build_examples_prompt(...)`.
- For `examples` module in `continue_lesson`:
  - Uses authored examples in deterministic sequence.
  - Avoids unstable generation quality.
  - Marks section complete after threshold and includes explicit progression message.

#### Deterministic recognition handling (quality/stability)
- Added `_continue_recognition_deterministic(...)`.
- Added `_build_recognition_prompt(...)`.
- For `recognition` module in `continue_lesson`:
  - Uses authored lesson sentences only.
  - Includes translation hint in prompt.
  - Uses fill-in format for target particle.
  - Validates response and returns concise correction/confirmation.
  - Tracks pending prompt state (`pending_sentence_id`, `expected_answer`).

#### Module switching behavior
- `_do_switch(...)` now has deterministic opening behavior for:
  - `examples`
  - `recognition`
- Keeps LLM-based switch behavior for other modules.

#### Start/continue/switch tokenization updates
- `start_lesson`, `continue_lesson`, and `_do_switch` now pass `lesson` into tokenization so lesson-target highlight can apply immediately.

---

### [backend/core/modules/conversation.py](backend/core/modules/conversation.py)

#### Practice output tightened for N5
- Prompt changed to enforce simpler Japanese output.
- Segment size reduced from longer output to **1–2 short sentences**.
- Added explicit constraints:
  - N5-friendly vocab/grammar only
  - avoid advanced kanji/expressions
  - prefer kana or very common beginner kanji
  - short dialogue choices
- JSON output example updated accordingly (`story_text` reflects 1–2 short sentences).

---

## 2) Frontend changes

### [frontend/src/lib/types.ts](frontend/src/lib/types.ts)
- Added `LessonProgressStatus` union:
  - `"completed" | "active" | "available" | "locked"`
- Extended `Lesson` type with:
  - `progress_status`
  - `active_session_id`

### [frontend/src/lib/api.ts](frontend/src/lib/api.ts)
- Updated `listLessons()` to request user-specific progress:
  - from `/lessons`
  - to `/lessons?user_id=1`

---

### [frontend/src/app/lessons/page.tsx](frontend/src/app/lessons/page.tsx) *(new)*
- Added Lessons page shell.
- Added category tabs:
  - Grammar
  - Vocabulary
  - Conversation
- Loads lessons from API and filters by active tab.
- Handles loading/error/empty states.
- Launch action respects locked state and navigates to lesson session.

### [frontend/src/components/lesson/LessonMap.tsx](frontend/src/components/lesson/LessonMap.tsx) *(new)*
- Added zig-zag lesson map layout.
- Added cubic-bezier style SVG spline path behind lesson nodes.
- Node status visuals:
  - completed
  - active
  - available
  - locked
- Added inline lesson detail card on node selection.
- Added Start/Continue/Start again action logic by node status.

---

### [frontend/src/components/lesson/LessonCanvas.tsx](frontend/src/components/lesson/LessonCanvas.tsx)

#### Section progression UX
- Added explicit next-section prompt after stage completion:
  - **Finish section → next module**
  - **Continue examples/section**
- Added helper `getNextModule(...)` for progression order:
  - presentation → examples → recognition → conversation

#### Rendering fixes
- `JAPANESE_MODULES` narrowed to only `conversation`.
- Examples/recognition now render as plain text (prevents broken tokenized mixed-language display).

#### Misc
- Tailwind utility cleanup (`flex-shrink-0` → `shrink-0`) to satisfy lint.

---

### [frontend/src/components/story/TokenSpan.tsx](frontend/src/components/story/TokenSpan.tsx)
- Updated underline logic so `lesson_example` highlighting also applies to non-content tokens (e.g., particles like `の`).
- Keeps standard behavior for `unseen`, `new`, and `known` statuses.

---

## 3) Validation
- Ran error checks on all changed backend/frontend files.
- No compile/lint errors remain in the touched files.

---

## 4) Working tree status (related changes)
Current modified/new files covered by this log:
- [backend/core/modules/conversation.py](backend/core/modules/conversation.py)
- [backend/routes/lessons.py](backend/routes/lessons.py)
- [frontend/src/components/lesson/LessonCanvas.tsx](frontend/src/components/lesson/LessonCanvas.tsx)
- [frontend/src/components/story/TokenSpan.tsx](frontend/src/components/story/TokenSpan.tsx)
- [frontend/src/lib/api.ts](frontend/src/lib/api.ts)
- [frontend/src/lib/types.ts](frontend/src/lib/types.ts)
- [frontend/src/app/lessons/page.tsx](frontend/src/app/lessons/page.tsx)
- [frontend/src/components/lesson/LessonMap.tsx](frontend/src/components/lesson/LessonMap.tsx)

---

## Notes
- This log documents uncommitted changes made after commit `31e17b7`.
- Recommended next step: split into two commits:
  1) L4 lesson map/page/progress wiring
  2) lesson flow and quality fixes

---

## 5) Follow-up fixes (same day)

### Backend module follow-up: [backend/core/modules/conversation.py](backend/core/modules/conversation.py)

- Fixed backend startup crash caused by malformed JSON f-string in the prompt template.
- Corrected JSON format example string escaping so Uvicorn can import the module cleanly.

### Backend route follow-up: [backend/routes/lessons.py](backend/routes/lessons.py)

#### Presentation stability

- Added deterministic presentation continuation handling:
  - `_continue_presentation_deterministic(...)`
  - `_build_presentation_opening(...)`
- Purpose: prevent low-quality/hallucinated examples during intro follow-ups.

#### Examples improvements

- Updated deterministic examples to avoid repeating authored examples in a tight loop after exhaustion.
- Added controlled bonus examples pool (including anime-friendly entries) when authored list is fully consumed.
- Kept explicit section progression prompt to Recognition.

#### Recognition improvements

- Recognition deterministic path is async and now converts romaji-heavy answers before evaluation.
- Added closer correctness checks for:
  - particle-only answers
  - full-sentence answers (including kanji/kana variants)
  - “close” vs “wrong” feedback
- Added recognition state fields to improve matching:
  - `expected_prefix`
  - `expected_suffix`
- Feedback now surfaces converted text when romaji was interpreted.

#### Practice contamination fix

- Conversation generation now trims prior module history context using `conversation_start_index`.
- Goal: prevent recognition text from leaking into conversation output and producing broken concatenated responses.

### Frontend follow-up: [frontend/src/components/lesson/LessonCanvas.tsx](frontend/src/components/lesson/LessonCanvas.tsx)

- Added safe rendering fallback for conversation turns containing Latin text:
  - if detected, render plain text instead of token-span Japanese rendering.
- Purpose: avoid visually broken joined output in edge cases where non-Japanese text appears.

### Runtime verification after follow-up fixes

- Backend log checked after reloads; syntax/import crash resolved.
- Manual endpoint smoke tests executed successfully:
  - `/health`
  - `POST /lessons/{id}/start`
  - recognition flow with romaji input conversion + evaluation
