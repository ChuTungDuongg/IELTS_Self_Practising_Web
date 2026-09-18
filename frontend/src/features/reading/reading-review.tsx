"use client";

import { questionRegistry } from "@/features/questions/registry";
import type { ExamGroup } from "@/features/questions/types";

type ReviewData = Awaited<ReturnType<typeof import("@/lib/api/exam").getReadingReview>>;

export function ReadingReviewView({ data }: { data: ReviewData }) {
  const answers = new Map(data.review.answers.map((item) => [item.question_id, item]));
  const values = Object.fromEntries(data.review.answers.map((item) => [item.question_id, item.value]));
  return <div className="space-y-8">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Reading review</p><h1 className="mt-2 text-3xl font-semibold">{data.review.test_title}</h1></div><p className="text-xl font-semibold">Score {data.review.attempt.raw_score ?? "—"} / {data.review.attempt.max_score ?? "—"}</p></div>
    {data.passages.map((passage) => <section key={passage.id} className="grid gap-6 rounded-xl border border-[var(--line)] bg-[var(--surface)] p-6 lg:grid-cols-2"><article><h2 className="mb-5 text-xl font-semibold">{passage.title}</h2><div className="space-y-4 leading-7">{passage.blocks.map((block) => block.type === "heading" ? <h3 key={block.id} className="font-semibold">{block.text}</h3> : <p key={block.id}><b className="mr-2">{block.label}</b>{block.text}</p>)}</div></article><div>{passage.question_groups.map((group) => { const definition = questionRegistry[group.question_type as keyof typeof questionRegistry]; if (!definition) return null; const Renderer = definition.ReviewRenderer; return <div key={group.id} className="mb-8"><p className="mb-4 rounded-md bg-[var(--surface-soft)] p-3 text-sm font-medium">{group.instruction}</p><Renderer group={group as ExamGroup} values={values} passageBlocks={passage.blocks} disabled /><div className="mt-4 space-y-2">{group.questions.map((question) => { const answer = answers.get(question.id); const optionLists = [...((group.config.options as Array<{ id: string; label: string; text: string }> | undefined) ?? []), ...((question.config.options as Array<{ id: string; label: string; text: string }> | undefined) ?? [])]; const display = (value: unknown) => optionLists.find((option) => option.id === value) ? `${optionLists.find((option) => option.id === value)!.label} — ${optionLists.find((option) => option.id === value)!.text}` : String(value ?? "—"); return <div key={question.id} className={`rounded-md border p-3 text-sm ${answer?.is_correct ? "border-emerald-400 bg-emerald-50 text-emerald-950" : "border-red-300 bg-red-50 text-red-950"}`}><b>Q{question.number}</b> · Your answer: {display(answer?.value)} · Correct: {display(question.answer_key.value ?? (question.answer_key.accepted as string[] | undefined)?.[0])}</div>; })}</div></div>; })}</div></section>)}
  </div>;
}
