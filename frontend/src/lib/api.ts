import type { AvailableModelsResponse, ContinueLessonResponse, ConfidenceRating, CreateLessonRequest, CreateLessonResponse, ErrorAnalysisResponse, ExportToStoryResponse, ImportPreview, ImportUrlRequest, Lesson, LessonModule, LessonSummaryResponse, SessionSummaryResponse, StartLessonResponse, StoryResponse, SwitchModuleResponse, Token, UpdateProfileRequest, UserProfile, VocabGridResponse, WordLookup } from "./types";

// In Client Components this env var is available (NEXT_PUBLIC_ prefix).
// Server Components use API_URL_INTERNAL instead.
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, { signal });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

/**
 * Like post(), but reads an NDJSON stream from the backend.
 * The backend sends `~\n` heartbeats while the LLM is working, then the
 * JSON result as the final line. This keeps the TCP connection alive for
 * slow local model generations that would otherwise trigger a NetworkError.
 */
async function postStreamed<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  const reader = res.body!.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines) {
      const t = line.trim();
      if (!t || t === "~") continue; // heartbeat
      const msg = JSON.parse(t) as Record<string, unknown>;
      if (msg.__error__) throw new Error(msg.__error__ as string);
      return msg as T;
    }
  }
  throw new Error("Stream ended without a result");
}

export const api = {
  startStory: (params: {
    user_id?: number;
    theme?: string;
    grammar_focus?: string;
    new_word_pct?: number;
  }, signal?: AbortSignal): Promise<StoryResponse> =>
    postStreamed("/story/start", { user_id: 1, ...params }, signal),

  continueStory: (
    session_id: number,
    params: { user_input: string; difficulty_hint?: string },
    signal?: AbortSignal,
  ): Promise<StoryResponse> =>
    postStreamed(`/story/continue/${session_id}`, { user_id: 1, ...params }, signal),

  lookupWord: (vocab_id: number): Promise<WordLookup> =>
    get(`/vocab/lookup/${vocab_id}?user_id=1`),

  rateWord: (vocab_id: number, rating: ConfidenceRating): Promise<{ new_status: string; interval_days: number }> =>
    post("/vocab/rate", { vocab_id, rating, user_id: 1 }),

  translateSegment: (text: string): Promise<{ translation: string }> =>
    post("/story/translate", { text, user_id: 1 }),

  analyzeErrors: (session_id: number, user_input: string): Promise<ErrorAnalysisResponse> =>
    post("/story/analyze-errors", { session_id, user_input, user_id: 1 }),

  getSessionSummary: (session_id: number): Promise<SessionSummaryResponse> =>
    post(`/story/summary/${session_id}`, { user_id: 1 }),

  getVocabGrid: (params: { status?: string; jlpt?: string } = {}): Promise<VocabGridResponse> => {
    const qs = new URLSearchParams({ user_id: "1", status: "all", jlpt: "all", ...params }).toString();
    return get(`/vocab/grid?${qs}`);
  },

  getProfile: (): Promise<UserProfile> =>
    get("/users/me?user_id=1"),

  updateProfile: (updates: UpdateProfileRequest): Promise<UserProfile> =>
    patch("/users/me?user_id=1", updates),

  tokenize: (text: string): Promise<{ tokens: Token[] }> =>
    post("/vocab/tokenize", { text, user_id: 1 }),

  getAvailableModels: (): Promise<AvailableModelsResponse> =>
    get("/users/models"),

  // -------------------------------------------------------------------------
  // Lessons
  // -------------------------------------------------------------------------

  listLessons: (): Promise<Lesson[]> =>
    get("/lessons?user_id=1"),

  startLesson: (lesson_id: number, signal?: AbortSignal): Promise<StartLessonResponse> =>
    postStreamed(`/lessons/${lesson_id}/start`, { user_id: 1 }, signal),

  continueLesson: (
    session_id: number,
    params: { user_input: string },
    signal?: AbortSignal,
  ): Promise<ContinueLessonResponse> =>
    postStreamed(`/lessons/session/${session_id}/continue`, { user_id: 1, ...params }, signal),

  switchModule: (
    session_id: number,
    target_module: LessonModule
  ): Promise<SwitchModuleResponse> =>
    post(`/lessons/session/${session_id}/switch-module`, { target_module }),

  analyzeLessonErrors: (
    session_id: number,
    user_input: string
  ): Promise<ErrorAnalysisResponse> =>
    post(`/lessons/session/${session_id}/analyze-errors`, { session_id, user_input, user_id: 1 }),

  getLessonSummary: (session_id: number): Promise<LessonSummaryResponse> =>
    post(`/lessons/session/${session_id}/summary`, { user_id: 1 }),

  exportLessonToStory: (session_id: number): Promise<ExportToStoryResponse> =>
    post(`/lessons/session/${session_id}/export-to-story`, { user_id: 1 }),

  importLessonUrl: (req: ImportUrlRequest): Promise<ImportPreview> =>
    post("/lessons/import-url", req),

  createLesson: (req: CreateLessonRequest): Promise<CreateLessonResponse> =>
    post("/lessons", req),
};
