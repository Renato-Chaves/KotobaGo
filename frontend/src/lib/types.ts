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
  converted_input?: string; // present when the user typed romaji and it was converted
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

// Error analysis
export type ErrorType = "critical" | "grammar" | "politeness" | "unnatural" | "stylistic";

export interface ErrorItem {
  error_text: string;
  correction: string;
  type: ErrorType;
  explanation: string;
}

export interface ErrorAnalysisResponse {
  session_id: number;
  errors: ErrorItem[];
  overall_feedback: string;
  converted_input?: string; // present when romaji was converted before analysis
}

// Session summary
export interface SessionStats {
  turns: number;
  new_words_total: number;
  content_words_total: number;
  errors_by_type: Record<ErrorType, number>;
}

export interface WordEntry {
  vocab_id: number;
  word: string;
  reading: string;
  meaning: string;
}

export interface SessionSummaryResponse {
  session_id: number;
  story_id: number;
  stats: SessionStats;
  coach_note: string;
  new_words: WordEntry[];
  known_words: WordEntry[];
}

export type ErrorAnalysisMode = "on_call" | "auto";

// User profile
export interface UserProfile {
  id: number;
  native_language: string;
  target_language: string;
  jlpt_goal: string;
  ai_context: string | null;
  error_analysis_mode: ErrorAnalysisMode;
  furigana_mode: FuriganaMode;
  dark_mode: boolean;
  model_settings: Record<string, string | null> | null;
}

export interface UpdateProfileRequest {
  native_language?: string;
  jlpt_goal?: string;
  ai_context?: string;
  error_analysis_mode?: ErrorAnalysisMode;
  furigana_mode?: FuriganaMode;
  model_settings?: Record<string, string | null>;
}

export interface AvailableModelsResponse {
  models: string[];
}

// Vocabulary grid
export type VocabStatusFull = "unseen" | "introduced" | "practiced" | "mastered";

export interface VocabGridItem {
  vocab_id: number;
  word: string;
  reading: string;
  meaning: string;
  jlpt_level: string | null;
  status: VocabStatusFull;
  next_review: string | null;
  interval_days: number;
  is_due: boolean;
}

export interface VocabGridStats {
  unseen: number;
  introduced: number;
  practiced: number;
  mastered: number;
  due: number;
}

export interface VocabGridResponse {
  items: VocabGridItem[];
  total: number;
  stats: VocabGridStats;
}
