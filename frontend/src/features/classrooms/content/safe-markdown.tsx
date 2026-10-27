import { Fragment, type ReactNode } from "react";

export function safeHttpUrl(value: string): string | null {
  try { const url = new URL(value); return (url.protocol === "http:" || url.protocol === "https:") && !url.username && !url.password && !/[\u0000-\u001f]/.test(value) ? url.href : null; } catch { return null; }
}
function inline(text: string): ReactNode[] {
  // Deliberately small, bounded grammar: escaped React text is the default for every token.
  const pattern = /(\[[^\]\n]+\]\([^\s)]+\)|\*\*[^*\n]+\*\*|\*[^*\n]+\*|`[^`\n]+`)/g;
  return text.split(pattern).filter(Boolean).map((part, index) => {
    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
    if (link) { const href = safeHttpUrl(link[2]); return href ? <a key={index} href={href} target="_blank" rel="noopener noreferrer">{link[1]}</a> : <Fragment key={index}>{link[1]}</Fragment>; }
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("*") && part.endsWith("*")) return <em key={index}>{part.slice(1, -1)}</em>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={index}>{part.slice(1, -1)}</code>;
    return <Fragment key={index}>{part}</Fragment>;
  });
}
export function SafeMarkdown({ text }: { text: string }) {
  return <div className="classroom-markdown">{text.replace(/\r\n?/g, "\n").split(/\n\s*\n/).filter(Boolean).map((block, index) => {
    const lines = block.split("\n");
    if (lines.every(line => /^[-*] /.test(line))) return <ul key={index}>{lines.map((line, i) => <li key={i}>{inline(line.slice(2))}</li>)}</ul>;
    if (lines.every(line => /^\d+\. /.test(line))) return <ol key={index}>{lines.map((line, i) => <li key={i}>{inline(line.replace(/^\d+\. /, ""))}</li>)}</ol>;
    if (lines.every(line => line.startsWith("> "))) return <blockquote key={index}>{inline(lines.map(line => line.slice(2)).join("\n"))}</blockquote>;
    if (/^#{1,3} /.test(block)) return <h4 key={index}>{inline(block.replace(/^#{1,3} /, ""))}</h4>;
    return <p key={index}>{lines.map((line, i) => <Fragment key={i}>{i > 0 ? <br /> : null}{inline(line)}</Fragment>)}</p>;
  })}</div>;
}
