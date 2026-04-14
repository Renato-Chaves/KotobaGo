const HealthCheck = async () => {
  // Server Components run inside Docker — use the internal Docker network URL.
  // NEXT_PUBLIC_API_URL is for Client Components (browser → host machine).
  const apiUrl = process.env.API_URL_INTERNAL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

  let status: string | null = null;
  try {
    const res = await fetch(`${apiUrl}/health`, { cache: "no-store" });
    const data = await res.json();
    status = data.status;
  } catch {
    // backend unreachable
  }

  if (status) {
    return <p className="text-sm text-emerald-400">Backend: {status}</p>;
  }
  return <p className="text-sm text-red-400">Backend: unreachable</p>;
}

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6">
      <h1 className="text-4xl font-bold tracking-tight">
        ことばGo
      </h1>
      <p className="text-zinc-400">
        AI-powered Japanese learning through comprehensible input
      </p>
      <HealthCheck />
      <div className="flex gap-3 mt-2 flex-wrap justify-center">
        <a
          href="/story"
          className="px-6 py-3 rounded-xl bg-sky-600 hover:bg-sky-500
                     text-white font-medium transition-colors"
        >
          Start Story →
        </a>
        <a
          href="/lessons"
          className="px-6 py-3 rounded-xl bg-amber-700 hover:bg-amber-600
                     text-white font-medium transition-colors"
        >
          Lessons →
        </a>
        <a
          href="/vocab"
          className="px-6 py-3 rounded-xl border border-zinc-700 hover:border-zinc-500
                     text-zinc-300 hover:text-zinc-100 font-medium transition-colors"
        >
          Vocabulary →
        </a>
        <a
          href="/profile"
          className="px-6 py-3 rounded-xl border border-zinc-700 hover:border-zinc-500
                     text-zinc-300 hover:text-zinc-100 font-medium transition-colors"
        >
          Profile →
        </a>
      </div>
    </div>
  );
}