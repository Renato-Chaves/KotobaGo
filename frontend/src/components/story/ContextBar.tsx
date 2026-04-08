"use client";

interface Props {
  usagePct: number; // 0–100
}

const SIZE = 48;
const STROKE = 4;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

// Color transitions: green → yellow → red as context fills up
function strokeColor(pct: number): string {
  if (pct < 60) return "#34d399"; // emerald-400
  if (pct < 80) return "#facc15"; // yellow-400
  return "#f87171";               // red-400
}

export function ContextBar({ usagePct }: Props) {
  const clamped = Math.min(100, Math.max(0, usagePct));
  const offset = CIRCUMFERENCE * (1 - clamped / 100);

  return (
    <div className="flex items-center gap-2" title={`Context window: ${clamped}% used`}>
      <svg width={SIZE} height={SIZE} className="-rotate-90">
        {/* Background track */}
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          fill="none"
          stroke="#3f3f46" // zinc-700
          strokeWidth={STROKE}
        />
        {/* Progress arc */}
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          fill="none"
          stroke={strokeColor(clamped)}
          strokeWidth={STROKE}
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 0.5s ease, stroke 0.5s ease" }}
        />
      </svg>
      <span className="text-xs text-zinc-500">{Math.round(clamped)}%</span>
    </div>
  );
}
