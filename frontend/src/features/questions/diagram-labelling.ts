import type {
  DiagramCanvasItem,
  DiagramLabellingConfig,
  Option,
  QuestionGroupModel,
  QuestionModel,
} from "./types";

export const DIAGRAM_GAP_MARKER = "{{gap}}";
export const DIAGRAM_MIN_WIDTH = 0.12;
export const DIAGRAM_MAX_WIDTH = 0.8;

export function createDiagramCanvasItem(questionId: string, index: number): DiagramCanvasItem {
  const width = 0.3;
  const onLeft = index % 2 === 0;
  const x = onLeft ? 0.05 : 0.65;
  const y = Math.min(0.82, 0.06 + (index % 7) * 0.12);
  return {
    id: crypto.randomUUID(),
    question_id: questionId,
    box: { x, y, width },
    arrow: {
      start_x: onLeft ? x + width : x,
      start_y: Math.min(1, y + 0.05),
      end_x: 0.5,
      end_y: Math.min(0.9, y + 0.12),
    },
  };
}

export function splitDiagramPrompt(prompt: string): [string, string] {
  const markerIndex = prompt.indexOf(DIAGRAM_GAP_MARKER);
  if (markerIndex < 0) return [prompt, ""];
  return [
    prompt.slice(0, markerIndex),
    prompt.slice(markerIndex + DIAGRAM_GAP_MARKER.length),
  ];
}

export function diagramPercent(value: number): string {
  return `${Number((value * 100).toFixed(4))}%`;
}

export function diagramLabellingErrors(group: QuestionGroupModel): string[] {
  if (group.question_type !== "diagram_labelling") return [];
  const errors: string[] = [];
  const config = group.config as Partial<DiagramLabellingConfig>;
  const items = Array.isArray(config.items) ? config.items : [];
  const annotations = Array.isArray(config.annotations) ? config.annotations : [];
  const questionIds = group.questions.map((question) => question.id ?? "");
  const itemIds = items.map((item) => item.id);
  const itemQuestionIds = items.map((item) => item.question_id);

  if (!group.image_asset_id) errors.push("Upload a diagram image before saving this group.");
  if (!items.length) errors.push("Add a canvas label for every diagram question.");
  if (itemIds.some((id) => !isUuid(id)) || new Set(itemIds).size !== itemIds.length) {
    errors.push("Diagram canvas items must have unique stable IDs.");
  }
  const annotationIds = annotations.map((annotation) => annotation.id);
  if (annotationIds.some((id) => !isUuid(id)) || new Set([...itemIds, ...annotationIds]).size !== itemIds.length + annotationIds.length) {
    errors.push("Diagram annotations must have unique stable IDs.");
  }
  if (typeof config.title === "string" && config.title.length > 300) {
    errors.push("Diagram title must be 300 characters or fewer.");
  }
  if (annotations.some((annotation) => (
    !["ARROW_LABEL", "NOTE"].includes(annotation.kind)
    || !annotation.text.trim() || annotation.text.length > 300
    || ![annotation.label_x, annotation.label_y].every(normalizedCoordinate)
    || (annotation.kind === "ARROW_LABEL" && ![annotation.target_x, annotation.target_y].every(normalizedCoordinate))
    || (annotation.kind === "NOTE" && (annotation.target_x !== undefined || annotation.target_y !== undefined))
  ))) {
    errors.push("Diagram annotations need text and valid canvas positions.");
  }
  if (
    items.length !== questionIds.length
    || new Set(itemQuestionIds).size !== itemQuestionIds.length
    || itemQuestionIds.some((id) => !questionIds.includes(id))
    || questionIds.some((id) => !itemQuestionIds.includes(id))
  ) {
    errors.push("Every question must be linked to exactly one diagram label.");
  }
  if (items.some((item) => !geometryIsValid(item))) {
    errors.push("Diagram label and arrow positions must remain inside the canvas.");
  }
  if (group.questions.some((question) => question.prompt.split(DIAGRAM_GAP_MARKER).length !== 2)) {
    errors.push("Every diagram sentence must contain exactly one {{gap}} marker.");
  }
  if (group.questions.some((question) => !textLimitsAreValid(question))) {
    errors.push("Diagram answer limits must use 1–20 words and 0–20 numbers.");
  }
  return [...new Set(errors)];
}

