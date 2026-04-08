"use client";

import type { DifficultyHint } from "@/lib/types";

interface Props {
  disabled: boolean;
  onHint: (hint: DifficultyHint) => void;
}

export function DifficultyButtons({ disabled, onHint }: Props) {
  return (
    <div className="flex gap-2">
      <button
        onClick={() => onHint("too_hard")}
        disabled={disabled}
        className="px-3 py-1.5 text-xs rounded-md border border-zinc-700
                   text-zinc-400 hover:border-red-500 hover:text-red-400
                   disabled:opacity-40 disabled:cursor-not-allowed
                   transition-colors duration-150"
      >
        Too Hard
      </button>
      <button
        onClick={() => onHint("too_easy")}
        disabled={disabled}
        className="px-3 py-1.5 text-xs rounded-md border border-zinc-700
                   text-zinc-400 hover:border-emerald-500 hover:text-emerald-400
                   disabled:opacity-40 disabled:cursor-not-allowed
                   transition-colors duration-150"
      >
        Too Easy
      </button>
    </div>
  );
}
