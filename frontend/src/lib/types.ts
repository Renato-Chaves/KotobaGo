// Mirrors the backend TokenOut schema
export type VocabStatus = "known" | "new" | "unseen";

export interface Token {
  surface: string;
  reading: string;
  pos: string;
  is_content: boolean;
  status: VocabStatus;
  vocab_id: number | null;
}

// Mirrors the backend StoryResponse schema
export interface StoryResponse {
  session_id: number;
  story_id: number;
  tokens: Token[];
  choices: string[];
  context_usage_pct: number;
  new_word_count: number;
  total_content_words: number;
}

export type FuriganaMode = "full" | "known_only" | "none";
export type DifficultyHint = "too_hard" | "too_easy";
export type ConfidenceRating = "again" | "hard" | "good" | "easy";

export interface WordLookup {
  vocab_id: number;
  word: string;
  reading: string;
  meaning: string;
  jlpt_level: string | null;
  explanation: string;
  jisho_url: string;
  user_status: string;
  next_review: string | null;
}
