"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ConfidenceRating, Token, WordLookup } from "@/lib/types";

interface Props {
  token: Token;
  onClose: () => void;
  onRated: (vocabId: number, newStatus: string) => void;
}

const CONFIDENCE_BUTTONS: { rating: ConfidenceRating; label: string; sublabel: string; color: string }[] = [
  { rating: "again", label: "Again",  sublabel: "1d",   color: "border-red-600    text-red-400    hover:bg-red-950"     },
  { rating: "hard",  label: "Hard",   sublabel: "~3d",  color: "border-orange-600 text-orange-400 hover:bg-orange-950"  },
  { rating: "good",  label: "Good",   sublabel: "~1w",  color: "border-sky-600    text-sky-400    hover:bg-sky-950"     },
  { rating: "easy",  label: "Easy",   sublabel: "~2w+", color: "border-emerald-600 text-emerald-400 hover:bg-emerald-950" },
];

export function WordSidebar({ token, onClose, onRated }: Props) {
  const [lookup, setLookup] = useState<WordLookup | null>(null);
  const [loading, setLoading] = useState(false);
  const [rating, setRating] = useState<ConfidenceRating | null>(null);

  // Fetch lookup data whenever the selected token changes
  useEffect(() => {
    if (!token.vocab_id) return;
    setLookup(null);
    setRating(null);
    setLoading(true);

    api.lookupWord(token.vocab_id)
      .then(setLookup)
      .catch(() => {}) // sidebar stays showing surface/reading on failure
      .finally(() => setLoading(false));
  }, [token.vocab_id]);

  const handleRate = async (r: ConfidenceRating) => {
    if (!token.vocab_id) return;
    setRating(r);
    try {
      const res = await api.rateWord(token.vocab_id, r);
      onRated(token.vocab_id, res.new_status);
    } catch {
      setRating(null); // reset on failure
    }
  };

  return (
    <div className="w-72 border-l border-zinc-800 bg-zinc-900 flex flex-col h-screen sticky top-0">
      {/* Header */}
      <div className="flex items-start justify-between p-6 pb-4">
        <div>
          <p className="text-3xl font-medium tracking-wide">{token.surface}</p>
          <p className="text-zinc-400 text-sm mt-0.5">{token.reading}</p>
        </div>
        <button
          onClick={onClose}
          className="text-zinc-600 hover:text-zinc-300 text-xl leading-none mt-1"
        >
          ×
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 flex flex-col gap-5 pb-6">
        {/* Status badge */}
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2 py-0.5 rounded-full border ${statusStyle(lookup?.user_status ?? token.status)}`}>
            {lookup?.user_status ?? token.status}
          </span>
          {lookup?.jlpt_level && (
            <span className="text-xs px-2 py-0.5 rounded-full border border-zinc-700 text-zinc-400">
              {lookup.jlpt_level}
            </span>
          )}
        </div>

        {loading && (
          <p className="text-zinc-600 text-sm animate-pulse">Looking up…</p>
        )}

        {lookup && (
          <>
            {/* Meaning */}
            <div>
              <p className="text-xs text-zinc-500 uppercase tracking-widest mb-1">Meaning</p>
              <p className="text-zinc-200 text-sm leading-relaxed">{lookup.meaning}</p>
            </div>

            {/* Explanation in native language */}
            <div>
              <p className="text-xs text-zinc-500 uppercase tracking-widest mb-1">Explanation</p>
              <p className="text-zinc-300 text-sm leading-relaxed">{lookup.explanation}</p>
            </div>

            {/* Jisho link */}
            <a
              href={lookup.jisho_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-sky-500 hover:text-sky-400 transition-colors"
            >
              View on jisho.org →
            </a>
          </>
        )}

        {/* No vocab_id — word not in seed data yet */}
        {!token.vocab_id && !loading && (
          <p className="text-xs text-zinc-600">
            This word is not in the vocabulary list yet.
          </p>
        )}
      </div>

      {/* Confidence buttons — always visible if word is tracked */}
      {token.vocab_id && (
        <div className="border-t border-zinc-800 p-4">
          <p className="text-xs text-zinc-600 mb-3">How well did you know this?</p>
          <div className="grid grid-cols-4 gap-1.5">
            {CONFIDENCE_BUTTONS.map(({ rating: r, label, sublabel, color }) => (
              <button
                key={r}
                onClick={() => handleRate(r)}
                disabled={rating !== null}
                className={`flex flex-col items-center py-2 rounded-lg border text-xs
                            transition-colors disabled:opacity-50 disabled:cursor-not-allowed
                            ${color} ${rating === r ? "opacity-100 ring-1 ring-white/20" : ""}`}
              >
                <span className="font-medium">{label}</span>
                <span className="text-[10px] opacity-60 mt-0.5">{sublabel}</span>
              </button>
            ))}
          </div>
          {rating && (
            <p className="text-xs text-zinc-600 mt-2 text-center">
              Rated · next review scheduled
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function statusStyle(status: string): string {
  switch (status) {
    case "mastered":   return "border-emerald-700 text-emerald-400";
    case "practiced":  return "border-sky-700     text-sky-400";
    case "introduced": return "border-zinc-600    text-zinc-400";
    default:           return "border-zinc-700    text-zinc-500";
  }
}
