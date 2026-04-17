// Mirrors the backend TokenOut schema
export type VocabStatus = "known" | "new" | "unseen" | "lesson_example";

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

export type StoryLength = "tiny" | "short" | "medium" | "long";

export interface StoryConfig {
  temperature?: number;      // 0.0–2.0, default 0.7
  story_length?: StoryLength; // default "medium"
  new_word_pct?: number;     // 0–50, default 15
}

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
  story_config: StoryConfig | null;
}

export interface UpdateProfileRequest {
  native_language?: string;
  jlpt_goal?: string;
  ai_context?: string;
  error_analysis_mode?: ErrorAnalysisMode;
  furigana_mode?: FuriganaMode;
  model_settings?: Record<string, string | null>;
  story_config?: StoryConfig;
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

// ---------------------------------------------------------------------------
// Lessons
// ---------------------------------------------------------------------------

export interface LessonExample {
  id: string;
  japanese: string;
  reading: string;
  translation: string;
}

export interface LessonSentence {
  id: string;
  japanese: string;
  reading: string;
  translation: string;
}

export interface LessonContent {
  grammar_point: string;
  source_language: string;
  explanation: string;
  examples: LessonExample[];
  sentences: LessonSentence[];
}

export type LessonCategory = "grammar" | "vocabulary" | "conversation";

export type LessonProgressStatus = "completed" | "active" | "available" | "locked";

export interface Lesson {
  id: number;
  title: string;
  jlpt_level: string;
  grammar_point: string | null;
  category: LessonCategory;
  stage: number;
  order: number;
  content_json: LessonContent | null;
  progress_status: LessonProgressStatus;
  active_session_id: number | null;
}

// Module names matching the backend
export type LessonModule = "presentation" | "examples" | "recognition" | "conversation" | "qa";

export interface ModuleState {
  turns: number;
  seen_ids?: string[];
  scored_ids?: string[];
  exported?: boolean;
}

export interface LessonSessionMeta {
  active_module: LessonModule;
  module_history: LessonModule[];
  qa_return_module: LessonModule | null;
  modules: Record<LessonModule, ModuleState>;
}

export interface LessonSession {
  id: number;
  lesson_id: number;
  user_id: number;
  content_json: Array<{ role: "user" | "assistant"; content: string }>;
  session_meta: LessonSessionMeta;
  status: "active" | "completed" | "abandoned";
  created_at: string;
}

export interface StartLessonResponse {
  session_id: number;
  lesson_id: number;
  text: string;
  tokens: Token[];
  session_meta: LessonSessionMeta;
  choices: string[];
}

export interface ContinueLessonResponse {
  session_id: number;
  text: string;
  tokens: Token[];
  session_meta: LessonSessionMeta;
  stage_complete: boolean;
  choices: string[];   // non-empty for conversation module
}

export interface SwitchModuleResponse {
  session_id: number;
  text: string;
  tokens: Token[];
  session_meta: LessonSessionMeta;
  choices: string[];
}

export interface LessonSummaryResponse {
  session_id: number;
  lesson_id: number;
  stats_json: Record<string, unknown>;
  coach_note: string;
}

export interface ExportToStoryResponse {
  session_id: number;   // new StorySession id
}

// ---------------------------------------------------------------------------
// Lesson creation / import
// ---------------------------------------------------------------------------

export interface ImportUrlRequest {
  url?: string;
  text?: string;
}

export interface ImportPreview {
  title: string;
  grammar_point: string;
  jlpt_level: string;
  category: string;
  source_language: string;
  explanation: string;
  examples: LessonExample[];
  sentences: LessonSentence[];
}

export interface CreateLessonRequest {
  title: string;
  grammar_point?: string;
  jlpt_level: string;
  category: string;
  source_language: string;
  explanation: string;
  examples: LessonExample[];
  sentences: LessonSentence[];
}

export interface CreateLessonResponse {
  id: number;
  title: string;
}
