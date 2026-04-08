"use client";

interface Props {
  choices: string[];
  disabled: boolean;
  onChoice: (choice: string) => void;
}

export function ChoiceButtons({ choices, disabled, onChoice }: Props) {
  return (
    <div className="flex flex-col gap-2 mt-6">
      {choices.map((choice, i) => (
        <button
          key={i}
          onClick={() => onChoice(choice)}
          disabled={disabled}
          className="w-full text-left px-4 py-3 rounded-lg border border-zinc-700
                     bg-zinc-900 text-zinc-100 text-base
                     hover:border-sky-500 hover:bg-zinc-800
                     disabled:opacity-40 disabled:cursor-not-allowed
                     transition-colors duration-150"
        >
          {choice}
        </button>
      ))}
    </div>
  );
}
