"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { Lesson, LessonProgressStatus } from "@/lib/types";

interface Props {
  lessons: Lesson[];
  onLaunch: (lesson: Lesson) => void;
}

// Layout constants
const NODE_RADIUS = 32;
const Y_START = 80;
const Y_GAP = 140;
const X_LEFT_PCT = 30;
const X_RIGHT_PCT = 70;

export function LessonMap({ lessons, onLaunch }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const sorted = [...lessons].sort((a, b) => {
    if (a.stage !== b.stage) return a.stage - b.stage;
    return a.order - b.order;
  });

  // Measure container width for SVG coordinate calculation
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(([entry]) => {
      setContainerWidth(entry.contentRect.width);
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const points = sorted.map((lesson, idx) => ({
    lesson,
    xPct: idx % 2 === 0 ? X_LEFT_PCT : X_RIGHT_PCT,
    x: containerWidth * (idx % 2 === 0 ? X_LEFT_PCT : X_RIGHT_PCT) / 100,
    y: Y_START + idx * Y_GAP,
  }));

  const mapHeight = Math.max(260, Y_START + Math.max(0, points.length - 1) * Y_GAP + 200);

  // Default-select first non-locked lesson
  const resolvedSelectedId =
    selectedId !== null && points.some((p) => p.lesson.id === selectedId)
      ? selectedId
      : (points.find((p) => p.lesson.progress_status !== "locked")?.lesson.id ??
         points[0]?.lesson.id ?? null);

  const selected = points.find((p) => p.lesson.id === resolvedSelectedId) ?? null;

  const buildPath = useCallback(() => {
    if (points.length < 2 || containerWidth === 0) return "";

    let d = `M ${points[0].x} ${points[0].y}`;
    for (let i = 0; i < points.length - 1; i++) {
      const a = points[i];
      const b = points[i + 1];
      // S-curve control points: push handles ~55% of vertical gap
      const handleY = Y_GAP * 0.55;
      d += ` C ${a.x} ${a.y + handleY}, ${b.x} ${b.y - handleY}, ${b.x} ${b.y}`;
    }
    return d;
  }, [points, containerWidth]);

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-950/60 p-4 md:p-6">
      {points.length === 0 ? (
        <div className="py-14 text-center text-zinc-500">No lessons in this category yet.</div>
      ) : (
        <div ref={containerRef} className="relative w-full" style={{ height: mapHeight }}>
          {/* SVG connector path */}
          {containerWidth > 0 && points.length >= 2 && (
            <svg
              className="pointer-events-none absolute inset-0"
              width="100%"
              height={mapHeight}
              aria-hidden
            >
              <defs>
                <linearGradient id="splineGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="rgb(56 189 248)" stopOpacity="0.5" />
                  <stop offset="100%" stopColor="rgb(56 189 248)" stopOpacity="0.15" />
                </linearGradient>
                <filter id="pathGlow">
                  <feGaussianBlur stdDeviation="3" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>
              {/* Glow layer */}
              <path
                d={buildPath()}
                fill="none"
                stroke="rgba(56, 189, 248, 0.15)"
                strokeWidth={6}
                strokeLinecap="round"
                filter="url(#pathGlow)"
              />
              {/* Main path */}
              <path
                d={buildPath()}
                fill="none"
                stroke="url(#splineGrad)"
                strokeWidth={2.5}
                strokeLinecap="round"
                strokeDasharray="8 6"
              />
            </svg>
          )}

          {/* Nodes */}
          {points.map((p) => {
            const state = p.lesson.progress_status;
            const isSelected = p.lesson.id === resolvedSelectedId;
            return (
              <button
                key={p.lesson.id}
                type="button"
                disabled={state === "locked"}
                onClick={() => setSelectedId(p.lesson.id)}
                className="absolute -translate-x-1/2 -translate-y-1/2 transition-all duration-200 focus:outline-none disabled:cursor-not-allowed"
                style={{ left: `${p.xPct}%`, top: p.y }}
              >
                {/* Outer ring */}
                <div
                  className={`flex items-center justify-center rounded-full transition-all duration-200
                    ${nodeRingClasses(state, isSelected)}`}
                  style={{ width: NODE_RADIUS * 2, height: NODE_RADIUS * 2 }}
                >
                  {/* Inner circle */}
                  <div
                    className={`flex items-center justify-center rounded-full text-lg font-bold
                      ${nodeInnerClasses(state)}`}
                    style={{ width: NODE_RADIUS * 2 - 10, height: NODE_RADIUS * 2 - 10 }}
                  >
                    {nodeIcon(state)}
                  </div>
                </div>
                {/* Label below the node */}
                <div className="mt-2 w-[140px] -translate-x-[calc(50%-32px)] text-center">
                  <p className={`truncate text-xs font-semibold ${state === "locked" ? "text-zinc-600" : "text-zinc-200"}`}>
                    {p.lesson.title}
                  </p>
                  <p className="text-[10px] text-zinc-500">
                    {p.lesson.jlpt_level}
                  </p>
                </div>
              </button>
            );
          })}

          {/* Detail card for selected node */}
          {selected && (
            <DetailCard
              point={selected}
              onLaunch={() => onLaunch(selected.lesson)}
            />
          )}
        </div>
      )}
    </div>
  );
}

// ── Detail card ──────────────────────────────────────────────────────────────

interface DetailCardProps {
  point: { lesson: Lesson; xPct: number; y: number };
  onLaunch: () => void;
}

function DetailCard({ point, onLaunch }: DetailCardProps) {
  const { lesson, xPct, y } = point;
  const isLeft = xPct <= 50;
  return (
    <div
      className="absolute z-10 w-[260px] rounded-xl border border-zinc-700/80 bg-zinc-900/95 p-4 shadow-2xl backdrop-blur-sm transition-all duration-200"
      style={{
        left: isLeft ? `calc(${xPct}% + 80px)` : `calc(${xPct}% - 80px)`,
        top: y - 20,
        transform: isLeft ? "translateX(0)" : "translateX(-100%)",
      }}
    >
      <p className="text-sm font-semibold text-zinc-100">{lesson.title}</p>
      {lesson.grammar_point && (
        <p className="mt-0.5 text-xs text-zinc-400">{lesson.grammar_point}</p>
      )}
      <div className="mt-2 flex items-center gap-2">
        <StatusPill state={lesson.progress_status} />
        <span className="text-[10px] text-zinc-500">
          Stage {lesson.stage}.{lesson.order}
        </span>
      </div>
      <button
        type="button"
        disabled={lesson.progress_status === "locked"}
        onClick={onLaunch}
        className="mt-3 w-full rounded-lg bg-sky-600 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {lesson.progress_status === "active"
          ? "Continue"
          : lesson.progress_status === "completed"
            ? "Start again"
            : "Start"}
      </button>
    </div>
  );
}

