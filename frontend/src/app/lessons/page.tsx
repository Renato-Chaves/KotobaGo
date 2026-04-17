"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { LessonMap } from "@/components/lesson/LessonMap";
import { api } from "@/lib/api";
import type { Lesson, LessonCategory } from "@/lib/types";

const TABS: Array<{ id: LessonCategory; label: string }> = [
  { id: "grammar", label: "Grammar" },
  { id: "vocabulary", label: "Vocabulary" },
  { id: "conversation", label: "Conversation" },
];

export default function LessonsPage() {
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [activeTab, setActiveTab] = useState<LessonCategory>("grammar");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    api.listLessons()
      .then((res) => {
        if (mounted) {
          setLessons(res);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (mounted) {
          setError(e instanceof Error ? e.message : "Failed to load lessons");
          setLoading(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, []);

  const byCategory = useMemo(() => {
    return lessons.filter((l) => l.category === activeTab);
  }, [lessons, activeTab]);

  const hasAnyInTab = byCategory.length > 0;

  const handleLaunch = (lesson: Lesson) => {
    if (lesson.progress_status === "locked") return;
    const sessionQuery = lesson.active_session_id ? `?session=${lesson.active_session_id}` : "";
    window.location.href = `/lessons/${lesson.id}${sessionQuery}`;
  };

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-6 px-4 py-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-100">Lessons</h1>
          <p className="mt-1 text-sm text-zinc-400">Pick a lesson and practice in guided stages.</p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/lessons/new"
            className="rounded-lg bg-sky-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-sky-500"
          >
            + Create Lesson
          </Link>
          <Link href="/" className="text-sm text-zinc-500 transition-colors hover:text-zinc-300">← Home</Link>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`rounded-full border px-4 py-1.5 text-sm transition-colors
                ${isActive
                  ? "border-sky-600 bg-sky-900/30 text-sky-200"
                  : "border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200"
                }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {loading ? (
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 px-5 py-10 text-center text-zinc-500">
          Loading lessons…
        </div>
      ) : error ? (
        <div className="rounded-xl border border-red-900/60 bg-red-950/20 px-5 py-4 text-sm text-red-300">
          {error}
        </div>
      ) : hasAnyInTab ? (
        <LessonMap lessons={byCategory} onLaunch={handleLaunch} />
      ) : (
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 px-5 py-10 text-center text-zinc-500">
          No lessons yet in this category.
        </div>
      )}
    </div>
  );
}
