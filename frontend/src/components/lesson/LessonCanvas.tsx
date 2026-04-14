"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type {
  ContinueLessonResponse,
  ErrorAnalysisMode,
  ErrorAnalysisResponse,
  ErrorItem,
  FuriganaMode,
  LessonModule,
  LessonSessionMeta,
  LessonSummaryResponse,
  StartLessonResponse,
  SwitchModuleResponse,
  Token,
} from "@/lib/types";
import { ErrorPanel } from "@/components/story/ErrorPanel";
import { StoryInput } from "@/components/story/StoryInput";
import { TokenSpan } from "@/components/story/TokenSpan";
import { TranslationToggle } from "@/components/story/TranslationToggle";
import { WordSidebar } from "@/components/story/WordSidebar";
import { LessonProgressBar, StageNav } from "./StageNav";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

// Modules that output Japanese text worth rendering with TokenSpan
const JAPANESE_MODULES = new Set<LessonModule>(["examples", "recognition", "conversation"]);

interface AssistantTurn {
  role: "assistant";
  text: string;
  tokens: Token[];
  module: LessonModule;
  choices: string[];
  stageComplete: boolean;
}

interface UserTurn {
  role: "user";
  text: string;
  errors?: ErrorItem[] | null;
  overallFeedback?: string;
}

type Turn = AssistantTurn | UserTurn;

// ---------------------------------------------------------------------------
// Stage cleared banner
// ---------------------------------------------------------------------------

