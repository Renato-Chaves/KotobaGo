"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Token, VocabGridItem, VocabGridResponse, VocabGridStats } from "@/lib/types";
import { WordSidebar } from "@/components/story/WordSidebar";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const STATUS_FILTERS = [
  { value: "all",        label: "All" },
  { value: "due",        label: "Due" },
  { value: "introduced", label: "Introduced" },
  { value: "practiced",  label: "Practiced" },
  { value: "mastered",   label: "Mastered" },
  { value: "unseen",     label: "Unseen" },
] as const;

const JLPT_FILTERS = ["all", "N5", "N4", "N3", "N2", "N1"] as const;

const STATUS_CARD: Record<string, string> = {
  unseen:     "border-zinc-800  bg-zinc-900/60",
  introduced: "border-sky-800   bg-sky-950/40",
  practiced:  "border-amber-700 bg-amber-950/30",
  mastered:   "border-emerald-700 bg-emerald-950/30",
};

const STATUS_BADGE: Record<string, string> = {
  unseen:     "text-zinc-600",
  introduced: "text-sky-500",
  practiced:  "text-amber-400",
  mastered:   "text-emerald-400",
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatsBar({ stats }: { stats: VocabGridStats }) {
  const total = stats.unseen + stats.introduced + stats.practiced + stats.mastered;
  const known = stats.practiced + stats.mastered;

  return (
    <div className="flex flex-wrap gap-4 text-sm">
      <Stat value={total}            label="Total" color="text-zinc-300" />
      <Stat value={stats.due}        label="Due"         color="text-red-400" />
      <Stat value={stats.introduced} label="Introduced"  color="text-sky-400" />
      <Stat value={stats.practiced}  label="Practiced"   color="text-amber-400" />
      <Stat value={stats.mastered}   label="Mastered"    color="text-emerald-400" />
      {total > 0 && (
        <span className="text-zinc-600 text-xs self-end ml-auto">
          {Math.round((known / total) * 100)}% known
        </span>
      )}
    </div>
  );
}

function Stat({ value, label, color }: { value: number; label: string; color: string }) {
  return (
    <div className="flex flex-col items-center gap-0.5 min-w-[48px]">
      <span className={`text-lg font-bold tabular-nums ${color}`}>{value}</span>
      <span className="text-xs text-zinc-600">{label}</span>
    </div>
  );
}

function WordCard({ item, onClick }: { item: VocabGridItem; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`relative text-left rounded-xl border p-3 transition-colors
                  hover:border-zinc-600 hover:bg-zinc-800/60 ${STATUS_CARD[item.status] ?? STATUS_CARD.unseen}`}
    >
      {item.is_due && (
        <span className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full bg-red-500" title="Due for review" />
      )}
      <p className="text-xl font-medium leading-tight">{item.word}</p>
      <p className="text-xs text-zinc-500 mt-0.5">{item.reading}</p>
      <p className="text-xs text-zinc-400 mt-1.5 leading-snug line-clamp-2">{item.meaning}</p>
      <p className={`text-xs mt-2 font-medium ${STATUS_BADGE[item.status] ?? STATUS_BADGE.unseen}`}>
        {item.status}
      </p>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function VocabGrid() {
  const [data, setData] = useState<VocabGridResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("all");
  const [jlptFilter, setJlptFilter] = useState("all");
  const [selectedToken, setSelectedToken] = useState<Token | null>(null);

  useEffect(() => {
    setLoading(true);
    api.getVocabGrid({ status: statusFilter, jlpt: jlptFilter })
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [statusFilter, jlptFilter]);

  // Convert a VocabGridItem into the Token shape WordSidebar expects
  const openSidebar = (item: VocabGridItem) => {
    setSelectedToken({
      surface: item.word,
      reading: item.reading,
      pos: "名詞",           // not meaningful here, sidebar doesn't use it
      is_content: true,
      status: item.status === "unseen" ? "new" : item.status === "introduced" ? "new" : "known",
      vocab_id: item.vocab_id,
    });
  };

  return (
    <div className="flex min-h-screen">
      {/* Main content */}
      <div className="flex-1 max-w-5xl mx-auto px-4 py-6">

        {/* Page header */}
        <div className="flex items-center justify-between mb-6 pb-4 border-b border-zinc-800">
          <div className="flex items-center gap-4">
            <a href="/" className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">
              ← Home
            </a>
            <a href="/story" className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">
              📖 Story
            </a>
          </div>
          <h1 className="text-sm font-medium text-zinc-300">Vocabulary</h1>
        </div>

        {/* Stats bar */}
        {data && (
          <div className="mb-6">
            <StatsBar stats={data.stats} />
          </div>
        )}

        {/* Filter bar */}
        <div className="flex flex-wrap gap-3 mb-6">
          {/* Status tabs */}
          <div className="flex gap-1 bg-zinc-900 border border-zinc-800 rounded-lg p-1">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.value}
                onClick={() => setStatusFilter(f.value)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                  statusFilter === f.value
                    ? "bg-zinc-700 text-zinc-100"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {f.label}
                {f.value === "due" && data && data.stats.due > 0 && (
                  <span className="ml-1 text-red-400">{data.stats.due}</span>
                )}
              </button>
            ))}
          </div>

          {/* JLPT filter */}
          <div className="flex gap-1 bg-zinc-900 border border-zinc-800 rounded-lg p-1">
            {JLPT_FILTERS.map((j) => (
              <button
                key={j}
                onClick={() => setJlptFilter(j)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                  jlptFilter === j
                    ? "bg-zinc-700 text-zinc-100"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {j === "all" ? "All JLPT" : j}
              </button>
            ))}
          </div>
        </div>

        {/* Grid */}
        {loading ? (
          <p className="text-zinc-600 text-sm animate-pulse">Loading vocabulary…</p>
        ) : data && data.items.length > 0 ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
            {data.items.map((item) => (
              <WordCard key={item.vocab_id} item={item} onClick={() => openSidebar(item)} />
            ))}
          </div>
        ) : (
          <div className="text-center py-16 text-zinc-600">
            <p className="text-4xl mb-3">📚</p>
            <p className="text-sm">No words here yet — read some stories to build your vocabulary!</p>
          </div>
        )}
      </div>

      {/* Word sidebar */}
      {selectedToken && (
        <WordSidebar
          token={selectedToken}
          onClose={() => setSelectedToken(null)}
          onRated={(vocabId, newStatus) => {
            // Update the card status inline without a full refetch
            setData((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                items: prev.items.map((item) =>
                  item.vocab_id === vocabId
                    ? {
                        ...item,
                        status: newStatus as VocabGridItem["status"],
                        is_due: false,
                      }
                    : item
                ),
              };
            });
          }}
        />
      )}
    </div>
  );
}
