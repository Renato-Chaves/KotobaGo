import type { ConfidenceRating, ErrorAnalysisResponse, SessionSummaryResponse, StoryResponse, UpdateProfileRequest, UserProfile, VocabGridResponse, WordLookup } from "./types";

// In Client Components this env var is available (NEXT_PUBLIC_ prefix).
// Server Components use API_URL_INTERNAL instead.
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`);
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

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  startStory: (params: {
    user_id?: number;
    theme?: string;
    grammar_focus?: string;
    new_word_pct?: number;
  }): Promise<StoryResponse> =>
    post("/story/start", { user_id: 1, ...params }),

  continueStory: (
    session_id: number,
    params: { user_input: string; difficulty_hint?: string }
  ): Promise<StoryResponse> =>
    post(`/story/continue/${session_id}`, { user_id: 1, ...params }),

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
};
