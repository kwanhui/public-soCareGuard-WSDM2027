"""Layer 1: LLM-written case notes with typed placeholders."""

from __future__ import annotations

import hashlib
import json
import random
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from socareguard.corpus import prompts
from socareguard.corpus.names import pick_origin
from socareguard.corpus.schema import (
    ATTRIBUTE_KEYS,
    CODE_SWITCH_LANGS,
    PLACEHOLDER_CATEGORIES,
    Brief,
    GenerationMeta,
    Template,
)

PLACEHOLDER_RE = re.compile(r"\{\{([A-Z_]+)(?::([^{}]*))?\}\}")
# Placeholder keys that the model sometimes writes as field labels ("CASE_REF: ..."). Keys that
# are ordinary words (NRIC, AGE, SCHOOL, ESTATE, PHONE, ADDRESS, DOB) are not checked.
AGE_LITERAL_RE = re.compile(
    r"\b(\d{1,2}[- ]year[- ]old|\d{1,2}\s?yo\b|aged?\s*:?\s*\d{1,2}\b|\bis\s+\d{1,2}\s*\()",
    re.IGNORECASE,
)
BARE_KEY_RE = re.compile(
    r"\b(CLIENT_NAME|CLIENT_FIRST|CLIENT_TITLE|TP_NAME|TP_FIRST|CASE_REF|ATTR|CS)\b"
)

AGE_RANGES = {"disability": (18, 62), "domestic-violence": (21, 58), "youth-offending": (12, 18)}
GENDER_WEIGHTS = {
    "disability": {"female": 0.5, "male": 0.5},
    "domestic-violence": {"female": 0.85, "male": 0.15},
    "youth-offending": {"female": 0.3, "male": 0.7},
}
PACK_INDEX = {"disability": 1, "domestic-violence": 2, "youth-offending": 3}
BASE_PLACEHOLDERS = ["CLIENT_NAME", "CLIENT_FIRST", "NRIC", "AGE", "ESTATE"]
OPTIONAL_PLACEHOLDERS = {
    "disability": [
        "DOB",
        "ADDRESS",
        "PHONE",
        "CASE_REF",
        "FACILITY:day activity centre",
        "FACILITY:hospital",
        "TP_NAME:mother",
        "TP_NAME:sister",
        "TP_NAME:brother",
        "EMPLOYER",
        "CLIENT_TITLE",
    ],
    "domestic-violence": [
        "DOB",
        "ADDRESS",
        "PHONE",
        "CASE_REF",
        "FACILITY:shelter",
        "FACILITY:polyclinic",
        "TP_NAME:husband",
        "TP_FIRST:husband",
        "SCHOOL",
        "EMPLOYER",
        "TP_NAME:mother",
        "CLIENT_TITLE",
    ],
    "youth-offending": [
        "DOB",
        "ADDRESS",
        "PHONE",
        "CASE_REF",
        "SCHOOL",
        "TP_NAME:mother",
        "TP_NAME:father",
        "TP_FIRST:mother",
        "TP_NAME:teacher",
        "FACILITY:rehabilitation centre",
        "TP_NAME:friend",
    ],
}


def git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return None


