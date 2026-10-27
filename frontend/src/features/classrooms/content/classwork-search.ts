import type { ClassworkGroup } from "./classwork-groups";

/** Vietnamese đ and combining accents share the same search spelling. */
export function normalizeClassworkSearch(value: string) {
  return value.toLocaleLowerCase("vi").normalize("NFD").replace(/\p{M}/gu, "").replace(/đ/g, "d").trim();
}

export function searchClasswork(groups: ClassworkGroup[], query: string): ClassworkGroup[] {
  const words = normalizeClassworkSearch(query).split(/\s+/).filter(Boolean);
  if (!words.length) return groups;
  const matches = (...values: (string | null | undefined)[]) => {
    const text = normalizeClassworkSearch(values.filter(Boolean).join(" "));
    return words.every(word => text.includes(word));
  };
  return groups.flatMap(group => {
    // Finding a topic preserves its complete context rather than hiding its children.
    if (group.section && matches(group.section.title, group.section.description)) return [group];
    const rows = group.rows.filter(({ resource, assignment }) => matches(resource?.title, resource?.description, resource?.body, assignment?.title, assignment?.version?.test_title, assignment?.note));
    return rows.length ? [{ ...group, rows }] : [];
  });
}
