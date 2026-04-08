"use client";

import { useState } from "react";
import { api } from "@/lib/api";

interface Props {
  text: string; // the raw Japanese surface text of the segment
}

export function TranslationToggle({ text }: Props) {
  const [shown, setShown] = useState(false);
  const [translation, setTranslation] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const handleToggle = async () => {
    if (shown) {
      setShown(false);
      return;
    }
    // Already fetched — just show it
    if (translation !== null) {
      setShown(true);
      return;
    }
    // First reveal — fetch from backend
    setLoading(true);
    setError(false);
    try {
      const res = await api.translateSegment(text);
      setTranslation(res.translation);
      setShown(true);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-2">
      <button
        onClick={handleToggle}
        disabled={loading}
        className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors
                   disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? "Translating…" : shown ? "Hide translation" : "Show translation"}
      </button>
      {error && (
        <p className="text-xs text-red-400 mt-1">Translation failed</p>
      )}
      {shown && translation && (
        <p className="text-sm text-zinc-400 mt-1 leading-relaxed italic">
          {translation}
        </p>
      )}
    </div>
  );
}
