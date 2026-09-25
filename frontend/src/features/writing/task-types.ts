import { z } from "zod";

export const taskOneTypes = [
  ["LINE_GRAPH", "Line graph"],
  ["BAR_CHART", "Bar chart"],
  ["PIE_CHART", "Pie chart"],
  ["TABLE", "Table"],
  ["MIXED_CHARTS", "Mixed / multiple charts"],
  ["PROCESS", "Process diagram"],
  ["MAP_PLAN", "Map / plan"],
  ["OBJECT_SYSTEM_DIAGRAM", "Object / system diagram"],
  ["OTHER_VISUAL", "Other visual"],
] as const;

export const taskTwoTypes = [
  ["OPINION", "Opinion / Agree or disagree"],
  ["DISCUSS_BOTH_VIEWS", "Discuss both views"],
  ["DISCUSS_BOTH_VIEWS_AND_OPINION", "Discuss both views + give your opinion"],
  ["ADVANTAGES_DISADVANTAGES", "Advantages / disadvantages"],
  ["ADVANTAGES_OUTWEIGH_DISADVANTAGES", "Do advantages outweigh disadvantages?"],
  ["PROBLEM_SOLUTION", "Problem / solution"],
  ["CAUSE_SOLUTION", "Causes / solutions"],
  ["TWO_PART_QUESTION", "Two-part / direct questions"],
  ["OTHER_ESSAY", "Other essay"],
] as const;

export const writingTaskTypeSchema = z.enum([
  ...taskOneTypes.map(([id]) => id),
  ...taskTwoTypes.map(([id]) => id),
]);
export type WritingTaskType = z.infer<typeof writingTaskTypeSchema>;

const labels: Record<WritingTaskType, string> = Object.fromEntries([...taskOneTypes, ...taskTwoTypes]) as Record<WritingTaskType, string>;

export function writingTaskTypeLabel(type: WritingTaskType | null): string {
  return type ? labels[type] : "Unclassified";
}