function StageClearedBanner({ onDismiss }: { onDismiss: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 2800);
    return () => clearTimeout(t);
  }, [onDismiss]);

  return (
    <div className="flex items-center justify-center gap-2 px-4 py-2 rounded-lg
                    bg-emerald-900/40 border border-emerald-700 text-emerald-300 text-sm
                    animate-pulse">
      Stage cleared! ✓
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface Props {
  lessonId: number;
}

export function LessonCanvas({ lessonId }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [sessionMeta, setSessionMeta] = useState<LessonSessionMeta | null>(null);
  const [furiganaMode, setFuriganaMode] = useState<FuriganaMode>("full");
  const [selectedToken, setSelectedToken] = useState<Token | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorMode, setErrorMode] = useState<ErrorAnalysisMode>("on_call");
  const [showStageBanner, setShowStageBanner] = useState(false);
  const [summary, setSummary] = useState<LessonSummaryResponse | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load user preferences and start lesson on mount
  useEffect(() => {
    api.getProfile()
      .then((p) => {
        setFuriganaMode(p.furigana_mode);
        setErrorMode(p.error_analysis_mode);
      })
      .catch(() => {});

    handleStart();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lessonId]);

  // Auto-scroll to bottom on new turns
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, loading]);

  // --- Start / restart lesson ---

  const handleStart = useCallback(async () => {
    setLoading(true);
    setError(null);
    setTurns([]);
    setSessionId(null);
    setSessionMeta(null);
    setSelectedToken(null);
    setSummary(null);

    try {
      const res: StartLessonResponse = await api.startLesson(lessonId);
      setSessionId(res.session_id);
      setSessionMeta(res.session_meta);
      setTurns([toAssistantTurn(res.text, res.tokens, res.session_meta.active_module, res.choices, false)]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start lesson");
    } finally {
      setLoading(false);
    }
  }, [lessonId]);

  // --- Submit user input ---

  const handleSubmit = useCallback(async (input: string) => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    setSelectedToken(null);

    const userTurnIndex = turns.length;
    setTurns((prev) => [...prev, { role: "user", text: input }]);

    try {
      const res: ContinueLessonResponse = await api.continueLesson(sessionId, { user_input: input });
      setSessionMeta(res.session_meta);

      const assistantTurn = toAssistantTurn(
        res.text, res.tokens, res.session_meta.active_module, res.choices, res.stage_complete
      );
      setTurns((prev) => [...prev, assistantTurn]);

      if (res.stage_complete) setShowStageBanner(true);

      if (errorMode === "auto") {
        runErrorAnalysis(userTurnIndex, input);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to continue lesson");
      setTurns((prev) => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  }, [sessionId, turns.length, errorMode]);

  // --- Switch module ---

  const handleSwitchModule = useCallback(async (module: LessonModule) => {
    if (!sessionId || loading) return;
    setLoading(true);
    setError(null);

    try {
      const res: SwitchModuleResponse = await api.switchModule(sessionId, module);
      setSessionMeta(res.session_meta);
      setTurns((prev) => [
        ...prev,
        toAssistantTurn(res.text, res.tokens, res.session_meta.active_module, res.choices, false),
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to switch module");
    } finally {
      setLoading(false);
    }
  }, [sessionId, loading]);

  // --- Error analysis ---

  const runErrorAnalysis = useCallback(async (turnIndex: number, text: string) => {
    if (!sessionId) return;
    setTurns((prev) =>
      prev.map((t, i) => i === turnIndex && t.role === "user" ? { ...t, errors: null } : t)
    );
    try {
      const res: ErrorAnalysisResponse = await api.analyzeLessonErrors(sessionId, text);
      setTurns((prev) =>
        prev.map((t, i) =>
          i === turnIndex && t.role === "user"
            ? { ...t, errors: res.errors, overallFeedback: res.overall_feedback }
            : t
        )
      );
    } catch {
      setTurns((prev) =>
        prev.map((t, i) => i === turnIndex && t.role === "user" ? { ...t, errors: undefined } : t)
      );
    }
  }, [sessionId]);

  // --- Text selection → word sidebar ---

  const handleTextSelection = useCallback(async () => {
    const selected = window.getSelection()?.toString().trim();
    if (!selected) return;
    try {
      const res = await api.tokenize(selected);
      const match = res.tokens.find((t) => t.is_content && t.vocab_id !== null);
      if (match) setSelectedToken(match);
    } catch { /* silent */ }
  }, []);

  // --- Furigana cycle ---

  const cycleFurigana = useCallback(() => {
    setFuriganaMode((m) => m === "full" ? "known_only" : m === "known_only" ? "none" : "full");
  }, []);

  // --- End lesson → summary ---

  const handleEndLesson = useCallback(async () => {
    if (!sessionId) return;
    setSummaryLoading(true);
    try {
      const res = await api.getLessonSummary(sessionId);
      setSummary(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load summary");
    } finally {
      setSummaryLoading(false);
    }
  }, [sessionId]);

  // --- Export conversation to story ---

  const handleExportToStory = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const res = await api.exportLessonToStory(sessionId);
      window.location.href = `/story?session=${res.session_id}`;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to export to story");
      setLoading(false);
    }
  }, [sessionId]);

  // Choices from the latest assistant turn (for the input area suggestions)
  const latestAssistantTurn = [...turns].reverse().find((t): t is AssistantTurn => t.role === "assistant") ?? null;
  const latestChoices = latestAssistantTurn?.choices ?? [];
  const activeModule = sessionMeta?.active_module ?? "presentation";
  const inConversation = activeModule === "conversation";

  // ---------------------------------------------------------------------------
  // Summary screen
  // ---------------------------------------------------------------------------

  if (summary) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="max-w-lg w-full px-6 py-10 flex flex-col gap-6">
          <h2 className="text-2xl font-bold text-zinc-100">Lesson Complete!</h2>
          <p className="text-zinc-300 leading-relaxed">{summary.coach_note}</p>
          <div className="flex gap-3 mt-2 flex-wrap">
            <button
              onClick={handleStart}
              className="px-5 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-sm font-medium transition-colors"
            >
              Restart Lesson
            </button>
            {summary && (
              <button
                onClick={handleExportToStory}
                disabled={loading}
                className="px-5 py-2 rounded-lg border border-zinc-600 hover:border-zinc-400
                           text-zinc-300 hover:text-zinc-100 text-sm font-medium transition-colors
                           disabled:opacity-40"
              >
                Take to Story →
              </button>
            )}
            <a
              href="/lessons"
              className="px-5 py-2 rounded-lg border border-zinc-700 hover:border-zinc-500
                         text-zinc-400 hover:text-zinc-200 text-sm font-medium transition-colors"
            >
              ← All Lessons
            </a>
          </div>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Loading (initial start)
  // ---------------------------------------------------------------------------

  if (turns.length === 0 && loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="flex gap-1.5">
          <span className="w-2 h-2 rounded-full bg-zinc-500 animate-bounce [animation-delay:0ms]" />
          <span className="w-2 h-2 rounded-full bg-zinc-500 animate-bounce [animation-delay:150ms]" />
          <span className="w-2 h-2 rounded-full bg-zinc-500 animate-bounce [animation-delay:300ms]" />
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Main lesson view
  // ---------------------------------------------------------------------------

  return (
    <div className="flex min-h-screen">

      {/* --- Left sidebar — stage nav --- */}
      <div className="hidden md:flex flex-col gap-4 pt-6 pl-4 pr-2 w-52 flex-shrink-0">
        {sessionMeta && (
          <StageNav
            meta={sessionMeta}
            loading={loading}
            onSwitch={handleSwitchModule}
          />
        )}
        {inConversation && (
          <button
            onClick={handleExportToStory}
            disabled={loading}
            className="mt-2 px-3 py-2 rounded-lg border border-zinc-700 hover:border-sky-600
                       text-zinc-400 hover:text-sky-300 text-sm transition-colors
                       disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Take to Story →
          </button>
        )}
      </div>

      {/* --- Main content area --- */}
      <div className="flex-1 flex flex-col max-w-2xl mx-auto px-4 py-6 min-w-0">

        {/* Progress bar */}
        {sessionMeta && (
          <div className="mb-4">
            <LessonProgressBar meta={sessionMeta} />
          </div>
        )}

        {/* Top bar */}
        <div className="flex items-center justify-between mb-4 pb-3 border-b border-zinc-800">
          <div className="flex items-center gap-3">
            <a
              href="/lessons"
              className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              ← Lessons
            </a>
            <button
              onClick={handleEndLesson}
              disabled={summaryLoading || loading || turns.length < 3}
              className="text-xs px-2 py-1 rounded border border-zinc-700
                        text-zinc-500 hover:border-zinc-500 hover:text-zinc-300
                        transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              {summaryLoading ? "Loading…" : "Finish Lesson"}
            </button>
          </div>
          <div className="flex items-center gap-3">
            {/* Error mode toggle */}
            <button
              onClick={() => setErrorMode((m) => m === "on_call" ? "auto" : "on_call")}
              className="text-xs px-2 py-1 rounded border border-zinc-700
                        text-zinc-400 hover:border-zinc-500 hover:text-zinc-200
                        transition-colors"
            >
              {errorMode === "auto" ? "誤り：自動" : "誤り：手動"}
            </button>
            {/* Furigana toggle */}
            <button
              onClick={cycleFurigana}
              className="text-xs px-2 py-1 rounded border border-zinc-700
                        text-zinc-400 hover:border-zinc-500 hover:text-zinc-200
                        transition-colors"
            >
              {furiganaMode === "full" ? "振仮名：全" : furiganaMode === "known_only" ? "振仮名：未" : "振仮名：無"}
            </button>
          </div>
        </div>

        {/* Turns */}
        <div className="flex flex-col gap-4 flex-1" onMouseUp={handleTextSelection}>
          {turns.map((turn, i) => {
            if (turn.role === "user") {
              const hasResult = turn.errors !== undefined;
              const isAnalysisLoading = turn.errors === null;
              return (
                <div key={i} className="flex flex-col items-end gap-1">
                  <div className="max-w-[75%] px-4 py-2.5 rounded-2xl rounded-tr-sm
                                  bg-sky-700 text-white text-base leading-relaxed">
                    {turn.text}
                  </div>
                  {errorMode === "on_call" && !hasResult && !isAnalysisLoading && (
                    <button
                      onClick={() => runErrorAnalysis(i, turn.text)}
                      className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors mr-1"
                    >
                      Check my Japanese
                    </button>
                  )}
                  {(hasResult || isAnalysisLoading) && (
                    <div className="w-full max-w-[85%]">
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

            // Assistant turn
            const isLatest = i === turns.length - 1;
            const useTokens = JAPANESE_MODULES.has(turn.module);

            return (
              <div key={i} className="flex flex-col gap-1">
                {/* Module badge — only on first turn of a new module */}
                {i === 0 || (turns[i - 1].role === "assistant" && (turns[i - 1] as AssistantTurn).module !== turn.module) ? (
                  <span className="text-[10px] text-zinc-600 uppercase tracking-widest ml-1">
                    {moduleLabel(turn.module)}
                  </span>
                ) : null}

                <div className={`leading-relaxed transition-colors
                  ${useTokens ? "text-xl tracking-wide" : "text-base text-zinc-200"}
                  ${isLatest ? "" : useTokens ? "text-zinc-500" : "text-zinc-600"}
                `}>
                  {useTokens
                    ? turn.tokens.map((token, ti) => (
                        <TokenSpan
                          key={`${i}-${ti}`}
                          token={token}
                          furiganaMode={furiganaMode}
                          onSelect={setSelectedToken}
                        />
                      ))
                    : <p className="whitespace-pre-wrap">{turn.text}</p>
                  }
                </div>

                {/* Translation toggle — only for Japanese turns */}
                {useTokens && (
                  <TranslationToggle text={turn.tokens.map((t) => t.surface).join("")} />
                )}
              </div>
            );
          })}

          {/* Stage cleared banner */}
          {showStageBanner && (
            <StageClearedBanner onDismiss={() => setShowStageBanner(false)} />
          )}

          {/* Loading */}
          {loading && (
            <div className="flex gap-1.5 items-center px-2 py-3">
              <span className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-bounce [animation-delay:0ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-bounce [animation-delay:300ms]" />
            </div>
          )}

          {error && <p className="text-red-400 text-sm px-2">{error}</p>}
          <div ref={bottomRef} />
        </div>

        {/* Input area */}
        {!loading && turns.length > 0 && (
          <div className="mt-4 pt-4 border-t border-zinc-800">
            {/* Mobile stage nav */}
            {sessionMeta && (
              <div className="flex md:hidden gap-2 mb-3 overflow-x-auto pb-1">
                {(["presentation", "examples", "recognition", "conversation"] as LessonModule[]).map((mod) => {
                  const isActive = sessionMeta.active_module === mod;
                  return (
                    <button
                      key={mod}
                      onClick={() => handleSwitchModule(mod)}
                      disabled={loading}
                      className={`flex-shrink-0 px-2 py-1 rounded-lg text-xs border transition-colors
                        ${isActive
                          ? "bg-sky-900/50 border-sky-700 text-sky-300"
                          : "border-zinc-700 text-zinc-500 hover:border-zinc-500 hover:text-zinc-300"
                        }`}
                    >
                      {moduleLabel(mod)}
                    </button>
                  );
                })}
              </div>
            )}
            <StoryInput
              suggestions={latestChoices}
              disabled={loading}
              onSubmit={handleSubmit}
            />
          </div>
        )}
      </div>

      {/* --- Word sidebar --- */}
      {selectedToken && (
        <WordSidebar
          token={selectedToken}
          onClose={() => setSelectedToken(null)}
          onRated={(vocabId, newStatus) => {
            setTurns((prev) => prev.map((turn) => {
              if (turn.role !== "assistant") return turn;
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

function toAssistantTurn(
  text: string,
  tokens: Token[],
  module: LessonModule,
  choices: string[],
  stageComplete: boolean,
): AssistantTurn {
  return { role: "assistant", text, tokens, module, choices, stageComplete };
}

function moduleLabel(module: LessonModule): string {
  const labels: Record<LessonModule, string> = {
    presentation: "📖 Intro",
    examples:     "💡 Examples",
    recognition:  "✅ Recognition",
    conversation: "💬 Practice",
    qa:           "❓ Q&A",
  };
  return labels[module] ?? module;
}
