# KotobaGo — Product Plan

This file tracks what has been built and what is planned. Planned items are rough ideas — each needs a design pass before implementation begins.

---

## Delivered

### Phase 1 — Core story loop
Interactive story generation calibrated to user JLPT level. Vocab tokenization with MeCab/fugashi. Vocabulary tracking (unseen → introduced → practiced → mastered). Basic story start + continue routes.

### Phase 2 — Chat-style UI
Bubble-based story canvas. Furigana overlay (full / new-only / none, toggle during session). Clickable tokens for inline word lookup. Choices rendered as buttons.

### Phase 3 — N5 vocab seed + story annotation fix
JLPT N5 vocabulary seeded into the database. Token annotation now correctly links story words to vocab IDs.

### Phase 4 — Dictionary sidebar, SM-2 SRS, translation toggle
Slide-in dictionary sidebar on token tap (reading, meaning, JLPT level, Jisho link). SM-2 spaced repetition: confidence rating after each word, next-review scheduling, due words injected into story prompts. Per-segment translation toggle (hide/show translation without losing story state).

### Phase 5 — Session coaching, profile settings, vocab grid
Post-session summary with coach note and per-word review. Profile page: JLPT goal, native language, AI context paragraph, error analysis mode (on-call vs auto), furigana default. Vocabulary grid with filter by status/JLPT.

### Phase 6 — Romaji handling, model overrides, story context
Romaji-to-Japanese conversion before error analysis. Per-task Ollama model overrides in profile. Story brief (narrative anchor JSON) generated at story start to keep the LLM coherent across turns.

### Phase 7 — Story prompt config in profile
User-tunable story generation settings exposed on the profile page: temperature (0.0–2.0), segment length (Tiny 1–2 / Short 3–5 / Medium 5–8 / Long 8–12 sentences), default new-word percentage (0–50%). Temperature is wired through all three LLM providers. Settings persist to DB and apply from the next story turn.

---

## Planned

> Items below are ideas, not commitments. Each needs a design pass before implementation.

---

### Scripted Conversation Mode (Lesson Mode)

**Concept:** The teacher/author pastes in a scripted dialogue (e.g. a textbook conversation like the Tanaka / Silva gift exchange), and the app turns it into an interactive practice session. The AI guides the user through the conversation, playing one role while the user plays the other, line by line. The user types or selects their response at each beat; the AI checks it against the expected register, accepts close-enough answers, and keeps moving forward until the whole script has been covered.

**Why it matters:** Free-form story generation is good for exploration, but beginners often need a fixed target — a conversation they know exists, with grammar and vocab they're currently studying. Scripted mode bridges textbook material and active production practice.

**Key design questions:**
- How does the author mark which lines belong to each role? (plain alternating turns, character tags, something else?)
- What counts as a "close enough" response — exact match, semantic match, or let the model judge?
- Does the session end when the script is exhausted, or loop / branch?
- How does vocab tracking interact — new words in the script should still get introduced/reviewed.
- Should the script be stored as a reusable Lesson object, or is it one-off per session?

**Rough implementation sketch:**
- New `Lesson` session type (separate from free-form story sessions) with its own DB table and API routes.
- Script stored as a sequence of `{role, text}` turns; one role is "user", the other is "npc".
- NPC turns are displayed directly (tokenized, with furigana); user turns become the prompt the user must respond to.
- Error analysis compares user response to the expected line and gives targeted feedback.
- Session summary shows how much of the script was covered and which lines needed corrections.

---

### Vocabulary Import (Anki / jpdb / custom list)

**Concept:** Let users seed their vocab list from an Anki export, a jpdb.io export, or a plain word list. Words already known skip the "introduced" stage and start as practiced/mastered, so the story generator doesn't waste turns on them.

---

### Grammar Focus Mode

**Concept:** When starting a story, the user optionally picks a grammar point (e.g. て-form, conditionals, keigo). The system prompt reinforces that structure across the session, and the coach note specifically comments on it.

---

### Multi-user / Profiles

**Concept:** Support more than one user profile on the same local instance, so a household or a teacher/student pair can each have their own vocab state and story history. Currently `user_id` is hardcoded to 1 everywhere.

---

### Story History & Resume

**Concept:** A story library page listing past sessions with their title, date, and status (active / completed / abandoned). Users can resume an active session or re-read a completed one.

---

### Lesson Mode

