import { LessonCanvas } from "@/components/lesson/LessonCanvas";

interface Props {
  params: Promise<{ id: string }>;
}

export default async function LessonPage({ params }: Props) {
  const { id } = await params;
  const lessonId = parseInt(id, 10);

  if (isNaN(lessonId)) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-zinc-400">Invalid lesson ID.</p>
      </div>
    );
  }

  return <LessonCanvas lessonId={lessonId} />;
}
