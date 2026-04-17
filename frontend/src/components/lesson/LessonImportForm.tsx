"use client";

import { useCallback, useState } from "react";

import { api } from "@/lib/api";
import type {
  CreateLessonRequest,
  ImportPreview,
  LessonExample,
  LessonSentence,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

type ImportTab = "url" | "paste" | "manual";

const TABS: Array<{ id: ImportTab; label: string }> = [
  { id: "url", label: "URL" },
  { id: "paste", label: "Paste" },
  { id: "manual", label: "Manual" },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface Props {
  onSaved: (id: number) => void;
}

export function LessonImportForm({ onSaved }: Props) {
  const [tab, setTab] = useState<ImportTab>("url");
  const [url, setUrl] = useState("");
  const [pastedText, setPastedText] = useState("");
  const [importing, setImporting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Editable preview state
  const [preview, setPreview] = useState<ImportPreview | null>(null);

  // ── Import (URL or Paste) ──────────────────────────────────────────────

  const handleImport = useCallback(async () => {
    setImporting(true);
    setError(null);
    try {
      const req = tab === "url" ? { url } : { text: pastedText };
      const res = await api.importLessonUrl(req);
      setPreview(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setImporting(false);
    }
  }, [tab, url, pastedText]);

  // ── Start from blank (Manual) ──────────────────────────────────────────

  const handleStartBlank = useCallback(() => {
    setPreview({
      title: "",
      grammar_point: "",
      jlpt_level: "N5",
      category: "grammar",
      source_language: "en",
      explanation: "",
      examples: [{ id: "ex_1", japanese: "", reading: "", translation: "" }],
      sentences: [{ id: "s_1", japanese: "", reading: "", translation: "" }],
    });
  }, []);

  // ── Save ───────────────────────────────────────────────────────────────

  const handleSave = useCallback(async () => {
    if (!preview) return;
    setSaving(true);
    setError(null);
    try {
      const req: CreateLessonRequest = {
        title: preview.title,
        grammar_point: preview.grammar_point || undefined,
        jlpt_level: preview.jlpt_level,
        category: preview.category,
        source_language: preview.source_language,
        explanation: preview.explanation,
        examples: preview.examples,
        sentences: preview.sentences,
      };
      const res = await api.createLesson(req);
      onSaved(res.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }, [preview, onSaved]);

  // ── Helpers to update preview fields ───────────────────────────────────

  const updateField = <K extends keyof ImportPreview>(key: K, val: ImportPreview[K]) => {
    setPreview((p) => (p ? { ...p, [key]: val } : p));
  };

  const updateExample = (idx: number, field: keyof LessonExample, val: string) => {
    setPreview((p) => {
      if (!p) return p;
      const examples = [...p.examples];
      examples[idx] = { ...examples[idx], [field]: val };
      return { ...p, examples };
    });
  };

  const addExample = () => {
    setPreview((p) => {
      if (!p) return p;
      const id = `ex_${p.examples.length + 1}`;
      return { ...p, examples: [...p.examples, { id, japanese: "", reading: "", translation: "" }] };
    });
  };

  const removeExample = (idx: number) => {
    setPreview((p) => {
      if (!p) return p;
      return { ...p, examples: p.examples.filter((_, i) => i !== idx) };
    });
  };

  const updateSentence = (idx: number, field: keyof LessonSentence, val: string) => {
    setPreview((p) => {
      if (!p) return p;
      const sentences = [...p.sentences];
      sentences[idx] = { ...sentences[idx], [field]: val };
      return { ...p, sentences };
    });
  };

  const addSentence = () => {
    setPreview((p) => {
      if (!p) return p;
      const id = `s_${p.sentences.length + 1}`;
      return { ...p, sentences: [...p.sentences, { id, japanese: "", reading: "", translation: "" }] };
    });
  };

  const removeSentence = (idx: number) => {
    setPreview((p) => {
      if (!p) return p;
      return { ...p, sentences: p.sentences.filter((_, i) => i !== idx) };
    });
  };

  // ── Render ─────────────────────────────────────────────────────────────

  // If we have a preview, show the edit form
  if (preview) {
    return (
      <div className="flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-zinc-100">Review Lesson</h2>
          <button
            type="button"
            onClick={() => setPreview(null)}
            className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            ← Back to import
          </button>
        </div>

        {error && (
          <div className="rounded-lg border border-red-900/60 bg-red-950/20 px-4 py-2 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* Meta fields */}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Title" value={preview.title} onChange={(v) => updateField("title", v)} />
          <Field label="Grammar Point" value={preview.grammar_point} onChange={(v) => updateField("grammar_point", v)} />
          <Select
            label="JLPT Level"
            value={preview.jlpt_level}
            options={["N5", "N4", "N3", "N2", "N1"]}
            onChange={(v) => updateField("jlpt_level", v)}
          />
          <Select
            label="Category"
            value={preview.category}
            options={["grammar", "vocabulary", "conversation"]}
            onChange={(v) => updateField("category", v)}
          />
        </div>

        <TextArea
          label="Explanation"
          value={preview.explanation}
          onChange={(v) => updateField("explanation", v)}
          rows={3}
        />

        {/* Examples */}
        <ItemListEditor
          label="Examples"
          items={preview.examples}
          onUpdate={updateExample}
          onAdd={addExample}
          onRemove={removeExample}
        />

        {/* Sentences */}
        <ItemListEditor
          label="Practice Sentences"
          items={preview.sentences}
          onUpdate={updateSentence}
          onAdd={addSentence}
          onRemove={removeSentence}
        />

        <button
          type="button"
          onClick={handleSave}
          disabled={saving || !preview.title.trim()}
          className="w-full rounded-lg bg-sky-600 py-2.5 text-sm font-medium text-white
                     transition-colors hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {saving ? "Saving…" : "Save Lesson"}
        </button>
      </div>
    );
  }

  // Import form (no preview yet)
  return (
    <div className="flex flex-col gap-5">
      {/* Tab selector */}
      <div className="flex gap-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => { setTab(t.id); setError(null); }}
            className={`rounded-full border px-4 py-1.5 text-sm transition-colors
              ${tab === t.id
                ? "border-sky-600 bg-sky-900/30 text-sky-200"
                : "border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200"
              }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded-lg border border-red-900/60 bg-red-950/20 px-4 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {tab === "url" && (
        <div className="flex flex-col gap-3">
          <label className="text-xs text-zinc-400">Lesson URL</label>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.tofugu.com/japanese-grammar/..."
            className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100
                       placeholder:text-zinc-600 focus:border-sky-600 focus:outline-none"
          />
          <button
            type="button"
            onClick={handleImport}
            disabled={importing || !url.trim()}
            className="w-full rounded-lg bg-sky-600 py-2.5 text-sm font-medium text-white
                       transition-colors hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {importing ? "Extracting…" : "Import"}
          </button>
        </div>
      )}

      {tab === "paste" && (
        <div className="flex flex-col gap-3">
          <label className="text-xs text-zinc-400">Paste lesson content</label>
          <textarea
            value={pastedText}
            onChange={(e) => setPastedText(e.target.value)}
            rows={8}
            placeholder="Paste the grammar explanation, examples, and practice sentences here…"
            className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100
                       placeholder:text-zinc-600 focus:border-sky-600 focus:outline-none resize-y"
          />
          <button
            type="button"
            onClick={handleImport}
            disabled={importing || !pastedText.trim()}
            className="w-full rounded-lg bg-sky-600 py-2.5 text-sm font-medium text-white
                       transition-colors hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {importing ? "Extracting…" : "Extract Lesson"}
          </button>
        </div>
      )}

      {tab === "manual" && (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-zinc-400">
            Build a lesson from scratch using the structured editor.
          </p>
          <button
            type="button"
            onClick={handleStartBlank}
            className="w-full rounded-lg bg-sky-600 py-2.5 text-sm font-medium text-white
                       transition-colors hover:bg-sky-500"
          >
            Start Blank Lesson
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Small reusable field components
// ---------------------------------------------------------------------------

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-zinc-400">{label}</label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100
                   focus:border-sky-600 focus:outline-none"
      />
    </div>
  );
}

function Select({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-zinc-400">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100
                   focus:border-sky-600 focus:outline-none"
      >
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}

function TextArea({ label, value, onChange, rows = 3 }: { label: string; value: string; onChange: (v: string) => void; rows?: number }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-zinc-400">{label}</label>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={rows}
        className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100
                   focus:border-sky-600 focus:outline-none resize-y"
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Editable list of examples / sentences
// ---------------------------------------------------------------------------

interface ItemListEditorProps {
  label: string;
  items: Array<{ id: string; japanese: string; reading: string; translation: string }>;
  onUpdate: (idx: number, field: "japanese" | "reading" | "translation", val: string) => void;
  onAdd: () => void;
  onRemove: (idx: number) => void;
}

function ItemListEditor({ label, items, onUpdate, onAdd, onRemove }: ItemListEditorProps) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-zinc-300">{label}</span>
        <button
          type="button"
          onClick={onAdd}
          className="text-xs text-sky-400 hover:text-sky-300 transition-colors"
        >
          + Add
        </button>
      </div>
      {items.map((item, idx) => (
        <div key={item.id} className="flex gap-2 items-start">
          <div className="flex-1 grid grid-cols-3 gap-2">
            <input
              value={item.japanese}
              onChange={(e) => onUpdate(idx, "japanese", e.target.value)}
              placeholder="Japanese"
              className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-xs text-zinc-100
                         placeholder:text-zinc-600 focus:border-sky-600 focus:outline-none"
            />
            <input
              value={item.reading}
              onChange={(e) => onUpdate(idx, "reading", e.target.value)}
              placeholder="Reading"
              className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-xs text-zinc-100
                         placeholder:text-zinc-600 focus:border-sky-600 focus:outline-none"
            />
            <input
              value={item.translation}
              onChange={(e) => onUpdate(idx, "translation", e.target.value)}
              placeholder="Translation"
              className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-xs text-zinc-100
                         placeholder:text-zinc-600 focus:border-sky-600 focus:outline-none"
            />
          </div>
          {items.length > 1 && (
            <button
              type="button"
              onClick={() => onRemove(idx)}
              className="mt-1 text-xs text-zinc-600 hover:text-red-400 transition-colors"
            >
              x
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
