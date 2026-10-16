#!/usr/bin/env python3
"""Scan prose for mechanical tell-tale patterns and exit non-zero on a hit.

Used on the README files, the panel and the policy packs of SoCareGuard, and by
the interface tests (tests/test_terminology.py and the review-round tests).

Takes files or directories. Markdown, LaTeX, HTML, Python and CFF sources are
read as prose: a `.py` file contributes its comments and docstrings, a `.tex`
file drops commands, comments and maths, and an `.html` file keeps its text
nodes and its title, placeholder, aria-label and alt attributes (Jinja tags,
scripts and styles are dropped). A `.js` file contributes its string literals,
template literals included, with any HTML tags inside them removed. A `.yaml`
file contributes the values of its prose keys (see YAML_PROSE_KEYS), never its
patterns. `scripts/check_prose_allow.txt` suppresses a justified hit with one
`path:pattern:substring` line, optionally followed by `# reason`.

A semicolon that joins two clauses is reported as a warning (`semicolon-splice`),
which is printed but does not change the exit status unless `--strict` is given.
The test is a heuristic: each side of the semicolon, up to the sentence boundary
or the next semicolon, is longer than 25 characters, carries a verb-like word, and
is not a list item (a bullet line, a table row, or a side opening with an
enumerator such as "(a)" or with "and"/"or"). Block quotes, which hold verbatim
notes and model replies, are skipped. Wrapped lines are joined first.

With no paths, the default set is scanned: the Markdown files, the panel
templates and scripts, and the policy packs.

Run:
    python3 scripts/check_prose.py              # the default set
    python3 scripts/check_prose.py README.md docs/
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

SUFFIXES = {".md", ".tex", ".html", ".py", ".cff", ".js", ".yaml", ".yml"}
ALLOW_FILE = Path(__file__).with_name("check_prose_allow.txt")
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGETS = [
    "README.md", "CHANGELOG.md", "demo/README.md", "demo/scenarios.md",
    "corpus/README.md", "docs/metrics.md", "policy-packs/README.md",
    "src/socareguard/proxy/templates", "src/socareguard/proxy/static",
    "policy-packs",
]
# keys whose values a reader sees as prose; `pattern` and `withhold_as` are not
YAML_PROSE_KEYS = {"description", "rationale", "note", "label", "status", "name", "clause"}

BANNED_WORDS = [
    "leverage", "leverages", "leveraging", "utilize", "utilise", "utilizes",
    "utilises", "delve", "delves", "holistic", "multifaceted", "seamless",
    "cutting-edge", "paradigm", "foster", "fosters", "facilitate",
    "facilitates", "robust and comprehensive",
]
HEDGES = ["it is worth noting", "notably,", "interestingly,", "it is important to"]
OPENERS = ["furthermore,", "moreover,", "additionally,"]
SHOUTED = ["NOT", "ONLY", "NEVER", "ALWAYS", "MUST"]

CODE_SPAN = re.compile(r"`[^`]*`|```.*?```", re.DOTALL)
SENTENCE_START = re.compile(r"(?:^|(?<=[.!?])\s+)([A-Z][\w'-]*)")
FENCE = re.compile(r"^\s*(```|~~~)")


def _strip_code(text: str) -> str:
    return CODE_SPAN.sub(lambda m: " " * len(m.group(0)), text)


def prose_lines(path: Path) -> list[tuple[int, str]]:
    """The prose of one file, as (line number, text) pairs."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".py":
        return _python_prose(raw)
    if path.suffix == ".js":
        return _separate(_js_strings(raw))
    if path.suffix in (".yaml", ".yml"):
        return _separate(_yaml_prose(raw))
    if path.suffix == ".html":
        return _html_prose(raw)
    out: list[tuple[int, str]] = []
    fenced = False
    for n, line in enumerate(raw.splitlines(), 1):
        if path.suffix in (".md", ".cff") and FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        if path.suffix == ".tex":
            line = re.sub(r"(?<!\\)%.*", "", line)
            line = re.sub(r"\$[^$]*\$", " ", line)
            line = re.sub(r"\\[A-Za-z@]+\*?(\[[^]]*])?(\{[^{}]*})?", " ", line)
        elif path.suffix == ".html":
            line = re.sub(r"<[^>]*>", " ", line)
        out.append((n, line))
    return out


