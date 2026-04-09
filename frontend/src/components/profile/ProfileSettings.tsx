"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ErrorAnalysisMode, FuriganaMode, UserProfile } from "@/lib/types";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const JLPT_LEVELS = ["N5", "N4", "N3", "N2", "N1"] as const;

const NATIVE_LANGUAGES = [
  { value: "pt", label: "Portuguese" },
  { value: "en", label: "English" },
  { value: "es", label: "Spanish" },
  { value: "fr", label: "French" },
  { value: "de", label: "German" },
  { value: "zh", label: "Chinese" },
  { value: "ko", label: "Korean" },
] as const;

// ---------------------------------------------------------------------------
// Section wrapper
// ---------------------------------------------------------------------------

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 flex flex-col gap-4">
      <h2 className="text-xs text-zinc-500 uppercase tracking-widest font-medium">{title}</h2>
      {children}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs text-zinc-400">{label}</label>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Toggle group (for 2–3 options)
// ---------------------------------------------------------------------------

function ToggleGroup<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex gap-1 bg-zinc-950 border border-zinc-800 rounded-lg p-1 w-fit">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
            value === opt.value
              ? "bg-zinc-700 text-zinc-100"
              : "text-zinc-500 hover:text-zinc-300"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stats mini-bar (fetched from vocab grid stats)
// ---------------------------------------------------------------------------

