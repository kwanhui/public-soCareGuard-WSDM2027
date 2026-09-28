"""Synthetic case-note corpus with exact gold spans.

Two generation layers plus a conduct-draft layer:

1. ``generate``: an LLM writes practitioner case notes with typed placeholders
   (``{{CLIENT_NAME}}``, ``{{NRIC}}``, ``{{ATTR:dv_disclosure=...}}``).
2. ``inject``: placeholders are replaced deterministically by Singapore-format
   surrogates, and the exact character offsets become gold spans.
3. ``drafts``: for each note, a compliant model draft and a draft instructed to
   exhibit one labelled professional-conduct failure.
"""
