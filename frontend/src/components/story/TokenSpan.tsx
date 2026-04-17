"use client";

import type { FuriganaMode, Token } from "@/lib/types";

interface Props {
  token: Token;
  furiganaMode: FuriganaMode;
  onSelect: (token: Token) => void;
}

// Maps vocab status to underline style.
// "unseen" = solid (never seen before), "new" = dashed (seen, not practiced),
// "known" = no underline. Non-content words (particles etc.) never underlined.
const underlineClass: Record<string, string> = {
  unseen:         "underline decoration-2 decoration-sky-400 underline-offset-4",
  new:            "underline decoration-1 decoration-dashed decoration-sky-400/60 underline-offset-4",
  known:          "",
  lesson_example: "underline decoration-2 decoration-amber-400 underline-offset-4",
};

export function TokenSpan({ token, furiganaMode, onSelect }: Props) {
  const showFurigana = shouldShowFurigana(token, furiganaMode);
  // lesson_example overrides is_content so grammar targets (e.g. の particle) always get highlighted
  const ulClass = (token.is_content || token.status === "lesson_example")
    ? (underlineClass[token.status] ?? "")
    : "";

  // Punctuation and newlines — render without interaction
  if (!token.is_content && isPunctuation(token.surface)) {
    return <span className="select-none">{token.surface}</span>;
  }

  const handleClick = () => {
    if (token.is_content) onSelect(token);
  };

  if (showFurigana && token.reading !== token.surface) {
    return (
      <ruby
        className={`cursor-pointer transition-colors hover:text-sky-300 ${ulClass}`}
        onClick={handleClick}
      >
        {token.surface}
        <rt className="text-[0.55em] text-zinc-400 not-italic">{token.reading}</rt>
      </ruby>
    );
  }

  return (
    <span
      className={`${ulClass} ${token.is_content ? "cursor-pointer transition-colors hover:text-sky-300" : ""}`}
      onClick={handleClick}
    >
      {token.surface}
    </span>
  );
}

function shouldShowFurigana(token: Token, mode: FuriganaMode): boolean {
  if (!token.is_content) return false;
  if (mode === "none") return false;
  if (mode === "full") return true;
  // "known_only" — show furigana only for words not yet mastered
  return token.status !== "known";
}

function isPunctuation(surface: string): boolean {
  return /^[。、！？…「」『』（）【】\s]+$/.test(surface);
}