function VocabStatsBar() {
  const [stats, setStats] = useState<Record<string, number> | null>(null);

  useEffect(() => {
    api.getVocabGrid({ status: "all" }).then((d) => setStats(d.stats)).catch(() => {});
  }, []);

  if (!stats) return <p className="text-xs text-zinc-600 animate-pulse">Loading…</p>;

  const total = (stats.unseen ?? 0) + (stats.introduced ?? 0) + (stats.practiced ?? 0) + (stats.mastered ?? 0);
  const known = (stats.practiced ?? 0) + (stats.mastered ?? 0);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex gap-4 text-sm">
        {[
          { label: "Introduced", value: stats.introduced, color: "text-sky-400" },
          { label: "Practiced",  value: stats.practiced,  color: "text-amber-400" },
          { label: "Mastered",   value: stats.mastered,   color: "text-emerald-400" },
          { label: "Due",        value: stats.due,         color: "text-red-400" },
        ].map(({ label, value, color }) => (
          <div key={label} className="flex flex-col items-center gap-0.5 min-w-[52px]">
            <span className={`text-lg font-bold tabular-nums ${color}`}>{value}</span>
            <span className="text-xs text-zinc-600">{label}</span>
          </div>
        ))}
      </div>
      {/* Mastery progress bar */}
      {total > 0 && (
        <div className="flex flex-col gap-1">
          <div className="h-2 rounded-full bg-zinc-800 overflow-hidden">
            <div
              className="h-full rounded-full bg-emerald-600 transition-all"
              style={{ width: `${Math.round((known / total) * 100)}%` }}
            />
          </div>
          <p className="text-xs text-zinc-600">
            {Math.round((known / total) * 100)}% of {total} words known
          </p>
        </div>
      )}
      <a
        href="/vocab"
        className="text-xs text-sky-500 hover:text-sky-400 transition-colors w-fit"
      >
        View vocabulary grid →
      </a>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ProfileSettings() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // Local editable state — mirrors the profile fields
  const [jlptGoal, setJlptGoal] = useState("N5");
  const [nativeLang, setNativeLang] = useState("pt");
  const [aiContext, setAiContext] = useState("");
  const [errorMode, setErrorMode] = useState<ErrorAnalysisMode>("on_call");
  const [furiganaMode, setFuriganaMode] = useState<FuriganaMode>("full");

  useEffect(() => {
    api.getProfile()
      .then((p) => {
        setProfile(p);
        setJlptGoal(p.jlpt_goal);
        setNativeLang(p.native_language);
        setAiContext(p.ai_context ?? "");
        setErrorMode(p.error_analysis_mode);
        setFuriganaMode(p.furigana_mode);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const updated = await api.updateProfile({
        jlpt_goal: jlptGoal,
        native_language: nativeLang,
        ai_context: aiContext,
        error_analysis_mode: errorMode,
        furigana_mode: furiganaMode,
      });
      setProfile(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch {
      // keep current state
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-zinc-600 animate-pulse text-sm">Loading profile…</p>
      </div>
    );
  }

  return (
    <div className="max-w-lg mx-auto px-4 py-6">

      {/* Page header */}
      <div className="flex items-center justify-between mb-6 pb-4 border-b border-zinc-800">
        <div className="flex items-center gap-4">
          <a href="/" className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">← Home</a>
          <a href="/story" className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">📖 Story</a>
          <a href="/vocab" className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">📚 Vocab</a>
        </div>
        <h1 className="text-sm font-medium text-zinc-300">Profile</h1>
      </div>

      <div className="flex flex-col gap-4">

        {/* Learning profile */}
        <Section title="Learning Profile">
          <Field label="JLPT goal">
            <ToggleGroup
              options={JLPT_LEVELS.map((l) => ({ value: l, label: l }))}
              value={jlptGoal as typeof JLPT_LEVELS[number]}
              onChange={setJlptGoal}
            />
          </Field>
          <Field label="Native language">
            <select
              value={nativeLang}
              onChange={(e) => setNativeLang(e.target.value)}
              className="bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm
                         text-zinc-200 focus:outline-none focus:border-zinc-600 w-fit"
            >
              {NATIVE_LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>{l.label}</option>
              ))}
            </select>
          </Field>
        </Section>

        {/* Preferences */}
        <Section title="Preferences">
          <Field label="Error analysis mode">
            <ToggleGroup<ErrorAnalysisMode>
              options={[
                { value: "on_call", label: "On Call — check manually" },
                { value: "auto",    label: "Auto — check every turn" },
              ]}
              value={errorMode}
              onChange={setErrorMode}
            />
            <p className="text-xs text-zinc-600">
              On Call: a "Check my Japanese" button appears on each message.<br />
              Auto: analysis runs automatically after every submission.
            </p>
          </Field>
          <Field label="Default furigana">
            <ToggleGroup<FuriganaMode>
              options={[
                { value: "full",       label: "Full" },
                { value: "known_only", label: "New only" },
                { value: "none",       label: "None" },
              ]}
              value={furiganaMode}
              onChange={setFuriganaMode}
            />
            <p className="text-xs text-zinc-600">
              Applied when a new story starts. You can still toggle it during a session.
            </p>
          </Field>
        </Section>

        {/* AI context */}
        <Section title="AI Context">
          <Field label="Tell the AI about yourself">
            <textarea
              value={aiContext}
              onChange={(e) => setAiContext(e.target.value)}
              rows={4}
              placeholder="e.g. I'm a software engineer from Brazil learning Japanese for travel and anime. I struggle with keigo but enjoy slice-of-life settings."
              className="bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm
                         text-zinc-200 placeholder-zinc-700 focus:outline-none focus:border-zinc-600
                         resize-none w-full leading-relaxed"
            />
          </Field>
          <p className="text-xs text-zinc-600">
            This paragraph is available to the AI when generating stories and coach notes.
            Be specific — the more context, the more personalised your experience.
          </p>
        </Section>

        {/* Vocabulary stats */}
        <Section title="Vocabulary Progress">
          <VocabStatsBar />
        </Section>

        {/* Save button */}
        <button
          onClick={handleSave}
          disabled={saving}
          className="w-full px-6 py-3 rounded-xl bg-sky-600 hover:bg-sky-500
                     text-white font-medium transition-colors
                     disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? "Saving…" : saved ? "✓ Saved" : "Save Changes"}
        </button>

      </div>
    </div>
  );
}