**Concept:** The teacher authors a structured grammar lesson in any language. When a user starts it, the AI presents the content in the user's selected native language and runs a staged interactive session: concept introduction → worked examples → passive recognition → conversation practice. Each stage is powered by a focused AI module. The user can skip or revisit any stage at any time, ask questions mid-lesson, or request more examples on demand. The lesson ends with a mini-story; the user can export it to free-form story mode where it continues without the lesson overhead.

**Example lesson content (の particle):**

```yaml
grammar_point: N1のN2
source_language: pt
explanation: "O の liga dois substantivos, onde N1 modifica N2 (como 'de' em português)..."
examples:
  - { id: ex_1, japanese: "もりのくま", translation: "urso da floresta" }
  - { id: ex_2, japanese: "にほんのたべもの", translation: "comida japonesa" }
sentences:
  - { id: s_1, japanese: "ブラジルのたべものはおいしい！", translation: "Comida brasileira é gostosa!" }
```

#### Language handling

Lessons are authored in any language — the `source_language` field flags what language the stored explanation is written in. The presentation module never displays stored explanations directly; it passes them as context/notes to the AI and instructs it to re-explain in `user.native_language`. One lesson record serves all learner languages with no per-language translation stored.

#### Module architecture

Each teaching function is an independent module with its own prompt template, state shape, and input/output contract. The lesson orchestrates them in sequence, but they are individually reusable in other contexts (e.g. the Recognition module could be dropped into an SRS drill page; the Presentation module could power an on-demand grammar reference).

```text
backend/core/modules/
  presentation.py   — explains the concept conversationally in user's native language
  examples.py       — generates and extends examples; tracks which have been shown
  recognition.py    — fill-in-blank / is-this-correct; exclusively from authored sentences
  conversation.py   — mini-story constrained to use the target grammar (wraps story_builder.py)
  qa.py             — meta-question handling; answers questions, returns to origin stage
```

Each module exports `build_prompt(lesson, user, module_state)` and owns its slice of `session_meta["modules"][module_name]`. The lesson route reads `session_meta["active_module"]` and delegates each turn. Switching stages is just updating that field.

#### Stage flow and navigation

Stages are linear by recommendation but freely navigable — all are reachable at all times, none are locked.

```text
[📖 Intro] → [💡 Examples] → [✅ Recognition] → [💬 Practice]
    ↑______________↑__________________↑________________↑
                  (freely navigable in any direction)
```

Two UI elements share the same `active_module` / `module_history` state:

- **Top progress bar** (horizontal stepper, always visible) — read-only position indicator
- **Sidebar `StageNav`** — interactive: clickable chips to jump stages, visited/active/unvisited states, "Reset this stage" button per stage

State is preserved per module when the user jumps away and returns.

`session_meta` structure:

```json
{
  "active_module": "examples",
  "module_history": ["presentation", "examples"],
  "qa_return_module": null,
  "modules": {
    "presentation": { "turns": 0 },
    "examples": { "seen_ids": ["ex_1", "ex_2"], "turns": 4 },
    "recognition": { "scored_ids": [], "turns": 0 },
    "conversation": { "turns": 0, "exported": false }
  }
}
```

#### Q&A flow

At any moment the user can ask a meta-question in any language. This activates the `qa` module temporarily (`qa_return_module` records where to resume). The AI answers, then returns on the next turn. Same pattern as all other modules — no special-casing.

#### Examples module — "give me more"

At the bottom of the examples stage, two buttons appear: **See more examples** (AI generates new ones using the authored pattern + `ai_context` interests, avoiding already-shown examples) and **Continue to Recognition**. Progression is explicit but never forced.

#### Recognition module

Exercises are generated **exclusively from the lesson's authored sentences** — no AI invention. This prevents hallucination on learning material.

Exercise types: fill-in-blank, is-this-correct (pick the valid option), pattern spotting. No SRS integration for recognition results in this phase.

#### Conversation practice and export

The mini-story is self-contained in the lesson session — no `Story` or `StorySession` DB record is created during the lesson.

`POST /lessons/session/{id}/export-to-story` when the user wants to continue:

1. Extracts the last N conversation turns
2. Creates a real `Story` + `StorySession` with those turns as initial history
3. Injects a **hard grammar constraint** into the story brief: `"REQUIRED: use [grammar_point] naturally throughout this story"` — makes lesson-exported stories feel purposefully different from free-form ones
4. Returns `{ "session_id" }` — frontend navigates to `/story`