def make_brief(rng: random.Random, pack: str, cfg: dict[str, Any], idx: int) -> Brief:
    lo, hi = AGE_RANGES[pack]
    age = rng.randint(lo, hi)
    gw = GENDER_WEIGHTS[pack]
    gender = rng.choices(list(gw), weights=list(gw.values()), k=1)[0]
    origin = pick_origin(rng, cfg["name_origins"])
    ref = date.fromisoformat(str(cfg["reference_date"]))
    note_date = ref - timedelta(days=rng.randint(0, 120))
    optional = rng.sample(OPTIONAL_PLACEHOLDERS[pack], k=rng.randint(3, 5))
    if pack == "youth-offending" and "SCHOOL" not in optional:
        optional.append("SCHOOL")
    if pack == "youth-offending" and "CASE_REF" not in optional:
        optional.append("CASE_REF")
    required = BASE_PLACEHOLDERS + optional
    attrs = list(prompts.PACK_ATTRIBUTES[pack])
    if pack == "domestic-violence":
        attrs = ["dv_disclosure"] + rng.sample(["ppo", "safety_plan"], k=rng.randint(1, 2))
    if pack == "disability":
        attrs = ["disability"] + rng.sample(["diagnosis", "capacity"], k=rng.randint(1, 2))
    cs_lang = None
    if rng.random() < cfg["code_switch_share"]:
        langs = cfg["code_switch_langs"]
        cs_lang = rng.choices(list(langs), weights=list(langs.values()), k=1)[0]
        # Keep the language plausible for the family, with Singlish as the common fallback.
        if cs_lang == "malay" and origin != "malay":
            cs_lang = "singlish"
        if cs_lang == "tamil" and origin != "indian":
            cs_lang = "singlish"
        if cs_lang == "mandarin" and origin != "chinese":
            cs_lang = "singlish"
    return Brief(
        pack=pack,
        note_type=rng.choice(prompts.NOTE_TYPES[pack]),
        practitioner_role=rng.choice(prompts.PRACTITIONER_ROLES[pack]),
        client_gender=gender,
        client_age=age,
        client_origin=origin,
        presenting_concern=rng.choice(prompts.PRESENTING_CONCERNS[pack]),
        required_placeholders=required,
        attributes=attrs,
        code_switch_lang=cs_lang,
        note_date=note_date.isoformat(),
    )


def validate_template(
    text: str, brief: Brief, min_words: int = 120, max_words: int = 420
) -> list[str]:
    """Return a list of problems; empty means the template is usable."""
    errors: list[str] = []
    found = PLACEHOLDER_RE.findall(text)
    keys = {k for k, _ in found}
    for k, arg in found:
        if k not in PLACEHOLDER_CATEGORIES and k != "CS":
            errors.append(f"unknown placeholder {k}")
        if k == "ATTR":
            if "=" not in (arg or ""):
                errors.append("ATTR without key=text")
            elif arg.split("=", 1)[0] not in ATTRIBUTE_KEYS:
                errors.append(f"unknown ATTR key {arg.split('=', 1)[0]}")
        if k == "CS" and ("=" not in (arg or "") or arg.split("=", 1)[0] not in CODE_SWITCH_LANGS):
            errors.append("CS without a known lang")
        if k in {"TP_NAME", "TP_FIRST", "FACILITY"} and not arg:
            errors.append(f"{k} without a role/kind argument")
    for req in brief.required_placeholders:
        rk = req.split(":", 1)[0]
        if rk not in keys:
            errors.append(f"missing required placeholder {req}")
    attr_keys = {a.split("=", 1)[0] for k, a in found if k == "ATTR" and a}
    for a in brief.attributes:
        if a not in attr_keys:
            errors.append(f"missing ATTR:{a}")
    if brief.code_switch_lang and "CS" not in keys:
        errors.append("missing CS fragment")
    for k, arg in found:
        if k in {"ATTR", "CS"} and not (arg or "").partition("=")[2].strip():
            errors.append(f"{k} with empty text")
    if "AGE" in keys and AGE_LITERAL_RE.search(PLACEHOLDER_RE.sub(" ", text)):
        errors.append("age written as a plain number alongside {{AGE}}")
    bare = set(BARE_KEY_RE.findall(PLACEHOLDER_RE.sub(" ", text)))
    if bare:
        errors.append(f"placeholder key written as plain text: {sorted(bare)}")
    stray = re.findall(r"\{\{|\}\}", PLACEHOLDER_RE.sub("", text))
    if stray:
        errors.append("stray braces outside a valid placeholder")
    words = len(PLACEHOLDER_RE.sub("X", text).split())
    if words < min_words or words > max_words:
        errors.append(f"length {words} words outside {min_words}-{max_words}")
    return errors