export function migrateLegacyDiagramGroup(group: QuestionGroupModel): QuestionGroupModel {
  if (group.question_type !== "diagram_labelling" || Array.isArray(group.config.items)) return group;
  const config = group.config as Partial<DiagramLabellingConfig>;
  const options = Array.isArray(group.config.options) ? group.config.options as Option[] : [];
  const markers = Array.isArray(group.config.markers)
    ? group.config.markers as Array<{ id?: string; question_id?: string; x?: number; y?: number }>
    : [];
  const positionalFallback = markers.length === group.questions.length;
  const questions = group.questions.map((question) => migrateLegacyQuestion(question, options));
  const items = questions.map((question, index) => {
    const matches = markers.filter((marker) => marker.question_id === question.id);
    const marker = matches.length === 1 ? matches[0] : positionalFallback ? markers[index] : undefined;
    const targetX = clamp(Number(marker?.x ?? 0.5));
    const targetY = clamp(Number(marker?.y ?? 0.5));
    const item = createDiagramCanvasItem(question.id ?? crypto.randomUUID(), index);
    return {
      ...item,
      id: marker?.id && isUuid(marker.id) ? marker.id : item.id,
      arrow: { ...item.arrow, end_x: targetX, end_y: targetY },
    };
  });
  return { ...group, config: { title: config.title ?? "", items, annotations: config.annotations ?? [] }, questions };
}

function normalizedCoordinate(value: unknown): boolean {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}

function migrateLegacyQuestion(question: QuestionModel, options: Option[]): QuestionModel {
  const answerKey = question.answer_key;
  let accepted = Array.isArray(answerKey.accepted)
    ? (answerKey.accepted as unknown[]).map(String).filter((value) => value.trim())
    : [];
  if (answerKey.kind !== "TEXT") {
    const selected = String(answerKey.value ?? accepted[0] ?? "");
    const matches = options.filter((option) => selected === option.id || selected === option.label);
    accepted = matches.length === 1 && matches[0].text.trim() ? [matches[0].text.trim()] : [];
  }
  let prompt = question.prompt;
  if (!prompt.includes(DIAGRAM_GAP_MARKER)) {
    prompt = /_{2,}/.test(prompt)
      ? prompt.replace(/_{2,}/, DIAGRAM_GAP_MARKER)
      : `${prompt.trimEnd()} ${DIAGRAM_GAP_MARKER}`.trim();
  }
  return {
    ...question,
    prompt,
    config: {
      max_words: question.config.max_words ?? 2,
      max_numbers: question.config.max_numbers ?? 1,
    },
    answer_key: {
      kind: "TEXT",
      accepted,
      case_sensitive: Boolean(answerKey.case_sensitive),
    },
  };
}

function geometryIsValid(item: DiagramCanvasItem): boolean {
  const values = [
    item.box?.x,
    item.box?.y,
    item.box?.width,
    item.arrow?.start_x,
    item.arrow?.start_y,
    item.arrow?.end_x,
    item.arrow?.end_y,
  ];
  return values.every((value) => Number.isFinite(value) && value >= 0 && value <= 1)
    && item.box.width >= DIAGRAM_MIN_WIDTH
    && item.box.width <= DIAGRAM_MAX_WIDTH
    && item.box.x + item.box.width <= 1;
}

function textLimitsAreValid(question: QuestionModel): boolean {
  const maxWords = question.config.max_words;
  const maxNumbers = question.config.max_numbers;
  return (maxWords == null || (Number.isInteger(maxWords) && Number(maxWords) >= 1 && Number(maxWords) <= 20))
    && (maxNumbers == null || (Number.isInteger(maxNumbers) && Number(maxNumbers) >= 0 && Number(maxNumbers) <= 20));
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

function clamp(value: number): number {
  return Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0.5;
}
