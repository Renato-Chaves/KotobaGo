# KotobaGo

A local-first, AI-powered Japanese language learning app built around the **comprehensible input** method (Krashen's i+1). Generates interactive stories calibrated to your exact vocabulary level, with a non-intrusive dictionary and spaced repetition built in.

---

## Architecture Overview

```
┌──────────────────────────────────────────┐
│           Next.js Frontend               │
│  (UI, story canvas, sidebar, progress)   │
└──────────────────┬───────────────────────┘
                   │ HTTP / WebSocket
┌──────────────────▼───────────────────────┐
│           FastAPI Backend                │
│  (business logic, tokenization, SRS)     │
└────────┬──────────────┬──────────────────┘
         │              │            
┌────────▼───┐  ┌───────▼──────┐  ┌──────────────┐
│  Ollama    │  │   SQLite     │  │ MeCab/Fugashi│
│  (LLM)     │  │   (data)     │  │ (tokenizer)  │
└────────────┘  └──────────────┘  └──────────────┘
```

The frontend and backend run in separate Docker containers and communicate over HTTP. A third container runs Ollama for local LLM inference. All persistent data lives in a SQLite file volume-mounted from the host.

---

## Stack & Dependency Rationale

### Infrastructure

| Tool | Purpose | Why this over alternatives |
|------|---------|---------------------------|
| **Docker Compose** | Orchestrates frontend + backend + Ollama as one system | Single `docker compose up` runs everything; GPU passthrough for Ollama is well-supported |
| **SQLite** | Local database | Local-first app with a single user — no need for a server DB. SQLAlchemy abstracts it so migrating to Postgres later is straightforward |

### Backend (`/backend`)

| Library | Purpose | Why this over alternatives |
|---------|---------|---------------------------|
| **FastAPI** | Web framework + REST API | Native async, automatic OpenAPI docs, Pydantic validation out of the box. Faster to write than Flask, more pythonic than Django for an API-only backend |
| **Uvicorn** | ASGI server that runs FastAPI | The standard production-grade server for FastAPI. `[standard]` extra adds websocket support and faster event loop (uvloop) |
| **SQLAlchemy 2.0** | ORM + database abstraction | Modern async ORM. Version 2.0 has a cleaner API than 1.x. Lets us swap SQLite for Postgres without touching business logic |
| **fugashi + unidic-lite** | Japanese tokenizer (MeCab wrapper) | MeCab is the industry standard for Japanese morphological analysis. `fugashi` is the most maintained Python binding. `unidic-lite` is a smaller dictionary bundled directly — avoids a separate system-level install |
| **httpx** | Async HTTP client | Used to call the Ollama API. `httpx` is async-native (unlike `requests`) which is important in a FastAPI async context |
| **python-dotenv** | Load `.env` file into environment | Keeps API keys out of code. Standard practice; FastAPI doesn't have built-in env loading |
| **anthropic** | Official Anthropic SDK | Typed client for Claude API, used as LLM fallback when Ollama is unavailable or a task benefits from a larger model |
| **openai** | Official OpenAI SDK | Optional LLM fallback. Same LLM abstraction layer routes to this when configured |

## LLM Abstraction Layer

All AI calls go through two classes in `backend/core/llm.py`:

- **`LLMClient`** — knows *how* to talk to one provider (Ollama, Anthropic, OpenAI). Single `chat(system, messages)` method regardless of provider.
- **`LLMRouter`** — knows *which* provider to use per task. Routes story generation, error analysis, and context compression to Ollama (local). Coach notes can optionally route to a cloud API for better prose quality via `COACH_NOTE_SOURCE` env var.

Routes and business logic only ever call `router.route(task, system, messages)` — they never know which model is running.

## Tokenizer Pipeline

Every piece of Japanese text passes through `backend/core/tokenizer.py` before reaching the frontend:

```
Raw AI text
    ↓
fugashi (MeCab + unidic-lite) tokenizes
    → ["私", "は", "学生", "です"]
    ↓
Each token gets: surface, reading (hiragana), part-of-speech, is_content flag
    ↓
Content tokens (nouns, verbs, adjectives…) checked against user_vocab in DB
    ↓
Annotated JSON returned:
{
  "tokens": [
    { "surface": "私",  "reading": "わたくし", "pos": "代名詞", "is_content": true,  "status": "known",  "vocab_id": 1  },
    { "surface": "は",  "reading": "は",       "pos": "助詞",   "is_content": false, "status": "unseen", "vocab_id": null },
    { "surface": "学生","reading": "がくせい",  "pos": "名詞",   "is_content": true,  "status": "new",    "vocab_id": 42 }
  ]
}
    ↓
Frontend renders each token as a selectable <span>
with underline style based on status, furigana based on user setting
```

**Vocab status mapping:**

- `unseen` — not in user's vocab list at all → solid underline (brand new word)
- `new` — introduced but not yet practiced → faint underline
- `known` — practiced or mastered → no underline

### Frontend (`/frontend`)

| Library | Purpose | Why this over alternatives |
|---------|---------|---------------------------|
| **Next.js** | React framework | App Router gives us server components, streaming, and file-based routing. Overkill-free for this app, and portfolio-relevant |
| **TypeScript** | Type safety | Catches token shape mismatches at compile time — critical since we're passing annotated JSON between backend and frontend |

---

## Running Locally

```bash
cp .env.example .env
# Edit .env if you want to use a cloud LLM instead of local Ollama

docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8001
- Backend docs: http://localhost:8001/docs
- Ollama: http://localhost:11434

---

## Project Structure

```
KotobaGo/
├── docker-compose.yml
├── .env.example
├── frontend/                  ← Next.js app
│   ├── Dockerfile
│   └── src/
├── backend/                   ← FastAPI app
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── core/
│   │   ├── llm.py             ← LLM abstraction (Ollama / Claude / OpenAI)
│   │   ├── tokenizer.py       ← MeCab wrapper
│   │   ├── srs.py             ← SM-2 spaced repetition algorithm
│   │   ├── furigana.py        ← Furigana injection
│   │   └── context.py         ← Context window tracking + compression
│   ├── routes/
│   │   ├── story.py
│   │   ├── vocab.py
│   │   ├── lessons.py
│   │   ├── profile.py
│   │   └── summary.py
│   └── db/
│       ├── models.py          ← SQLAlchemy models
│       └── seed/              ← JLPT N5–N1 vocab seed data
└── data/                      ← SQLite file (gitignored, volume-mounted)
```