// ── Status pill ──────────────────────────────────────────────────────────────

function StatusPill({ state }: { state: LessonProgressStatus }) {
  const map: Record<LessonProgressStatus, { label: string; cls: string }> = {
    completed: { label: "Done", cls: "bg-emerald-900/60 text-emerald-300" },
    active:    { label: "In progress", cls: "bg-amber-900/60 text-amber-300" },
    available: { label: "Available", cls: "bg-sky-900/60 text-sky-300" },
    locked:    { label: "Locked", cls: "bg-zinc-800 text-zinc-500" },
  };
  const { label, cls } = map[state];
  return <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${cls}`}>{label}</span>;
}

// ── Node styling helpers ─────────────────────────────────────────────────────

function nodeRingClasses(state: LessonProgressStatus, isSelected: boolean): string {
  const ring = isSelected ? "ring-2 ring-offset-2 ring-offset-zinc-950" : "";
  switch (state) {
    case "completed":
      return `border-2 border-emerald-500/60 ${ring} ${isSelected ? "ring-emerald-400/60" : ""}`;
    case "active":
      return `border-2 border-amber-500/60 animate-pulse ${ring} ${isSelected ? "ring-amber-400/60" : ""}`;
    case "available":
      return `border-2 border-sky-500/60 ${ring} ${isSelected ? "ring-sky-400/60" : ""}`;
    default:
      return `border-2 border-zinc-700 ${ring} ${isSelected ? "ring-zinc-600" : ""}`;
  }
}

function nodeInnerClasses(state: LessonProgressStatus): string {
  switch (state) {
    case "completed":
      return "bg-emerald-600/30 text-emerald-300";
    case "active":
      return "bg-amber-600/20 text-amber-300";
    case "available":
      return "bg-sky-600/20 text-sky-300";
    default:
      return "bg-zinc-800/60 text-zinc-600";
  }
}

function nodeIcon(state: LessonProgressStatus): string {
  switch (state) {
    case "completed": return "\u2713";
    case "active": return "\u25B6";
    case "available": return "\u2605";
    default: return "\uD83D\uDD12";
  }
}