def prompt_hash(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n\n" + user).encode()).hexdigest()[:16]


def _call_openai(
    model: str,
    system: str,
    user: str,
    temperature: float,
    seed: int,
    history: list[dict[str, str]] | None = None,
) -> str:
    from openai import OpenAI

    client = OpenAI()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}] + (
        history or []
    )
    kwargs: dict[str, Any] = {"model": model, "messages": messages, "seed": seed}
    if not model.startswith("gpt-5"):
        kwargs["temperature"] = temperature
    resp = client.chat.completions.create(**kwargs)
    return (resp.choices[0].message.content or "").strip()


def generate_one(pack: str, idx: int, cfg: dict[str, Any], max_attempts: int = 4) -> Template:
    seed = int(cfg["seed"]) * 1000 + PACK_INDEX[pack] * 100_000 + idx
    rng = random.Random(seed)
    brief = make_brief(rng, pack, cfg, idx)
    system = prompts.SYSTEM_PROMPT
    user = prompts.user_prompt(brief, rng)
    gen = cfg["generation"]
    text, errors = "", ["not generated"]
    history: list[dict[str, str]] = []
    for attempt in range(max_attempts):
        text = _call_openai(
            gen["model"], system, user, float(gen["temperature"]), seed + attempt, history
        )
        errors = validate_template(text, brief)
        if not errors:
            break
        # Repair turn: show the model its own note and ask for a corrected full version.
        history = [
            {"role": "assistant", "content": text},
            {
                "role": "user",
                "content": (
                    "That note has these problems: " + "; ".join(errors) + ". "
                    "Rewrite the complete note fixing every problem and keep everything else. "
                    "Every required placeholder must appear exactly as spelled; every ATTR needs =text; "
                    "no placeholder may appear inside another; output the note text only."
                ),
            },
        ]
    return Template(
        id=f"{pack}-{idx:03d}",
        pack=pack,
        seed=seed,
        brief=brief,
        template_text=text,
        generation=GenerationMeta(
            provider=gen["provider"],
            model=gen["model"],
            prompt_hash=prompt_hash(system, user),
            temperature=float(gen["temperature"]),
            created_at=datetime.now(UTC),
            git_commit=git_commit(),
        ),
        validation_errors=errors,
    )


def generate_pack(pack: str, cfg: dict[str, Any], out_dir: Path, limit: int | None = None) -> Path:
    n = int(cfg["packs"][pack]["n_notes"])
    if limit:
        n = min(n, limit)
    out = out_dir / f"{pack}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done: dict[str, Template] = {}
    if out.exists():
        for line in out.read_text().splitlines():
            if line.strip():
                t = Template.model_validate_json(line)
                if not t.validation_errors:
                    done[t.id] = t
    todo = [i for i in range(n) if f"{pack}-{i:03d}" not in done]
    workers = int(cfg["generation"].get("workers", 4))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(generate_one, pack, i, cfg): i for i in todo}
        for fut in as_completed(futs):
            t = fut.result()
            done[t.id] = t
            print(
                f"{t.id}: {'ok' if not t.validation_errors else 'INVALID ' + '; '.join(t.validation_errors)}"
            )
    with out.open("w") as f:
        for tid in sorted(done):
            f.write(done[tid].model_dump_json() + "\n")
    return out


def load_templates(path: Path) -> list[Template]:
    return [Template.model_validate_json(l) for l in path.read_text().splitlines() if l.strip()]


def placeholders_in(text: str) -> list[tuple[str, str | None]]:
    return [(k, a or None) for k, a in PLACEHOLDER_RE.findall(text)]


def dump_jsonl(items: list[Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for it in items:
            f.write(json.dumps(it.model_dump(mode="json"), ensure_ascii=False) + "\n")
