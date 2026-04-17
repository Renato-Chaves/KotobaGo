"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";

import { LessonImportForm } from "@/components/lesson/LessonImportForm";

const SOURCE_CARDS = [
  {
    name: "Tofugu",
    url: "https://www.tofugu.com/japanese-grammar/",
    description:
      "Narrative, metaphor-driven explanations. 126+ grammar points. Recommended primary source.",
    accent: "border-amber-700/60 bg-amber-950/15",
  },
  {
    name: "Wasabi",
    url: "https://wasabi-jpn.com/magazine/japanese-grammar/wasabis-online-japanese-grammar-reference/",
    description:
      "Structured reference with furigana. 92 lessons. Good fallback for points Tofugu doesn't cover.",
    accent: "border-emerald-700/60 bg-emerald-950/15",
  },
];

export default function NewLessonPage() {
  const router = useRouter();

  const handleSaved = (id: number) => {
    router.push("/lessons");
  };

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-6 px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-100">
            Create Lesson
          </h1>
          <p className="mt-1 text-sm text-zinc-400">
            Import from a URL, paste content, or write from scratch.
          </p>
        </div>
        <Link
          href="/lessons"
          className="text-sm text-zinc-500 transition-colors hover:text-zinc-300"
        >
          ← Back to Lessons
        </Link>
      </div>

      {/* Two-panel layout */}
      <div className="grid gap-6 md:grid-cols-[1fr_300px]">
        {/* Left panel — import form */}
        <div className="rounded-2xl border border-zinc-800 bg-zinc-950/60 p-5 md:p-6">
          <LessonImportForm onSaved={handleSaved} />
        </div>

        {/* Right panel — source suggestion cards */}
        <div className="flex flex-col gap-4">
          <h3 className="text-xs font-medium uppercase tracking-widest text-zinc-500">
            Recommended Sources
          </h3>
          {SOURCE_CARDS.map((src) => (
            <div
              key={src.name}
              className={`rounded-xl border p-4 ${src.accent}`}
            >
              <p className="text-sm font-semibold text-zinc-200">{src.name}</p>
              <p className="mt-1 text-xs leading-relaxed text-zinc-400">
                {src.description}
              </p>
              <a
                href={src.url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 inline-block text-xs text-sky-400 transition-colors hover:text-sky-300"
              >
                Browse grammar index
              </a>
            </div>
          ))}

          <div className="rounded-xl border border-zinc-800 p-4">
            <p className="text-xs font-medium text-zinc-300">How it works</p>
            <ol className="mt-2 flex flex-col gap-1 text-[11px] leading-relaxed text-zinc-500">
              <li>1. Browse a source and find a grammar lesson</li>
              <li>2. Copy the URL or the page text</li>
              <li>3. Paste it in the import form</li>
              <li>4. Review the extracted structure</li>
              <li>5. Edit anything, then save</li>
            </ol>
          </div>
        </div>
      </div>
    </div>
  );
}
