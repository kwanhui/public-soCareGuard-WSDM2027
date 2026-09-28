"""Inbound conduct screen: the model's draft is read against the profession's own code.

Runs on the pseudonymised reply, before local re-identification, so the judge provider never
sees an original identifier either. Three sources of flags: deterministic rules (over-caution
boilerplate, invented identifiers), a clause-grounded LLM judge prompted with the policy pack's
SASW clause table, and a generic harm classifier kept only as the contrast baseline.
"""
