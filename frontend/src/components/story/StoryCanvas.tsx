"use client";

import { useCallback, useState } from "react";

import { api } from "@/lib/api";
import type { DifficultyHint, FuriganaMode, StoryResponse, Token } from "@/lib/types";
import { ChoiceButtons } from "./ChoiceButtons";
import { ContextBar } from "./ContextBar";
import { DifficultyButtons } from "./DifficultyButtons";
import { TokenSpan } from "./TokenSpan";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface StorySegment {
  tokens: Token[];
  choices: string[];
  contextPct: number;
  newWords: number;
  totalWords: number;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function StoryCanvas() {
  const [segments, setSegments] = useState<StorySegment[]>([]);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [furiganaMode, setFuriganaMode] = useState<FuriganaMode>("full");
  const [selectedToken, setSelectedToken] = useState<Token | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingHint, setPendingHint] = useState<DifficultyHint | null>(null);

  const latestSegment = segments[segments.length - 1] ?? null;

  // --- Start a new story ---

  const handleStart = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSegments([]);
    setSessionId(null);
    setSelectedToken(null);

    try {
      const res: StoryResponse = await api.startStory({ theme: "日常生活" });
      setSessionId(res.session_id);
      setSegments([toSegment(res)]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start story");
    } finally {
      setLoading(false);
    }
  }, []);

  // --- Continue after a choice ---

  const handleChoice = useCallback(async (choice: string) => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    setSelectedToken(null);

    try {
      const res: StoryResponse = await api.continueStory(sessionId, {
        user_input: choice,
        difficulty_hint: pendingHint ?? undefined,
      });
      setPendingHint(null);
      setSegments((prev) => [...prev, toSegment(res)]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to continue story");
    } finally {
      setLoading(false);
    }
  }, [sessionId, pendingHint]);

  // --- Difficulty hint — applied on the NEXT choice ---

  const handleDifficultyHint = useCallback((hint: DifficultyHint) => {
    setPendingHint(hint);
  }, []);

  // --- Furigana toggle (cycles through 3 modes) ---

  const cycleFurigana = useCallback(() => {
    setFuriganaMode((m) => m === "full" ? "known_only" : m === "known_only" ? "none" : "full");
  }, []);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (segments.length === 0) {
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

  return (
    <div className="flex min-h-screen">
      {/* --- Main story area --- */}
      <div className="flex-1 max-w-2xl mx-auto px-6 py-10 flex flex-col gap-8">

        {/* Top bar */}
        <div className="flex items-center justify-between">
          <button
            onClick={handleStart}
            className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            ← New Story
          </button>
          <div className="flex items-center gap-4">
            {/* Furigana mode toggle */}
            <button
              onClick={cycleFurigana}
              className="text-xs px-2 py-1 rounded border border-zinc-700
                         text-zinc-400 hover:border-zinc-500 hover:text-zinc-200
                         transition-colors"
              title="Toggle furigana"
            >
              {furiganaMode === "full" ? "振仮名：全" : furiganaMode === "known_only" ? "振仮名：未" : "振仮名：無"}
            </button>
            {latestSegment && <ContextBar usagePct={latestSegment.contextPct} />}
          </div>
        </div>

        {/* Story text — all segments stacked */}
        <div className="flex flex-col gap-6">
          {segments.map((seg, si) => (
            <div key={si} className={`text-xl leading-loose tracking-wide ${si < segments.length - 1 ? "text-zinc-500" : "text-zinc-100"}`}>
              {seg.tokens.map((token, ti) => (
                <TokenSpan
                  key={`${si}-${ti}`}
                  token={token}
                  furiganaMode={furiganaMode}
                  onSelect={setSelectedToken}
                />
              ))}
            </div>
          ))}
        </div>

        {/* Stats for the latest segment */}
        {latestSegment && (
          <p className="text-xs text-zinc-600">
            {latestSegment.newWords} new / {latestSegment.totalWords} content words this segment
            {pendingHint && (
              <span className={`ml-2 ${pendingHint === "too_hard" ? "text-red-400" : "text-emerald-400"}`}>
                ({pendingHint === "too_hard" ? "Easier next" : "Harder next"})
              </span>
            )}
          </p>
        )}

        {/* Loading indicator */}
        {loading && (
          <p className="text-zinc-500 text-sm animate-pulse">Generating next segment…</p>
        )}

        {error && <p className="text-red-400 text-sm">{error}</p>}

        {/* Choices + difficulty buttons */}
        {latestSegment && !loading && (
          <>
            <ChoiceButtons
              choices={latestSegment.choices}
              disabled={loading}
              onChoice={handleChoice}
            />
            <div className="flex justify-end mt-2">
              <DifficultyButtons disabled={loading} onHint={handleDifficultyHint} />
            </div>
          </>
        )}
      </div>

      {/* --- Sidebar — word lookup --- */}
      {selectedToken && (
        <div className="w-72 border-l border-zinc-800 bg-zinc-900 p-6 flex flex-col gap-4">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-2xl font-medium">{selectedToken.surface}</p>
              <p className="text-zinc-400 text-sm">{selectedToken.reading}</p>
            </div>
            <button
              onClick={() => setSelectedToken(null)}
              className="text-zinc-600 hover:text-zinc-300 text-xl leading-none"
            >
              ×
            </button>
          </div>
          <p className="text-xs text-zinc-500 uppercase tracking-widest">{selectedToken.pos}</p>
          <p className="text-xs text-zinc-500">
            Status:{" "}
            <span className={
              selectedToken.status === "known" ? "text-emerald-400" :
              selectedToken.status === "new"   ? "text-sky-400" :
                                                  "text-zinc-400"
            }>
              {selectedToken.status}
            </span>
          </p>
          <p className="text-xs text-zinc-600 mt-auto">
            Full dictionary lookup coming in Phase 5
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function toSegment(res: StoryResponse): StorySegment {
  return {
    tokens: res.tokens,
    choices: res.choices,
    contextPct: res.context_usage_pct,
    newWords: res.new_word_count,
    totalWords: res.total_content_words,
  };
}
