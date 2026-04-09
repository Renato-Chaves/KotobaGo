"use client";

import { useCallback, useRef, useEffect, useState } from "react";

import { api } from "@/lib/api";
import type {
  DifficultyHint,
  ErrorAnalysisMode,
  ErrorAnalysisResponse,
  ErrorItem,
  FuriganaMode,
  SessionSummaryResponse,
  StoryResponse,
  Token,
} from "@/lib/types";
import { ContextBar } from "./ContextBar";
import { DifficultyButtons } from "./DifficultyButtons";
import { ErrorPanel } from "./ErrorPanel";
import { SessionSummaryScreen } from "./SessionSummaryScreen";
import { StoryInput } from "./StoryInput";
import { TokenSpan } from "./TokenSpan";
import { TranslationToggle } from "./TranslationToggle";
import { WordSidebar } from "./WordSidebar";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface StoryTurn {
  type: "story";
  tokens: Token[];
  choices: string[];
  contextPct: number;
  newWords: number;
  totalWords: number;
}

interface UserTurn {
  type: "user";
  text: string;
  // Error analysis — undefined = not yet run, null = loading, array = result
  errors?: ErrorItem[] | null;
  overallFeedback?: string;
}

type Turn = StoryTurn | UserTurn;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function StoryCanvas() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [furiganaMode, setFuriganaMode] = useState<FuriganaMode>("full");
  const [selectedToken, setSelectedToken] = useState<Token | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingHint, setPendingHint] = useState<DifficultyHint | null>(null);
  const [errorMode, setErrorMode] = useState<ErrorAnalysisMode>("on_call");
  const [summary, setSummary] = useState<SessionSummaryResponse | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load saved user preferences on first mount
  useEffect(() => {
    api.getProfile()
      .then((profile) => {
        setFuriganaMode(profile.furigana_mode);
        setErrorMode(profile.error_analysis_mode);
      })
      .catch(() => {}); // silently keep defaults if unavailable
  }, []);

  const latestStory = [...turns].reverse().find((t): t is StoryTurn => t.type === "story") ?? null;

  // Auto-scroll to bottom on new turns
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, loading]);

  // --- Start a new story ---

  const handleStart = useCallback(async () => {
    setLoading(true);
    setError(null);
    setTurns([]);
    setSessionId(null);
    setSelectedToken(null);
    setSummary(null);

    try {
      const res: StoryResponse = await api.startStory({ theme: "日常生活" });
      setSessionId(res.session_id);
      setTurns([toStoryTurn(res)]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start story");
    } finally {
      setLoading(false);
    }
  }, []);

  // --- Run error analysis for a specific user turn ---

  const runErrorAnalysis = useCallback(async (turnIndex: number, text: string) => {
    if (!sessionId) return;

    // Mark as loading (null = loading)
    setTurns((prev) =>
      prev.map((t, i) =>
        i === turnIndex && t.type === "user"
          ? { ...t, errors: null }
          : t
      )
    );

    try {
      const res: ErrorAnalysisResponse = await api.analyzeErrors(sessionId, text);
      setTurns((prev) =>
        prev.map((t, i) =>
          i === turnIndex && t.type === "user"
            ? { ...t, errors: res.errors, overallFeedback: res.overall_feedback }
            : t
        )
      );
    } catch {
      // On failure, reset to "not run" state so user can retry
      setTurns((prev) =>
        prev.map((t, i) =>
          i === turnIndex && t.type === "user"
            ? { ...t, errors: undefined }
            : t
        )
      );
    }
  }, [sessionId]);

  // --- Continue with user input ---

  const handleSubmit = useCallback(async (input: string) => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    setSelectedToken(null);

    // Show user message immediately, before the API responds
    const userTurnIndex = turns.length; // index this turn will have
    setTurns((prev) => [...prev, { type: "user", text: input }]);

    try {
      const res: StoryResponse = await api.continueStory(sessionId, {
        user_input: input,
        difficulty_hint: pendingHint ?? undefined,
      });
      setPendingHint(null);
      setTurns((prev) => [...prev, toStoryTurn(res)]);

      // Auto mode: run error analysis immediately after the story responds
      if (errorMode === "auto") {
        runErrorAnalysis(userTurnIndex, input);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to continue story");
      // Remove the optimistic user turn on failure
      setTurns((prev) => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  }, [sessionId, pendingHint, turns.length, errorMode, runErrorAnalysis]);

  // --- Difficulty hint — applied on the next submission ---

  const handleDifficultyHint = useCallback((hint: DifficultyHint) => {
    setPendingHint(hint);
  }, []);

  // --- Furigana toggle (cycles through 3 modes) ---

  const cycleFurigana = useCallback(() => {
    setFuriganaMode((m) => m === "full" ? "known_only" : m === "known_only" ? "none" : "full");
  }, []);

  // --- End session → fetch summary ---

  const handleEndSession = useCallback(async () => {
    if (!sessionId) return;
    setSummaryLoading(true);
    try {
      const res = await api.getSessionSummary(sessionId);
      setSummary(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load summary");
    } finally {
      setSummaryLoading(false);
    }
  }, [sessionId]);

  // ---------------------------------------------------------------------------
  // Render — session summary screen
  // ---------------------------------------------------------------------------

  if (summary) {
    return (
      <SessionSummaryScreen
        summary={summary}
        onNewStory={handleStart}
      />
    );
  }

  // ---------------------------------------------------------------------------
  // Render — empty state
  // ---------------------------------------------------------------------------

  if (turns.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-6">
        <h1 className="text-3xl font-bold tracking-tight">ことばGo</h1>
        <p className="text-zinc-400 text-sm">
          AI-generated stories calibrated to your vocabulary level
        </p>
        <button
          onClick={handleStart}
          disabled={loading}
          className="px-6 py-3 rounded-xl bg-sky-600 hover:bg-sky-500
                    text-white font-medium transition-colors
                    disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? "Generating…" : "Start Story"}
        </button>
        {error && <p className="text-red-400 text-sm">{error}</p>}
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render — chat view
  // ---------------------------------------------------------------------------

  return (
    <div className="flex min-h-screen">
      {/* --- Main chat area --- */}
      <div className="flex-1 flex flex-col max-w-2xl mx-auto px-4 py-6">

        {/* Top bar — sticky */}
        <div className="flex items-center justify-between mb-6 pb-4 border-b border-zinc-800">
          <div className="flex items-center gap-3">
            <button
              onClick={handleStart}
              className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              ← New Story
            </button>
            <a
              href="/vocab"
              className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              📚 Vocab
            </a>
            <a
              href="/profile"
              className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              ⚙ Profile
            </a>
            <button
              onClick={handleEndSession}
              disabled={summaryLoading || loading || turns.length < 3}
              className="text-xs px-2 py-1 rounded border border-zinc-700
                        text-zinc-500 hover:border-zinc-500 hover:text-zinc-300
                        transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              title="End session and see stats"
            >
              {summaryLoading ? "Loading…" : "End Session"}
            </button>
          </div>
          <div className="flex items-center gap-3">
            {/* Error mode toggle */}
            <button
              onClick={() => setErrorMode((m) => m === "on_call" ? "auto" : "on_call")}
              className="text-xs px-2 py-1 rounded border border-zinc-700
                        text-zinc-400 hover:border-zinc-500 hover:text-zinc-200
                        transition-colors"
              title="Toggle error analysis mode"
            >
              {errorMode === "auto" ? "誤り：自動" : "誤り：手動"}
            </button>
            <button
              onClick={cycleFurigana}
              className="text-xs px-2 py-1 rounded border border-zinc-700
                        text-zinc-400 hover:border-zinc-500 hover:text-zinc-200
                        transition-colors"
              title="Toggle furigana"
            >
              {furiganaMode === "full" ? "振仮名：全" : furiganaMode === "known_only" ? "振仮名：未" : "振仮名：無"}
            </button>
            {latestStory && <ContextBar usagePct={latestStory.contextPct} />}
          </div>
        </div>

        {/* Turn list */}
        <div className="flex flex-col gap-4 flex-1">
          {turns.map((turn, i) => {
            if (turn.type === "user") {
              const hasResult = turn.errors !== undefined;
              const isAnalysisLoading = turn.errors === null;
              const showErrorPanel = hasResult || isAnalysisLoading;

              return (
                <div key={i} className="flex flex-col items-end gap-1">
                  <div className="max-w-[75%] px-4 py-2.5 rounded-2xl rounded-tr-sm
                                  bg-sky-700 text-white text-base leading-relaxed">
                    {turn.text}
                  </div>

                  {/* On Call mode: show "Check" button if analysis not yet run */}
                  {errorMode === "on_call" && !hasResult && !isAnalysisLoading && (
                    <button
                      onClick={() => runErrorAnalysis(i, turn.text)}
                      className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors mr-1"
                    >
                      Check my Japanese
                    </button>
                  )}

                  {showErrorPanel && (
                    <div className="w-full max-w-[85%] mr-0">
                      <ErrorPanel
                        errors={turn.errors ?? []}
                        overallFeedback={turn.overallFeedback ?? ""}
                        loading={isAnalysisLoading}
                      />
                    </div>
                  )}
                </div>
              );
            }

            // Story turn
            const isLatest = i === turns.length - 1;
            return (
              <div key={i} className="flex flex-col gap-1">
                <div className={`text-xl leading-loose tracking-wide transition-colors
                                ${isLatest ? "text-zinc-100" : "text-zinc-500"}`}>
                  {turn.tokens.map((token, ti) => (
                    <TokenSpan
                      key={`${i}-${ti}`}
                      token={token}
                      furiganaMode={furiganaMode}
                      onSelect={setSelectedToken}
                    />
                  ))}
                </div>
                {/* Translation toggle — available on every segment */}
                <TranslationToggle
                  text={turn.tokens.map((t) => t.surface).join("")}
                />
                {/* Stats — only on latest */}
                {isLatest && (
                  <p className="text-xs text-zinc-600 mt-1">
                    {turn.newWords} new / {turn.totalWords} content words
                    {pendingHint && (
                      <span className={`ml-2 ${pendingHint === "too_hard" ? "text-red-400" : "text-emerald-400"}`}>
                        · {pendingHint === "too_hard" ? "Easier next" : "Harder next"}
                      </span>
                    )}
                  </p>
                )}
              </div>
            );
          })}

          {/* Loading indicator */}
          {loading && (
            <div className="flex gap-1.5 items-center px-2 py-3">
              <span className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-bounce [animation-delay:0ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-bounce [animation-delay:300ms]" />
            </div>
          )}

          {error && <p className="text-red-400 text-sm px-2">{error}</p>}

          {/* Scroll anchor */}
          <div ref={bottomRef} />
        </div>

        {/* Input area — pinned to bottom */}
        {!loading && latestStory && (
          <div className="mt-4 pt-4 border-t border-zinc-800">
            <StoryInput
              suggestions={latestStory.choices}
              disabled={loading}
              onSubmit={handleSubmit}
            />
            <div className="flex justify-end mt-2">
              <DifficultyButtons disabled={loading} onHint={handleDifficultyHint} />
            </div>
          </div>
        )}
      </div>

      {/* --- Sidebar — word lookup + SRS --- */}
      {selectedToken && (
        <WordSidebar
          token={selectedToken}
          onClose={() => setSelectedToken(null)}
          onRated={(vocabId, newStatus) => {
            // Update the token's status in all turns so underlines reflect the rating
            setTurns((prev) => prev.map((turn) => {
              if (turn.type !== "story") return turn;
              return {
                ...turn,
                tokens: turn.tokens.map((t) =>
                  t.vocab_id === vocabId
                    ? { ...t, status: newStatus === "mastered" || newStatus === "practiced" ? "known" : "new" }
                    : t
                ),
              };
            }));
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function toStoryTurn(res: StoryResponse): StoryTurn {
  return {
    type: "story",
    tokens: res.tokens,
    choices: res.choices,
    contextPct: res.context_usage_pct,
    newWords: res.new_word_count,
    totalWords: res.total_content_words,
  };
}
