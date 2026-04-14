"use client";

import type { LessonModule, LessonSessionMeta } from "@/lib/types";

// ---------------------------------------------------------------------------
// Stage config — display order matches the lesson flow
// ---------------------------------------------------------------------------

interface StageConfig {
  module: LessonModule;
  label: string;
  icon: string;
  shortLabel: string;
}

const STAGES: StageConfig[] = [
  { module: "presentation", label: "Intro",       icon: "📖", shortLabel: "Intro" },
  { module: "examples",     label: "Examples",    icon: "💡", shortLabel: "Examples" },
  { module: "recognition",  label: "Recognition", icon: "✅", shortLabel: "Recognition" },
  { module: "conversation", label: "Practice",    icon: "💬", shortLabel: "Practice" },
];

// ---------------------------------------------------------------------------
// Progress bar (top, always visible)
// ---------------------------------------------------------------------------

interface ProgressBarProps {
  meta: LessonSessionMeta;
}

export function LessonProgressBar({ meta }: ProgressBarProps) {
  return (
    <div className="flex items-center gap-0 w-full">
      {STAGES.map((stage, i) => {
        const state = getStageState(stage.module, meta);
        return (
          <div key={stage.module} className="flex items-center flex-1">
            <div className={`
              flex flex-col items-center gap-1 flex-1 py-2 px-1 rounded-lg text-center
              transition-colors duration-200
              ${state === "active"   ? "bg-sky-900/40 text-sky-300" : ""}
              ${state === "visited"  ? "text-zinc-400" : ""}
              ${state === "unvisited"? "text-zinc-600" : ""}
            `}>
              <span className="text-lg leading-none">{stage.icon}</span>
              <span className={`text-[11px] font-medium tracking-wide
                ${state === "active"   ? "text-sky-300" : ""}
                ${state === "visited"  ? "text-zinc-400" : ""}
                ${state === "unvisited"? "text-zinc-600" : ""}
              `}>
                {stage.shortLabel}
                {state === "visited" && <span className="ml-1 text-emerald-400">✓</span>}
              </span>
            </div>
            {i < STAGES.length - 1 && (
              <div className={`h-px flex-shrink-0 w-4 mx-1
                ${getStageState(STAGES[i + 1].module, meta) !== "unvisited" ? "bg-zinc-500" : "bg-zinc-700"}
              `} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sidebar stage nav
// ---------------------------------------------------------------------------

interface StageNavProps {
  meta: LessonSessionMeta;
  loading: boolean;
  onSwitch: (module: LessonModule) => void;
}

export function StageNav({ meta, loading, onSwitch }: StageNavProps) {
  return (
    <div className="flex flex-col gap-2 w-44">
      <p className="text-[11px] text-zinc-500 font-medium uppercase tracking-wider mb-1">
        Stages
      </p>
      {STAGES.map((stage) => {
        const state = getStageState(stage.module, meta);
        const isActive = state === "active";
        const isQaActive = meta.active_module === "qa" && meta.qa_return_module === stage.module;

        return (
          <button
            key={stage.module}
            onClick={() => onSwitch(stage.module)}
            disabled={loading}
            className={`
              flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm
              transition-colors duration-150
              disabled:opacity-40 disabled:cursor-not-allowed
              ${isActive
                ? "bg-sky-900/50 border border-sky-700 text-sky-200"
                : state === "visited"
                  ? "bg-zinc-800/60 border border-zinc-700 text-zinc-300 hover:border-zinc-500 hover:text-zinc-100"
                  : "bg-zinc-900/40 border border-zinc-800 text-zinc-500 hover:border-zinc-700 hover:text-zinc-400"
              }
            `}
          >
            <span className="text-base">{stage.icon}</span>
            <span className="flex-1">{stage.label}</span>
            {state === "visited" && !isActive && (
              <span className="text-[10px] text-emerald-400">✓</span>
            )}
            {isActive && (
              <span className="text-[10px] text-sky-400">▶</span>
            )}
          </button>
        );
      })}

      <div className="mt-2 border-t border-zinc-800 pt-2">
        <button
          onClick={() => onSwitch("qa")}
          disabled={loading || meta.active_module === "qa"}
          className={`
            flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm w-full
            transition-colors duration-150
            disabled:opacity-40 disabled:cursor-not-allowed
            ${meta.active_module === "qa"
              ? "bg-amber-900/30 border border-amber-700 text-amber-300"
              : "bg-zinc-900/40 border border-zinc-800 text-zinc-500 hover:border-zinc-700 hover:text-zinc-400"
            }
          `}
        >
          <span className="text-base">❓</span>
          <span>Ask a question</span>
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type StageState = "active" | "visited" | "unvisited";

function getStageState(module: LessonModule, meta: LessonSessionMeta): StageState {
  // QA is a transient overlay — don't count it as a stage state
  const effectiveActive = meta.active_module === "qa"
    ? (meta.qa_return_module ?? "presentation")
    : meta.active_module;

  if (effectiveActive === module) return "active";
  if (meta.module_history.includes(module)) return "visited";
  return "unvisited";
}
