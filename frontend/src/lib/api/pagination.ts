export type PageOptions = { limit?: number; offset?: number; };
export const GOVERNANCE_PAGE_SIZE = 20;

export function pageOffset(value?: string): number {
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : 0;
}

export function appendPageQuery(path: string, options?: PageOptions): string {
  if (!options) return path;
  const params = new URLSearchParams();
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  if (options.offset !== undefined) params.set("offset", String(options.offset));
  return params.size ? `${path}${path.includes("?") ? "&" : "?"}${params}` : path;
}
