"use client";

import { useRef, useState } from "react";

interface Props {
  suggestions: string[];
  disabled: boolean;
  onSubmit: (input: string) => void;
}

export function StoryInput({ suggestions, disabled, onSubmit }: Props) {
  const [value, setValue] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setValue("");
    setShowSuggestions(false);
  };

  const handleSuggestion = (suggestion: string) => {
    setValue(suggestion);
    setShowSuggestions(false);
    textareaRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Shift+Enter = newline, Enter alone = submit
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="flex flex-col gap-3 mt-6">
      {/* Suggestions panel */}
      {showSuggestions && (
        <div className="flex flex-col gap-2">
          {suggestions.map((s, i) => (
            <button
              key={i}
              onClick={() => handleSuggestion(s)}
              disabled={disabled}
              className="w-full text-left px-4 py-2.5 rounded-lg border border-zinc-700
                         bg-zinc-900 text-zinc-300 text-base
                         hover:border-sky-500 hover:bg-zinc-800
                         disabled:opacity-40 disabled:cursor-not-allowed
                         transition-colors duration-150"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input row */}
      <div className="flex gap-2 items-end">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={2}
          placeholder="日本語で返事してください… (Enter to send)"
          className="flex-1 resize-none rounded-lg border border-zinc-700
                     bg-zinc-900 text-zinc-100 text-base px-4 py-3
                     placeholder:text-zinc-600
                     focus:outline-none focus:border-sky-500
                     disabled:opacity-40 disabled:cursor-not-allowed
                     transition-colors"
        />
        <div className="flex flex-col gap-2">
          {/* Suggestions toggle */}
          <button
            onClick={() => setShowSuggestions((s) => !s)}
            disabled={disabled}
            title="Show suggested responses"
            className="px-3 py-2 rounded-lg border border-zinc-700
                       text-zinc-400 hover:border-zinc-500 hover:text-zinc-200
                       disabled:opacity-40 disabled:cursor-not-allowed
                       transition-colors text-sm"
          >
            {showSuggestions ? "▲" : "▼"}
          </button>
          {/* Submit */}
          <button
            onClick={handleSubmit}
            disabled={disabled || !value.trim()}
            className="px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500
                       text-white text-sm font-medium
                       disabled:opacity-40 disabled:cursor-not-allowed
                       transition-colors"
          >
            →
          </button>
        </div>
      </div>
    </div>
  );
}
