"use client";

import type { SessionSummaryResponse } from "@/lib/types";

interface Props {
  summary: SessionSummaryResponse;
  onNewStory: () => void;
}

const ERROR_LABELS: Record<string, { label: string; color: string }> = {
  critical:   { label: "Critical",   color: "text-red-400"     },
  grammar:    { label: "Grammar",    color: "text-orange-400"  },
  politeness: { label: "Politeness", color: "text-yellow-400"  },
  unnatural:  { label: "Unnatural",  color: "text-sky-400"     },
  stylistic:  { label: "Style",      color: "text-emerald-400" },
};

export function SessionSummaryScreen({ summary, onNewStory }: Props) {
  const { stats, coach_note } = summary;
  const totalErrors = Object.values(stats.errors_by_type).reduce((a, b) => a + b, 0);
  const accuracy =
    stats.turns > 0 && totalErrors <= stats.turns
      ? Math.round(((stats.turns - totalErrors) / stats.turns) * 100)
      : null;

  return (
    <div className="flex flex-col items-center justify-center min-h-screen px-6 py-12 gap-8 max-w-lg mx-auto">

      {/* Header */}
      <div className="text-center">
        <p className="text-4xl mb-2">🎌</p>
        <h1 className="text-2xl font-bold tracking-tight">Session Complete</h1>
        <p className="text-zinc-500 text-sm mt-1">Here's how you did</p>
      </div>

      {/* Stats grid */}
      <div className="w-full grid grid-cols-2 gap-3">
        <StatCard value={stats.turns} label="Turns" />
        <StatCard value={stats.new_words_total} label="New Words" />
        <StatCard value={stats.content_words_total} label="Words Read" />
        <StatCard value={accuracy !== null ? `${accuracy}%` : "—"} label="Accuracy" />
      </div>

      {/* Error breakdown */}
      {totalErrors > 0 && (
        <div className="w-full bg-zinc-900 border border-zinc-800 rounded-xl p-4">
          <p className="text-xs text-zinc-500 uppercase tracking-widest mb-3">Errors by type</p>
          <div className="flex flex-col gap-1.5">
            {Object.entries(stats.errors_by_type)
              .filter(([, count]) => count > 0)
              .map(([type, count]) => {
                const cfg = ERROR_LABELS[type] ?? { label: type, color: "text-zinc-400" };
                return (
                  <div key={type} className="flex items-center justify-between text-sm">
                    <span className={cfg.color}>{cfg.label}</span>
                    <span className="text-zinc-300 font-medium tabular-nums">{count}</span>
                  </div>
                );
              })}
          </div>
        </div>
      )}

      {totalErrors === 0 && (
        <div className="w-full bg-emerald-950/30 border border-emerald-800 rounded-xl p-4 text-center">
          <p className="text-emerald-400 text-sm font-medium">No errors detected — perfect session!</p>
        </div>
      )}

      {/* Coach note */}
      {coach_note && (
        <div className="w-full bg-zinc-900 border border-zinc-800 rounded-xl p-4">
          <p className="text-xs text-zinc-500 uppercase tracking-widest mb-2">Coach note</p>
          <p className="text-zinc-200 text-sm leading-relaxed">{coach_note}</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-col gap-3 w-full">
        <button
          onClick={onNewStory}
          className="w-full px-6 py-3 rounded-xl bg-sky-600 hover:bg-sky-500
                     text-white font-medium transition-colors"
        >
          Start New Story
        </button>
      </div>
    </div>
  );
}

function StatCard({ value, label }: { value: string | number; label: string }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 text-center">
      <p className="text-2xl font-bold tabular-nums">{value}</p>
      <p className="text-xs text-zinc-500 mt-1">{label}</p>
    </div>
  );
}
