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
    </div>
  );
}

async function HealthCheck() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  try {
    const res = await fetch(`${apiUrl}/health`, {
      cache: "no-store",
    });
    const data = await res.json();

    return (
      <p className="text-sm text-emerald-400">
        Backend: {data.status}
      </p>
    );
  } catch {
    return (
      <p className="text-sm text-red-400">
        Backend: unreachable
      </p>
    );
  }
}
