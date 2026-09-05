# Policy packs (v0, draft)

One YAML file per practice setting. A pack declares which sensitive attributes and
quasi-identifiers are generalised on the way out, what must never leave the premises,
which inbound conduct categories apply and with what default action, and the override
policy. The conduct categories reference `socareguard/taxonomy.py`, which adapts the
structure of Iftikhar et al. (AIES 2025) and re-anchors it on the SASW Code of
Professional Ethics, 3rd Revision (2017).

**Status: draft schema assembled by a computing researcher from published documents.** It
has no standing as a social-work ethics taxonomy until reviewed by the social-work
co-investigators. Items marked `grounded: false` could not be traced to a clause and are
flagged for that review rather than dropped.

v0 (this commit) is declarative only: the outbound generalisation rules and the inbound
actions become executable in build steps 2 and 3.
