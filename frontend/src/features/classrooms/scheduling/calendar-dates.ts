/** Local civil-date arithmetic keeps date-only values stable across timezones and DST. */
export function dayKey(value: Date) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}
export function civilDate(key: string) {
  const [year, month, day] = key.split("-").map(Number);
  return new Date(year, month - 1, day);
}
export function addDays(value: Date, days: number) { return new Date(value.getFullYear(), value.getMonth(), value.getDate() + days); }
export function monthStart(value: Date) { return new Date(value.getFullYear(), value.getMonth(), 1); }
export function weekStart(value: Date) { return addDays(value, -((value.getDay() + 6) % 7)); }
export function calendarMonth(key: string) {
  const first = monthStart(civilDate(key)), end = new Date(first.getFullYear(), first.getMonth() + 1, 1);
  const start = weekStart(first), gridEnd = addDays(weekStart(addDays(end, -1)), 7);
  const days: Date[] = [];
  for (let day = start; day < gridEnd; day = addDays(day, 1)) days.push(day);
  return { first, end, start, gridEnd, days };
}
export function moveMonth(selected: string, delta: number) {
  const value = civilDate(selected), last = new Date(value.getFullYear(), value.getMonth() + delta + 1, 0);
  return dayKey(new Date(last.getFullYear(), last.getMonth(), Math.min(value.getDate(), last.getDate())));
}
