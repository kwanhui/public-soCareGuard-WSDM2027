"""ExpGuard (Choi et al., ICLR 2026) as the screening-side substrate baseline.

Checkpoint ``6rightjade/expguard-1.5b`` (Qwen2.5-1.5B fine-tune, Apache-2.0). It classifies a
user prompt and an assistant response as safe or unsafe against a harm taxonomy specialised for
finance, healthcare and law. It has no professional-conduct categories; it is run here to show
what a domain-specialised harm classifier says about the same drafts.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache

MODEL_ID = os.environ.get("SOCAREGUARD_EXPGUARD", "6rightjade/expguard-1.5b")


@lru_cache(maxsize=1)
def _load():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, torch_dtype=torch.float32)
    model.eval()
    return tok, model


def assess(prompt: str, response: str, max_new_tokens: int = 64) -> dict[str, str]:
    """Return {'user': 'safe'|'unsafe'|'?', 'agent': 'safe'|'unsafe'|'?', 'raw': text}."""
    import torch

    tok, model = _load()
    messages = [{"role": "user", "content": prompt}, {"role": "assistant", "content": response}]
    ids = tok.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt")
    with torch.no_grad():
        out = model.generate(ids, max_new_tokens=max_new_tokens, do_sample=False)
    text = tok.decode(out[0][ids.shape[-1] :], skip_special_tokens=True)
    user = re.search(r"User Safety Assessment:\s*(\w+)", text, re.IGNORECASE)
    agent = re.search(r"Agent Safety Assessment:\s*(\w+)", text, re.IGNORECASE)
    return {
        "user": (user.group(1).lower() if user else "?"),
        "agent": (agent.group(1).lower() if agent else "?"),
        "raw": text.strip()[:300],
    }


def unsafe(prompt: str, response: str) -> bool:
    a = assess(prompt, response)
    return a["agent"] == "unsafe" or (a["agent"] == "?" and "unsafe" in a["raw"].lower())
