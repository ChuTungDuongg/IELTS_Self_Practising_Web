export function scrollQuestionIntoPane(pane: HTMLElement, target: HTMLElement): void {
  const paneRect = pane.getBoundingClientRect();
  const targetRect = target.getBoundingClientRect();
  const top = pane.scrollTop + targetRect.top - paneRect.top - (pane.clientHeight - targetRect.height) / 2;
  const maximum = Math.max(0, pane.scrollHeight - pane.clientHeight);
  pane.scrollTo({ top: Math.max(0, Math.min(top, maximum)), behavior: "auto" });
}

export function revealQuestionChip(strip: HTMLElement, chip: HTMLElement): void {
  const stripRect = strip.getBoundingClientRect();
  const chipRect = chip.getBoundingClientRect();
  const delta = chipRect.left < stripRect.left
    ? chipRect.left - stripRect.left
    : chipRect.right > stripRect.right ? chipRect.right - stripRect.right : 0;
  if (delta !== 0) strip.scrollTo({ left: strip.scrollLeft + delta, behavior: "auto" });
}
