"use client";

import { useState } from "react";
import type { ErrorItem, ErrorType } from "@/lib/types";

interface Props {
  errors: ErrorItem[];
  overallFeedback: string;
  loading?: boolean;
}

const TYPE_CONFIG: Record<ErrorType, { label: string; colors: string }> = {
  critical:   { label: "Critical",   colors: "border-red-700    bg-red-950/40    text-red-400"    },
  grammar:    { label: "Grammar",    colors: "border-orange-700 bg-orange-950/40 text-orange-400" },
  politeness: { label: "Politeness", colors: "border-yellow-700 bg-yellow-950/40 text-yellow-400" },
  unnatural:  { label: "Unnatural",  colors: "border-sky-700    bg-sky-950/40    text-sky-400"    },
  stylistic:  { label: "Style",      colors: "border-emerald-700 bg-emerald-950/40 text-emerald-400" },
};

export function ErrorPanel({ errors, overallFeedback, loading }: Props) {
  const [expanded, setExpanded] = useState<number | null>(null);

  if (loading) {
    return (
      <p className="text-xs text-zinc-600 animate-pulse mt-1 ml-1">Checking…</p>
    );
  }

  return (
    <div className="mt-2 flex flex-col gap-1.5">
      {errors.length === 0 ? (
        <p className="text-xs text-emerald-500 mt-1 ml-1">✓ No errors found</p>
      ) : (
        errors.map((err, i) => {
          const config = TYPE_CONFIG[err.type as ErrorType] ?? TYPE_CONFIG.grammar;
          const isOpen = expanded === i;
          return (
            <button
              key={i}
              onClick={() => setExpanded(isOpen ? null : i)}
              className={`text-left w-full rounded-lg border px-3 py-2 text-xs transition-colors ${config.colors}`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="shrink-0 font-medium opacity-70">{config.label}</span>
                  <span className="font-mono truncate">
                    <span className="line-through opacity-60">{err.error_text}</span>
                    {" → "}
                    <span className="font-semibold">{err.correction}</span>
                  </span>
                </div>
                <span className="shrink-0 opacity-50">{isOpen ? "▲" : "▼"}</span>
              </div>
              {isOpen && (
                <p className="mt-1.5 text-zinc-300 leading-relaxed">{err.explanation}</p>
              )}
            </button>
          );
        })
      )}
      {overallFeedback && (
        <p className="text-xs text-zinc-500 italic mt-0.5 ml-1">{overallFeedback}</p>
      )}
    </div>
  );
}