def _separate(pieces: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Merge pieces that start on the same line, and put a blank line between
    lines so that unrelated strings are not joined into one paragraph."""
    merged: dict[int, list[str]] = {}
    for n, text in pieces:
        text = " ".join(text.split())
        if text:
            merged.setdefault(n, []).append(text)
    out: list[tuple[int, str]] = []
    for n in sorted(merged):
        out += [(n, " | ".join(merged[n])), (n, "")]
    return out


def _strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]*>", " ", text)
    return re.sub(r"&[a-z]+;|&#\d+;", " ", text)


def _html_prose(raw: str) -> list[tuple[int, str]]:
    # blank out scripts, styles and Jinja tags, keeping the line count
    def blank(m: re.Match) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))
    raw = re.sub(r"<(script|style)\b.*?</\1>", blank, raw, flags=re.DOTALL | re.IGNORECASE)
    raw = re.sub(r"\{%.*?%\}|\{\{.*?\}\}", blank, raw, flags=re.DOTALL)
    out: list[tuple[int, str]] = []
    for n, line in enumerate(raw.splitlines(), 1):
        attrs = re.findall(r'\b(?:title|placeholder|aria-label|alt)="([^"]*)"', line)
        out.append((n, " | ".join([_strip_tags(line)] + attrs)))
    return out


def _js_strings(raw: str) -> list[tuple[int, str]]:
    """String and template literals of a script, with the line each starts on.

    Comments and regular-expression literals are skipped. A `${...}` inside a
    template literal is read as code, so the strings inside it are found too.
    """
    out: list[tuple[int, str]] = []
    n = len(raw)
    prev = ""  # last significant character outside strings and comments
    regex_prev = set("(,=:[!&|?{};+-*%<>~^") | {""}

    def read_template(i: int, line: int) -> tuple[int, int]:
        start, buf = line, []
        while i < n:
            c = raw[i]
            if c == "\\":
                buf.append(raw[i:i + 2]); i += 2; continue
            if c == "`":
                out.append((start, _strip_tags("".join(buf))))
                return i + 1, line
            if c == "$" and raw[i + 1:i + 2] == "{":
                out.append((start, _strip_tags("".join(buf))))
                buf, i = [], i + 2
                i, line = read_code(i, line, stop="}")
                start = line
                continue
            if c == "\n":
                line += 1
            buf.append(c); i += 1
        return i, line

    def read_code(i: int, line: int, stop: str | None = None) -> tuple[int, int]:
        nonlocal prev
        depth = 0
        while i < n:
            c = raw[i]
            if c == "\n":
                line += 1; i += 1; continue
            if c.isspace():
                i += 1; continue
            if raw.startswith("//", i):
                j = raw.find("\n", i)
                i = n if j < 0 else j
                continue
            if raw.startswith("/*", i):
                j = raw.find("*/", i + 2)
                j = n if j < 0 else j + 2
                line += raw.count("\n", i, j); i = j
                continue
            if c in "'\"":
                j, buf = i + 1, []
                while j < n and raw[j] != c and raw[j] != "\n":
                    if raw[j] == "\\":
                        buf.append(raw[j + 1:j + 2]); j += 2; continue
                    buf.append(raw[j]); j += 1
                out.append((line, _strip_tags("".join(buf))))
                i, prev = j + 1, c
                continue
            if c == "`":
                i, line = read_template(i + 1, line)
                prev = "`"
                continue
            if c == "/" and prev in regex_prev:
                j, in_class = i + 1, False
                while j < n and raw[j] != "\n":
                    if raw[j] == "\\":
                        j += 2; continue
                    if raw[j] == "[":
                        in_class = True
                    elif raw[j] == "]":
                        in_class = False
                    elif raw[j] == "/" and not in_class:
                        break
                    j += 1
                i, prev = j + 1, "/re"
                continue
            if stop and c == "{":
                depth += 1
            elif stop and c == "}":
                if depth == 0:
                    prev = "}"
                    return i + 1, line
                depth -= 1
            prev = c if not (c.isalnum() or c in "_$") else "a"
            i += 1
        return i, line

    read_code(0, 1)
    return out


def _yaml_prose(raw: str) -> list[tuple[int, str]]:
    import yaml

    out: list[tuple[int, str]] = []

    def walk(node) -> None:
        if isinstance(node, yaml.MappingNode):
            for key, value in node.value:
                if (isinstance(value, yaml.ScalarNode)
                        and str(key.value) in YAML_PROSE_KEYS):
                    out.append((value.start_mark.line + 1, str(value.value)))
                else:
                    walk(value)
        elif isinstance(node, yaml.SequenceNode):
            for item in node.value:
                if isinstance(item, yaml.ScalarNode) and item.style is None:
                    continue  # bare list items are identifiers or anchors
                walk(item)

    for doc in yaml.compose_all(raw):
        walk(doc)
    return out


def _python_prose(raw: str) -> list[tuple[int, str]]:
    out = [(n, line[line.index("#"):]) for n, line in enumerate(raw.splitlines(), 1)
           if "#" in line and line.lstrip().startswith("#")]
    try:
        tree = ast.parse(raw)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef
                          | ast.AsyncFunctionDef):
            continue
        doc = ast.get_docstring(node, clean=False)
        if not doc:
            continue
        first = node.body[0]
        start = getattr(first, "lineno", 1)
        out += [(start + i, line) for i, line in enumerate(doc.splitlines())]
    return sorted(out)


def line_hits(text: str) -> list[tuple[str, str]]:
    """Every (pattern, evidence) pair on one line of prose."""
    bare = _strip_code(text)
    low = bare.lower()
    hits: list[tuple[str, str]] = []
    for m in re.finditer(r"(?<=[A-Za-z,])\s?[\u2013\u2014]\s?(?=[A-Za-z])", bare):
        hits.append(("dash-as-punctuation", m.group(0).strip()))
    for word in BANNED_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", low):
            hits.append(("banned-word", word))
    for hedge in HEDGES:
        if hedge in low:
            hits.append(("filler-hedge", hedge))
    for opener in OPENERS:
        if low.lstrip().startswith(opener):
            hits.append(("hollow-transition", opener))
    if re.search(r"\bnot only\b.{0,120}?\bbut\b", low):
        hits.append(("not-only-but", "not only ... but"))
    for word in SHOUTED:
        if re.search(rf"(?<![A-Za-z_]){word}(?![A-Za-z_])", bare):
            hits.append(("capitalised-emphasis", word))
    return hits


def sentence_starts(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """The first word of each sentence, with the line the sentence begins on.

    Wrapped lines are joined into one paragraph first, so that a line break
    inside a sentence is not read as a new sentence.
    """
    out: list[tuple[int, str]] = []
    para: list[tuple[int, str]] = []
    for n, text in lines + [(0, "")]:
        stripped = text.strip()
        prose = not stripped.startswith(("|", "#", "    ", "\t"))
        if stripped and prose:
            para.append((n, _strip_code(text).strip()))
            continue
        if para:
            joined = " ".join(t for _, t in para)
            offsets, cursor = [], 0
            for n_line, t in para:
                offsets.append((cursor, n_line))
                cursor += len(t) + 1
            for m in SENTENCE_START.finditer(joined):
                line = next(ln for off, ln in reversed(offsets) if off <= m.start())
                out.append((line, m.group(1).lower()))
        para = []
    return out


ARTICLES = {"the", "a", "an"}

SPLICE_MIN = 25
VERBISH = re.compile(
    r"\b(?:is|are|was|were|be|been|being|has|have|had|do|does|did|can|could|may|"
    r"might|must|shall|should|will|would|\w{2,}ed|\w{2,}s)\b", re.IGNORECASE)
ENUMERATOR = re.compile(r"^(?:\(?(?:[a-z]|[ivx]+|\d+)\)|(?:and|or)\b)", re.IGNORECASE)
LIST_LINE = re.compile(r"^([-*+]|\d+\.)\s+")


def _paragraphs(lines: list[tuple[int, str]]):
    """Runs of wrapped prose lines, each as (joined text, [(offset, line number)]).
    Bullet lines, table rows, headings, indented code and block quotes (verbatim
    notes and model replies) are left out."""
    para: list[tuple[int, str]] = []
    for n, text in lines + [(0, "")]:
        stripped = text.strip()
        prose = (stripped and not stripped.startswith(("|", "#", ">", "    ", "\t"))
                 and not text.startswith(("    ", "\t")) and not LIST_LINE.match(stripped))
        if prose:
            para.append((n, _strip_code(text).strip()))
            continue
        if para:
            offsets, cursor, parts = [], 0, []
            for n_line, t in para:
                offsets.append((cursor, n_line))
                parts.append(t)
                cursor += len(t) + 1
            yield " ".join(parts), offsets
        para = []


def splice_hits(lines: list[tuple[int, str]]) -> list[tuple[int, str, str]]:
    """Semicolons that join two clauses (see the module docstring)."""
    out: list[tuple[int, str, str]] = []
    for joined, offsets in _paragraphs(lines):
        for m in re.finditer(";", joined):
            i = m.start()
            left = re.split(r"(?<=[.!?:])\s+|;|\s\|\s", joined[:i])[-1].strip()
            right = re.split(r"(?<=[.!?])\s+|;|\s\|\s", joined[i + 1:])[0].strip()
            if len(left) <= SPLICE_MIN or len(right) <= SPLICE_MIN:
                continue
            if ENUMERATOR.match(left) or ENUMERATOR.match(right):
                continue
            if not (VERBISH.search(left) and VERBISH.search(right)):
                continue
            line = next(ln for off, ln in reversed(offsets) if off <= i)
            out.append((line, "semicolon-splice", f"{left[-30:]}; {right[:30]}"))
    return out


def block_hits(lines: list[tuple[int, str]]) -> list[tuple[int, str, str]]:
    """Hits that need more than one line: repeated openers and bolded bullets."""
    out: list[tuple[int, str, str]] = []
    starts = sentence_starts(lines)
    for i in range(len(starts) - 2):
        words = {starts[i + j][1] for j in range(3)}
        if len(words) != 1 or starts[i + 2][0] - starts[i][0] > 12:
            continue
        # An article opens so many English sentences that three in a row is
        # ordinary; four in a row is reported.
        if starts[i][1] in ARTICLES:
            fourth = starts[i + 3][1] if i + 3 < len(starts) else None
            if fourth != starts[i][1]:
                continue
        out.append((starts[i][0], "three-same-openers", starts[i][1]))
    run: list[int] = []
    for n, text in lines + [(0, "")]:
        stripped = text.strip()
        item = re.match(r"^([-*+]|\d+\.)\s+(.*)", stripped)
        if item and re.match(r"^\*\*[^*]+\*\*", item.group(2)):
            run.append(n)
            continue
        if item or not stripped:
            if len(run) >= 3:
                out.append((run[0], "bolded-bullet-list", f"{len(run)} items"))
            run = []
    return out


def load_allow(path: Path = ALLOW_FILE) -> list[tuple[str, str, str]]:
    rules = []
    if not path.exists():
        return rules
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split(":", 2)
        if len(parts) == 3:
            rules.append((parts[0], parts[1], parts[2]))
    return rules


def allowed(rules: list[tuple[str, str, str]], path: Path, pattern: str,
            evidence: str, text: str) -> bool:
    name = path.as_posix()
    return any(
        (rule_path in name)
        and (rule_pattern in ("*", pattern))
        and (sub in text or sub == evidence)
        for rule_path, rule_pattern, sub in rules
    )


WARNINGS = {"semicolon-splice"}


def scan(path: Path, rules: list[tuple[str, str, str]]) -> list[str]:
    """Hits as report lines. A warning's line starts with `warning: `."""
    lines = prose_lines(path)
    by_line: dict[int, str] = {}
    for n, text in lines:  # a blank separator line must not hide the text before it
        if text.strip() or n not in by_line:
            by_line[n] = text
    found: list[tuple[int, str, str]] = []
    for n, text in lines:
        found += [(n, pattern, evidence) for pattern, evidence in line_hits(text)]
    found += block_hits(lines)
    found += splice_hits(lines)
    seen: set[tuple[int, str]] = set()
    out = []
    for n, pattern, evidence in sorted(found):
        if (n, pattern) in seen:
            continue
        seen.add((n, pattern))
        if allowed(rules, path, pattern, evidence, by_line.get(n, "")):
            continue
        text = by_line.get(n, "").strip()[:100]
        if pattern in WARNINGS:
            out.append(f"warning: {path}:{n}: {pattern}: {evidence}")
        else:
            out.append(f"{path}:{n}: {pattern}: {text}")
    return out


def walk(targets: list[str]) -> list[Path]:
    out: list[Path] = []
    for target in targets:
        path = Path(target)
        if path.is_dir():
            out += [p for p in sorted(path.rglob("*")) if p.suffix in SUFFIXES]
        elif path.suffix in SUFFIXES:
            out.append(path)
    seen: set[Path] = set()
    return [p for p in out if not (p.resolve() in seen or seen.add(p.resolve()))]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*",
                        help="files or directories (default: the public-bound set)")
    parser.add_argument("--allow", type=Path, default=ALLOW_FILE)
    parser.add_argument("--strict", action="store_true",
                        help="count warnings (semicolon splices) towards the exit status")
    args = parser.parse_args(argv)
    rules = load_allow(args.allow)
    targets = args.paths
    if not targets:
        targets = [
            str((ROOT / t).relative_to(Path.cwd()) if (ROOT / t).is_relative_to(Path.cwd())
                else ROOT / t)
            for t in DEFAULT_TARGETS
        ]
    files = walk(targets)
    reports = [line for path in files for line in scan(path, rules)]
    for line in reports:
        print(line)
    warnings = [line for line in reports if line.startswith("warning: ")]
    hits = len(reports) - len(warnings)
    print(f"{len(files)} files scanned, {hits} hits, {len(warnings)} warnings", file=sys.stderr)
    return 1 if hits or (args.strict and warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