Words introduced during the lesson are already in SRS and appear naturally in the new story's `confident_vocab` / `fragile_vocab`.

#### Stage completion feedback

When the user completes a stage, a brief celebratory prompt appears in the chat canvas — "Stage cleared! ✓" with a subtle animation. No XP or points yet; the hook is designed in for a future retention pass (XP, streaks, badges) without code changes.

#### Token highlighting for lesson examples

Add `"lesson_example"` to the `VocabStatus` union. A second annotation pass marks tokens whose surface matches an authored example or sentence. One new CSS class in `TokenSpan.tsx` (amber underline). No structural frontend changes.

#### DB additions

Extend the existing stub `Lesson` table (migration via `init_db()` `ALTER TABLE` pattern):

- `content_json JSON` — structured content (grammar_point, source_language, explanation, examples[], sentences[])
- `source_language STRING` — language the explanation is written in

New tables: `LessonSession` (mirrors `StorySession`) and `LessonSessionSummary` (mirrors `SessionSummary`).

#### API routes (`backend/routes/lessons.py` — new file)

| Method | Path                                    | Purpose                                         |
| ------ | --------------------------------------- | ----------------------------------------------- |
| GET    | `/lessons`                              | List all lessons grouped by JLPT / stage        |
| POST   | `/lessons/import-url`                   | Fetch URL, extract structure, return preview    |
| POST   | `/lessons/{id}/start`                   | Start a lesson session, enter Presentation      |
| POST   | `/lessons/session/{id}/continue`        | Continue current module                         |
| POST   | `/lessons/session/{id}/switch-module`   | Jump to a specific module (skip/revisit)        |
| POST   | `/lessons/session/{id}/analyze-errors`  | Error analysis (reuses `error_analyzer.py`)     |
| POST   | `/lessons/session/{id}/summary`         | Generate coach note, finalize session           |
| POST   | `/lessons/session/{id}/export-to-story` | Export conversation turns to a new StorySession |

#### Frontend

New files:

- `app/lessons/page.tsx` — lesson stage-select map
- `app/lessons/new/page.tsx` — lesson creation / URL import page
- `app/lessons/[id]/page.tsx` — lesson session shell
- `components/lesson/LessonCanvas.tsx` — mirrors `StoryCanvas`; top progress bar + sidebar `StageNav`; no difficulty buttons
- `components/lesson/StageNav.tsx` — sidebar with clickable stage chips and per-stage reset
- `components/lesson/LessonMap.tsx` — zig-zag stage-select map
- `components/lesson/LessonImportForm.tsx` — URL import form with source suggestion cards

Reused unchanged: `TokenSpan`, `StoryInput`, `ErrorPanel`, `TranslationToggle`, `WordSidebar`, `SessionSummaryScreen`.

Navigation: add "Lessons →" link to `app/page.tsx`.

#### Lesson stage-select page (`/lessons`)

Duolingo-inspired map with a **zig-zag node arrangement**. Lessons alternate left–right as you scroll down (e.g. 25% / 75% / 25% / 75% of container width), connected by a smooth SVG cubic bezier spline rendered behind the nodes. The spline uses the app's accent color with an optional subtle glow.

Node states: completed (filled, checkmark, full color) / available (outlined, pulse animation, clickable) / not yet started (dimmed, visible).

Tabs at the top separate categories: **Grammar**, **Vocabulary**, **Conversation** (extensible). Each tab has its own independent map ordered by `stage` and `order` columns. Clicking a node opens an inline detail card with "Start / Continue" — no separate lesson detail page.

#### Lesson creation page (`/lessons/new`)

Two-panel layout:

Left panel — tabbed import form:

- **URL tab**: text field + "Import" → LLM extraction → editable review form (title, jlpt_level, grammar_point, explanation, examples list, sentences list) → "Save Lesson"
- **Paste tab**: textarea → same extraction → same review form
- **Manual tab**: structured markdown editor with front matter + section format

Right panel — source suggestion cards (always visible):

- **Tofugu card**: narrative explanations, 126+ grammar points — recommended primary source
- **Wasabi card**: structured reference, 92 lessons, includes furigana — secondary source

Clicking a card pre-fills the URL field with the source's grammar index. Author browses to a specific lesson, copies the URL, pastes it back.

#### Lesson authoring sources

