export function countWords(text: string): number {
  return Array.from(text.matchAll(/[\p{L}\p{N}]+(?:['’\-][\p{L}\p{N}]+)*/gu)).length;
}
