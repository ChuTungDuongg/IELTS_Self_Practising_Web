import type { ClassworkItem } from "@/lib/api/classroom-content";
export function ordered<T extends { id: string; position: number }>(items: T[]): T[] { return [...items].sort((a, b) => a.position - b.position || a.id.localeCompare(b.id)); }
export function moveBy(ids: string[], id: string, delta: number): string[] {
  const index = ids.indexOf(id), target = index + delta; if (index < 0 || target < 0 || target >= ids.length) return ids;
  const next = [...ids]; next.splice(index, 1); next.splice(target, 0, id); return next;
}
export function targetItemOrder(items: ClassworkItem[], sectionId: string | null, itemId: string, beforeId?: string): string[] {
  const ids = ordered(items.filter(item => item.section_id === sectionId && item.id !== itemId)).map(item => item.id);
  const index = beforeId ? ids.indexOf(beforeId) : -1; ids.splice(index < 0 ? ids.length : index, 0, itemId); return ids;
}