**Primary: Tofugu** (`tofugu.com/japanese-grammar/`) — more memorable, metaphor-driven explanations, better model to work from when rewriting commercially. **Secondary: Wasabi** (`wasabi-jpn.com/magazine/japanese-grammar/`) — more structural, includes furigana, good fallback for points Tofugu doesn't cover. Both use standard copyright.

#### Content licensing

| Source          | License         | Personal/portfolio   | Commercial              |
| --------------- | --------------- | -------------------- | ----------------------- |
| Tofugu          | Standard ©      | Fine                 | Needs permission        |
| Wasabi          | Standard ©      | Fine                 | Needs permission        |
| Tae Kim's Guide | CC BY-NC-SA 3.0 | Fine                 | Blocked by NC clause    |
| Wikibooks       | CC BY-SA        | Fine                 | Forces app open-source  |
| JLPT Sensei     | Standard ©      | Risky                | Not permitted           |
| **Tatoeba**     | **CC0**         | **Fine**             | **Fine**                |

Grammar concepts and JLPT grammar point lists are facts about language — not copyrightable. Example sentences and written explanations are.

**Commercial path (when needed):** rewrite lessons one-by-one using Tofugu/Wasabi as a teaching model, replacing extracted text with original explanations and Tatoeba-sourced example sentences. The URL import workflow and DB schema stay identical — only the content origin changes.

#### Out of scope for this phase

- Per-user lesson completion tracking across sessions
- Curriculum progression / "unlock next lesson" logic
- Morphological variant matching for highlights (exact surface match only)
- Recognition results feeding into SRS
- Multiple users
- XP / streaks / badges (hook is designed in, implementation deferred)

#### Implementation phases

```text
L1 (foundation)
  └─ L2 (backend routes)
       ├─ L3 (lesson canvas)   ← most valuable, ship first
       ├─ L4 (lesson map)
       └─ L5 (lesson creation)
            └─ L6 (export + polish)
```

##### L1 — Foundation *(no UI, everything depends on this)*

- `backend/db/models.py` — extend `Lesson` with `content_json` + `source_language`; add `LessonSession` + `LessonSessionSummary`; `init_db()` migration
- `backend/core/tokenizer.py` — add `"lesson_example"` to `VocabStatus`
- `backend/core/llm.py` — add `"lesson"` to `TaskType`
- `backend/db/seed/lessons/no_particle.py` — seed the の particle lesson
- `frontend/src/lib/types.ts` + `api.ts` — lesson types and API methods

Verification: `init_db()` runs cleanly, seed inserts, no import errors in `/docs`.

##### L2 — Module system + backend routes *(testable via Swagger)*

- `backend/core/modules/` — all 5 modules (`presentation`, `examples`, `recognition`, `conversation`, `qa`)
- `backend/routes/lessons.py` — `start`, `continue`, `switch-module`, `analyze-errors`, `summary`
- `main.py` — register the router

Verification: drive a full session through Swagger — start, continue through each stage, switch modules, generate summary.

##### L3 — Lesson session UI *(core UX, reuses most of StoryCanvas)*

- `components/lesson/LessonCanvas.tsx` — session canvas
- `components/lesson/StageNav.tsx` — sidebar stage chips + reset
- `components/story/TokenSpan.tsx` — add `lesson_example` amber underline style
- `app/lessons/[id]/page.tsx` — shell page

Verification: complete a full session end-to-end — all 4 stages, Q&A, stage jump, stage reset.

##### L4 — Lesson map page

- `components/lesson/LessonMap.tsx` — SVG zig-zag with cubic bezier spline, node states, inline detail card
- `app/lessons/page.tsx` — category tabs + map
- `app/page.tsx` — add "Lessons →" link

Verification: map renders with seeded lesson, node states reflect session history, clicking opens detail card, "Start" navigates to session.

##### L5 — Lesson creation page

- `POST /lessons/import-url` — fetch URL, LLM extraction, return structured preview
- `components/lesson/LessonImportForm.tsx` — tabbed form (URL / Paste / Manual) + source suggestion cards
- `app/lessons/new/page.tsx` — two-panel layout

Verification: import the の particle lesson from a Tofugu URL, review extracted JSON, edit a field, save — confirm it appears on the lesson map.

##### L6 — Export to story + stage completion polish

- `POST /lessons/session/{id}/export-to-story` — creates `StorySession` with hard grammar constraint
- Export button in `LessonCanvas` conversation stage
- "Stage cleared! ✓" animation on stage completion

Verification: complete conversation stage, click "Take to Story →", confirm `/story` opens with grammar constraint in the brief.

---
