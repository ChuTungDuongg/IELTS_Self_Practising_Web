"""Check local inline Markdown links/anchors in docs and benchmark READMEs offline."""

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]


def without_fences(value):
    return re.sub(r"```[\s\S]*?```", "", value)


def heading_slug(value):
    value = re.sub(r"<[^>]+>", "", value).strip().lower().replace("`", "").replace("*", "")
    return "".join(
        char for char in value if char in "-_ " or unicodedata.category(char)[0] in "LN"
    ).replace(" ", "-")


def anchors(value):
    result = set(re.findall(r"<a\s+(?:id|name)=[\"']([^\"']+)", value))
    counts = Counter()
    for heading in re.findall(r"^#{1,6} +(.+?)\s*#*$", without_fences(value), re.M):
        slug = heading_slug(heading)
        result.add(slug + (f"-{counts[slug]}" if counts[slug] else ""))
        counts[slug] += 1
    return result


def validate():
    files = sorted(
        [*ROOT.joinpath("docs").rglob("*.md"), *ROOT.joinpath("benchmarks").rglob("README.md")]
    )
    files = [path for path in files if ".runs" not in path.parts]
    contents = {path.resolve(): path.read_text(encoding="utf-8") for path in files}
    errors, checked = [], 0
    for path in files:
        for match in re.finditer(r"\[[^\]\n]*\]\(([^\n]+?)\)", without_fences(contents[path])):
            target = match[1].split(' "')[0].strip("<>")
            if re.match(r"\w+://|mailto:|data:", target):
                continue
            checked += 1
            name, _, fragment = target.partition("#")
            destination = (path.parent / unquote(name)).resolve() if name else path
            reason = None
            if not destination.exists():
                reason = "missing file/directory"
            elif fragment and destination.suffix == ".md":
                body = contents.get(destination)
                if body is None:
                    body = destination.read_text(encoding="utf-8")
                if unquote(fragment) not in anchors(body):
                    reason = "missing anchor"
            if reason:
                errors.append(
                    {"file": path.relative_to(ROOT).as_posix(), "target": target, "reason": reason}
                )
    return {
        "status": "FAIL" if errors else "PASS",
        "markdown_files": len(files),
        "local_inline_links_checked": checked,
        "errors": errors,
        "limits": "Inline Markdown targets and GitHub-style heading anchors only; not external URL, reference-style links, rendered UI or semantic source verification",
    }


if __name__ == "__main__":
    result = validate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(bool(result["errors"]))
