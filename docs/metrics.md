# Metrics

Generated 2026-09-28 at commit `98ccb46` by `python3 -m socareguard.eval report` from the JSON files in this folder.
Corpus: `corpus-v1.2` (300 synthetic notes, 4,874 gold spans, namely 4,173 entity spans scored by the detection tables and 701 attribute spans scored as attribute recall, and the screen runs on the 600 labelled drafts of v1.1 and the 90 compliant external drafts that v1.2 adds). Every number below is measured on synthetic material; see `corpus/README.md`.

PDPC's Advisory Guidelines on Use of Personal Data in Generative AI (section 8.3) ask a System Provider to document the rate at which
personal identifiers are detected and redacted before a request leaves the premises. These tables report that rate on synthetic notes.

## Outbound detection (full pipeline)

Detectors: sg, gazetteer, presidio, fastino/gliner2-privacy-filter-PII-multi. Latency per note p50 0.93 s, p95 1.07 s (CPU).

| Category | Exact P | Exact R | Exact F1 | Relaxed P | Relaxed R | Relaxed F1 | Gold |
|---|---|---|---|---|---|---|---|
| ADDRESS | 0.974 | 0.974 | 0.974 | 1.000 | 1.000 | 1.000 | 114 |
| AGE | 0.968 | 0.890 | 0.927 | 0.968 | 0.890 | 0.927 | 301 |
| ALL | 0.942 | 0.961 | 0.951 | 0.959 | 0.976 | 0.968 | 4173 |
| CASE_REF | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 214 |
| DOB | 0.990 | 1.000 | 0.995 | 0.990 | 1.000 | 0.995 | 101 |
| EMPLOYER | 0.383 | 0.590 | 0.465 | 0.519 | 0.800 | 0.630 | 100 |
| ESTATE | 0.911 | 0.926 | 0.918 | 0.911 | 0.926 | 0.918 | 309 |
| FACILITY | 0.882 | 0.946 | 0.913 | 0.886 | 0.949 | 0.916 | 294 |
| NAME | 0.948 | 0.969 | 0.958 | 0.982 | 0.996 | 0.989 | 1409 |
| NRIC | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 302 |
| PHONE | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 137 |
| SCHOOL | 0.995 | 0.995 | 0.995 | 1.000 | 1.000 | 1.000 | 199 |
| THIRD_PARTY_NAME | 1.000 | 0.996 | 0.998 | 1.000 | 0.996 | 0.998 | 693 |

**Leakage rate, matched** (gold DIRECT spans with no overlapping detection of the same category): 9 of 2970 = 0.30%.
Per pack: disability 0.6%, domestic-violence 0.4%, youth-offending 0.0%.

**Leakage rate, covered** (gold DIRECT spans that no direct-identifier detection overlaps): 3 of 2970 = 0.10%.

**Recall by name origin** (relaxed, NAME and THIRD_PARTY_NAME): chinese 99.3% (n=428), eurasian 99.5% (n=385), indian 100.0% (n=456), malay 99.5% (n=413), western 99.5% (n=420).

**Attribute recall** (a gold ATTRIBUTE span counts as found when any attribute detection overlaps it): capacity 98.7% (n=78), diagnosis 100.0% (n=76), disability 85.0% (n=100), dv_disclosure 82.0% (n=100), minor 91.0% (n=100), offence 95.0% (n=100), ppo 100.0% (n=79), safety_plan 80.9% (n=68).

## Ablation: what each layer adds

| Configuration | Relaxed P | Relaxed R | Relaxed F1 | Leakage, matched | Leakage, covered | p50 latency |
|---|---|---|---|---|---|---|
| Singapore recognisers + gazetteers only | 0.971 | 0.552 | 0.704 | 59.5% | 59.3% | 0.002 s |
| + Presidio | 0.977 | 0.966 | 0.972 | 1.2% | 1.0% | 0.036 s |
| + GLiNER2-PII (full) | 0.959 | 0.976 | 0.968 | 0.3% | 0.1% | 0.928 s |

The deterministic layer alone catches every NRIC, phone number and case reference at near-perfect precision, whereas among names it catches only titled client names (NAME recall 0.233).
Presidio adds most names, and GLiNER2-PII reduces the remaining name and address gap at the cost of latency.

## Round trip (sanitise, then restore, no model in the loop)

| Consistency (one outbound form per original) | 99.0% |
|---|---|
| Injectivity (no two entities share an outbound form) | 99.3% |
| Surrogate fidelity (every substituted span restored verbatim, none left) | 100.0% |
| Exact text fidelity (whole note identical after restore) | 51.0% |
| Gold DIRECT strings still present in the outbound text | 0.07% (2 of 2970) |
| Gold ATTRIBUTE spans sent verbatim (not generalised) | 14.8% (104 of 701) |
| Spans substituted / generalised | 2891 / 2095 |
| Latency p50 / p95 | 1.02 s / 1.19 s |

Exact text fidelity is low by design: generalisation is one-way, so a note that carried a diagnosis or a
school name comes back with the generalised phrase unless the model reproduced it exactly. Surrogate fidelity
is the measure that matters for re-identification.

## Utility retention per provider

30 notes (10 per pack). For each provider, a case summary drafted from the raw note (never run in production) is compared
with the summary drafted through the guard and restored. Both providers judge every pair on a 1 to 5 scale, blind to condition,
so each provider's drafts are scored by itself and by the other model. Retention is the share of pairs rated 4 or 5.

| Provider | Judge | n | Mean score | Retention | Score histogram 1..5 | Per pack mean |
|---|---|---|---|---|---|---|
| openai/gpt-4.1-mini | openai/gpt-4.1-mini | 30 | 4.467 | 96.7% | 0/0/1/14/15 | disability 4.6, domestic-violence 4.3, youth-offending 4.5 |
| openai/gpt-4.1-mini | anthropic/claude-sonnet-5 | 30 | 3.433 | 53.3% | 0/4/10/15/1 | disability 3.5, domestic-violence 3.0, youth-offending 3.8 |
| anthropic/claude-sonnet-5 | openai/gpt-4.1-mini | 30 | 4.567 | 100.0% | 0/0/0/13/17 | disability 4.6, domestic-violence 4.3, youth-offending 4.8 |
| anthropic/claude-sonnet-5 | anthropic/claude-sonnet-5 | 30 | 3.267 | 50.0% | 0/7/8/15/0 | disability 3.5, domestic-violence 2.9, youth-offending 3.4 |

Leak-check pass rate on the guarded path: openai/gpt-4.1-mini 100.0%, anthropic/claude-sonnet-5 96.7%.

## Inbound conduct screen (labelled drafts)

690 drafts (300 written under a single-failure instruction, 390 compliant). Judge: `openai/gpt-4.1` at temperature 0, using the pack's SASW clause table, deterministic rules for over-caution, and disclosure categories gated on an external audience in the instruction. Labels are generation-intent labels, so these are
behaviour on scripted material, not validated accuracy. F1, AUPRC and FPR are reported together, as for safety classifiers.

| Scope | Precision | Recall | F1 | FPR | AUPRC |
|---|---|---|---|---|---|
| Any conduct flag vs compliant | 0.633 | 0.650 | 0.641 | 0.290 | 0.556 |
| I1 Emotive or derogatory documentation language | 0.455 | 0.217 | 0.294 | 0.009 | 0.152 |
| I10 Disclosure or referral without consent | 0.214 | 0.714 | 0.330 | 0.082 | 0.164 |
| I11 Consent language inappropriate to capacity | 0.545 | 0.462 | 0.500 | 0.007 | 0.276 |
| I12 Advice contrary to organisational policy or prot | 0.800 | 0.200 | 0.320 | 0.002 | 0.203 |
| I13 Re-identifying detail reintroduced by the model | 0.000 | 0.000 | 0.000 | 0.004 | 0.029 |
| I14 Identifies a protected child or young person in  | 0.122 | 1.000 | 0.218 | 0.063 | 0.107 |
| I2 Disrespectful language about the client | 0.071 | 0.174 | 0.101 | 0.078 | 0.040 |
| I3 Fabricated or unsupported content in a case note | 0.333 | 0.318 | 0.326 | 0.021 | 0.209 |
| I4 Discriminatory or culturally insensitive framing | 1.000 | 0.136 | 0.240 | 0.000 | 0.164 |
| I5 Overrides client self-determination | 0.500 | 1.000 | 0.667 | 0.033 | 0.939 |
| I6 Treats imminent risk as ordinary autonomy | 0.333 | 0.136 | 0.194 | 0.009 | 0.088 |
| I7 Boundary-violating suggestion | 1.000 | 0.818 | 0.900 | 0.000 | 0.824 |
| I8 Out-of-scope clinical or legal advice | 0.571 | 0.182 | 0.276 | 0.004 | 0.134 |
| I9 Unrealistic expectation-setting about outcomes | 0.889 | 0.364 | 0.516 | 0.002 | 0.322 |
| OVER_CAUTION Over-cautious boilerplate that displaces the pro | 1.000 | 0.750 | 0.857 | 0.000 | 0.757 |

Intended-label recall (the instructed failure is among the flags raised): 40.0%.
False-positive rate on the compliant drafts, with the audience gate and without it: internal drafts (300) 0.123 and 0.190, external drafts (90) 0.844 and 0.844.
Operating points by judge-confidence threshold (any flag vs compliant): t=0.5: P 0.63 / R 0.65 / F1 0.64 / FPR 0.29; t=0.7: P 0.63 / R 0.65 / F1 0.64 / FPR 0.29; t=0.85: P 0.67 / R 0.53 / F1 0.59 / FPR 0.20; t=0.95: P 0.65 / R 0.45 / F1 0.54 / FPR 0.18.

Judge confidence distribution on the 600 v1.1 drafts alone (600 drafts, 288 judge flags, from `screen-v1.2-rows.jsonl`): 0.6 (3), 0.7 (48), 0.8 (30), 0.85 (2), 0.9 (28), 0.95 (81), 0.98 (2), 1 (94). At or above 0.95: 177 of 288.

**Generic harm classifier on the same drafts** (openai omni-moderation-latest (any category >= 0.3)): precision 0.404, recall 0.183, F1 0.252, FPR 0.208.
Of the failure drafts, 166 were flagged by the conduct screen only, 29 by both, 26 by the harm classifier only, 79 by neither.
This is the H1 finding: professional-conduct failures are largely invisible to a harm taxonomy.

Per pack (any flag vs compliant): disability F1 0.703 / FPR 0.423, domestic-violence F1 0.631 / FPR 0.215, youth-offending F1 0.571 / FPR 0.231.

**Cross-provider check** (`anthropic/claude-sonnet-5`, 180 drafts): any-flag precision 0.789, recall 0.667, F1 0.723, FPR 0.178; intended-label recall 50.0%.
The drafts were generated by gpt-4.1-mini and the runtime judge is gpt-4.1, so this second judge from another provider guards against same-family leniency.
Per-category recall of the second judge at the 0.5 threshold: I1 0 of 8, I10 6 of 6, I11 0 of 4, I12 2 of 6, I13 3 of 6, I14 2 of 2, I2 1 of 8, I3 6 of 7, I4 2 of 7, I5 6 of 6, I6 0 of 6, I7 6 of 6, I8 0 of 6, I9 5 of 6, OVER_CAUTION 6 of 6.

## Prompt-only judge ablation

To measure what the clause table adds, the same judge (`openai/gpt-4.1` at temperature 0) was run on the same 690 drafts with a prompt that keeps the category ids and their plain names, so that its flags map onto the same labels, and removes the SASW clause text, the category definitions and guidance, and the pack's setting rules. The source note, the instruction, the output schema and the scoring are the same as for the clause-grounded screen, including the audience gate for I10 and I14 and the deterministic over-caution rule. The clause-grounded row is the reported result set (`screen-v1.2.json`).

| Judge prompt | t=0.5 P / R / F1 / FPR | t=0.85 P / R / F1 / FPR | AUPRC | Intended-label recall |
|---|---|---|---|---|
| Clause table, definitions and setting rules | 0.633 / 0.650 / 0.641 / 0.290 | 0.672 / 0.527 / 0.591 / 0.197 | 0.556 | 40.0% |
| Category names only (prompt-only) | 0.697 / 0.643 / 0.669 / 0.215 | 0.720 / 0.557 / 0.628 / 0.167 | 0.568 | 42.7% |

Per-category F1, clause-grounded against prompt-only: I1 0.29 against 0.14, I10 0.33 against 0.25, I11 0.50 against 0.35, I12 0.32 against 0.57, I13 0.00 against 0.23, I14 0.22 against 0.10, I2 0.10 against 0.00, I3 0.33 against 0.41, I4 0.24 against 0.53, I5 0.67 against 0.72, I6 0.19 against 0.15, I7 0.90 against 1.00, I8 0.28 against 0.11, I9 0.52 against 0.60, OVER_CAUTION 0.86 against 0.98.

At the 0.5 threshold, the prompt-only judge reaches F1 0.669 against 0.641 for the clause-grounded judge, with FPR 0.215 against 0.290 and AUPRC 0.568 against 0.556. At the 0.85 threshold, the FPR is 0.167 against 0.197. Both runs share the generation-intent labels described above, so the difference is between two prompts on the same scripted material, not a validated accuracy gap. Produced by `python3 -m socareguard.eval screen --prompt-only --tag v1.2-prompt-only --no-baseline --corpus v1.2`, at an estimated USD 2.08 at list prices (966 input tokens per call counted with o200k_base, 135 output tokens per call assumed).

## Cost

OpenAI list prices on 2026-09-27 (standard tier, USD per million tokens, https://developers.openai.com/api/docs/pricing): gpt-4.1-mini 0.40 input / 1.60 output; gpt-4.1 2.00 / 8.00; omni-moderation free.

| Call | Model | Input tokens | Output tokens | USD per call |
|---|---|---|---|---|
| Drafting | `openai/gpt-4.1-mini` | 169 | 197 | 0.0004 |
| Conduct judge | `openai/gpt-4.1` | 2334 (2057 to 2558) | 135 (estimated) | 0.0057 |
| Harm-classifier baseline | `openai/omni-moderation-latest` | | | 0 |
| Per draft | | | | 0.0061 |

That is approximately USD 6.13 per 1,000 drafts. A regeneration repeats the drafting and judge calls.
Drafting tokens are the means of the `usage` field over 26 live (not replayed) request rows in the ledger of the review-round dev server of 2026-09-27. The reviewers' notes were short, and the four Use Case payloads count 76 to 276 tokens.
The judge's usage is not recorded. Its input is counted by building the judge prompt for the four recorded Use Case scenarios and tokenising it with o200k_base,
and its output is estimated from the flags per request in the same ledger and the size of the judge flags in saved completion responses.
The judge prompt carries the pack's clause table, so the judge accounts for most of the cost. `docs/metrics/cost-v1.1.json` holds these figures; the cost was measured at v1.1 and has not been re-run on v1.2.

## NRIC and FIN format variants

The corpus writes every NRIC and FIN in the canonical form of the identifier factory in `corpus/identifiers.py`, which the deterministic recogniser also imports, so the NRIC row of the detection table is measured on that form only. A separate stress set of 30 synthetic variants (`tests/data/nric-variants.jsonl`) writes the number spaced, hyphenated, in lower case, after an "NRIC:" label, in parentheses, with a space on one side only and with a mistyped check letter.

Detectors: sg, gazetteer, presidio, fastino/gliner2-privacy-filter-PII-multi. Recall with an exact NRIC span: 100.0%; recall with any overlapping direct-identifier span: 100.0%; variants whose text survives in the sanitised note: 0 of 30. By form: compact 2 of 2, lower 2 of 2, spaced 2 of 2, spaced_lower 2 of 2, hyphenated 2 of 2, hyphenated_lower 2 of 2, prefix_colon 2 of 2, prefix_colon_nospace 2 of 2, parentheses 2 of 2, parentheses_spaced 2 of 2, letter_space_only 2 of 2, check_space_only 2 of 2, mixed_case 2 of 2, in_list 2 of 2, end_of_sentence 2 of 2.
Produced by `python3 -m socareguard.eval detect --variants`. Before round 4, the recogniser matched the compact form only.

## Average precision with ties processed together (v1.1 rows)

The judge returns few distinct confidence values, and the AUPRC reported in the v1.1 files walked tied drafts one at a time in file order, so its value depended on the order of the rows. The table recomputes average precision from the same per-draft rows with tied scores processed together, as `sklearn.metrics.average_precision_score` does, on the audience-gated score that the operating points use (I10 and I14 removed for an internal audience, the over-caution rule at 1.0). No model was called. From corpus v1.2, `eval screen` reports the gated tie-aware value as `auprc`, the number of distinct scores, and the file-order value under `auprc_file_order_deprecated`.

| Run | Drafts | Tie-aware, gated | Tie-aware, ungated | File order (v1.1, deprecated) | Distinct gated scores |
|---|---|---|---|---|---|
| Clause-grounded judge | 600 | 0.798 | 0.719 | 0.769 | 9 |
| Prompt-only judge | 600 | 0.727 | 0.658 | 0.701 | 9 |
| Second judge | 180 | 0.803 | 0.803 | 0.852 | 17 |

The distinct-score count includes 0.0 for a draft with no flag. `docs/metrics/auprc-tieaware-v1.1.json` holds these values with per-category average precision and per-category recall at the 0.5 threshold. Produced by `python3 -m socareguard.eval auprc --version v1.1`.

## Corpus v1.2: compliant drafts for an external reader

All 300 compliant drafts of corpus v1.1 are internal case summaries, so the audience gate for I10 and I14 was not tested against a compliant draft written for someone outside the case team. Corpus v1.2 appends 90 compliant drafts with an external audience, each from an existing v1.1 note, written by the same drafting model and prompt (disability 15 employer letters and 15 referral notes, domestic-violence 10 employer letters and 10 referral notes and 10 school letters, youth-offending 15 referral notes and 15 school letters). No v1.1 file was changed. The drafts are described in `corpus/drafts/README-v1.2.md`, and the run is recorded in `configs/corpus-v1.2.yaml`. With `python3 -m socareguard.eval screen --corpus v1.2`, the screen reports the false-positive rate on the compliant drafts with and without the gate, for internal and external drafts separately.

| Run | Internal compliant, gated | Internal compliant, ungated | External compliant, gated | External compliant, ungated | All compliant, gated / ungated |
|---|---|---|---|---|---|
| Clause-grounded judge | 0.123 (n=300) | 0.190 | 0.844 (n=90) | 0.844 | 0.290 / 0.341 |
| Prompt-only judge | 0.113 (n=300) | 0.260 | 0.556 (n=90) | 0.556 | 0.215 / 0.328 |

The gate removes I10 and I14 only when the draft is written for the case team, so on an external draft the gated and ungated rates are equal by construction, and the gate can lower the false-positive rate only on internal drafts. The external rate measures how often the judge raises a flag on a compliant letter or referral.

Clause-grounded judge: 76 of 90 compliant external drafts flagged (employer letters 19 of 25, referral notes 37 of 40, school letters 20 of 25). Flags raised: I10 42, I14 30, I2 7, I11 1, I13 1, I3 1.
Prompt-only judge: 50 of 90 compliant external drafts flagged (employer letters 12 of 25, referral notes 27 of 40, school letters 11 of 25). Flags raised: I13 22, I14 21, I10 5, I3 3, I11 2, I1 1, I8 1.

Rescored from the same rows with no model call, the numbers on the 600 drafts of v1.1 alone (`python3 -m socareguard.eval rescore --tag v1.2` and `--tag v1.2-prompt-only`, written to `screen-v1.2-v1.1-drafts.json` and `screen-v1.2-prompt-only-v1.1-drafts.json`), are the rows headed "600 v1.1 drafts" of the comparison table below and compare like for like with v1.1.

## Reading these numbers

- Gold spans are exact character offsets produced by injection, so exact-match scores are strict; relaxed (overlap) scores are the ones comparable to the de-identification literature.
- Cohen's kappa is not reported for spans; the corpus has no second annotator and span kappa is the wrong instrument (Deleger et al., 2012).
- Matched leakage counts a gold DIRECT span as missed when no detection of the same category overlaps it, one detection per gold span; it is the complement of direct-identifier recall and the measure reported for corpus v1.
- Covered leakage counts a gold DIRECT span as leaked only when no detection of any direct-identifier category overlaps it, because such a detection is substituted whatever its label; it is the detector's share of what reaches the provider unmasked. The round-trip count of gold strings in the outbound text also reflects the sanitiser's own choices.
- Dates of contact are not annotated in corpus v1 and are not scored.

## Corpus v1, v1.1 and v1.2

The v1 column is the result set of the first paper draft (code of commit `4868da4` for detection and round trip, `36a3ca9` for the screen and utility, corpus v1).
The v1.1 column is the result set tagged `results-v1.1` (commit `b0a38ac`, corpus v1.1). Its tie-aware average precision is recomputed from the saved rows. The paper reports the v1.2 column.
The v1.2 column is this document's result set (tag `results-v1.2`). The screen rows of v1.2 are on 690 drafts, the 600 of v1.1 and 90 compliant external drafts, whereas the second judge runs on the same 180-draft subset as in v1.1. A row without an earlier value is a new measure.
On the 90 external drafts the clause-grounded judge flags 76 (I10 42, I14 30, I2 7). A reading of every flag against the pack clauses found the 30 I14 flags to be the youth pack's rule that escalates any external document identifying a protected young person. Of the 42 I10 flags, 14 are drafter over-disclosure (a diagnosis named to an employer who needed only a work adjustment), 9 are false positives and 18 are undecidable because the referral instruction recorded no consent. The compliant label is therefore unreliable for external drafts. The paper reports the 600 labelled drafts in its table and states this result in its text.

| Measure | v1 | v1.1 | v1.2 |
|---|---|---|---|
| All spans, relaxed P / R / F1 | 0.949 / 0.980 / 0.964 | 0.955 / 0.969 / 0.962 | 0.959 / 0.976 / 0.968 |
| All spans, exact P / R / F1 | 0.903 / 0.942 / 0.922 | 0.933 / 0.948 / 0.940 | 0.942 / 0.961 / 0.951 |
| NRIC, phone, address, case ref., relaxed P / R / F1 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 |
| Names, relaxed P / R / F1 | 0.947 / 0.983 / 0.965 | 0.979 / 0.975 / 0.977 | 0.982 / 0.996 / 0.989 |
| Employer, relaxed recall | 0.800 | 0.800 | 0.800 |
| Leakage (matched), full pipeline | 0.94% (28 of 2970) | 1.28% (38 of 2970) | 0.30% (9 of 2970) |
| Leakage (covered), full pipeline | n/a | 0.10% (3 of 2970) | 0.10% (3 of 2970) |
| Leakage (matched), without GLiNER2-PII | 2.36% | 2.19% | 1.21% |
| Leakage (covered), without GLiNER2-PII | n/a | 1.01% | 1.01% |
| Leakage (matched), recognisers only | 70.8% | 60.0% | 59.5% |
| Leakage (covered), recognisers only | n/a | 58.7% | 59.3% |
| Name recall, recognisers only | 0.000 | 0.215 | 0.233 |
| Name recall by origin | chinese 0.977, eurasian 0.982, indian 0.996, malay 0.993, western 0.986 | chinese 0.991, eurasian 0.982, indian 0.978, malay 0.973, western 0.986 | chinese 0.993, eurasian 0.995, indian 1.000, malay 0.995, western 0.995 |
| Attribute recall by key, range | 0.81 to 1.00 | 0.81 to 1.00 | 0.81 to 1.00 |
| Latency per note, p50 | 1.37 s | 0.94 s | 0.93 s |
| Gold direct strings in outbound text | 0.07% (2 of 2970) | 0.07% (2 of 2970) | 0.07% (2 of 2970) |
| Gold attribute spans sent verbatim | 11.6% (81 of 701) | 15.7% (110 of 701) | 14.8% (104 of 701) |
| Screen drafts (failure / compliant) | 600 (300 / 300) | 600 (300 / 300) | 690 (300 / 390) |
| Screen any flag t=0.5, P / R / F1 / FPR | 0.814 / 0.713 / 0.760 / 0.163 | 0.825 / 0.660 / 0.733 / 0.140 | 0.633 / 0.650 / 0.641 / 0.290 |
| Screen any flag t=0.85, P / R / F1 / FPR | 0.961 / 0.570 / 0.716 / 0.023 | 0.964 / 0.537 / 0.690 / 0.020 | 0.672 / 0.527 / 0.591 / 0.197 |
| Screen AUPRC, file order (deprecated) | 0.815 | 0.769 | 0.617 |
| Screen average precision, tie-aware, gated | n/a | 0.798 | 0.556 |
| Screen any flag t=0.5 without the audience gate, P / R / F1 / FPR | n/a | n/a | 0.615 / 0.707 / 0.657 / 0.341 |
| FPR on internal compliant drafts, gated / ungated | n/a | n/a | 0.123 / 0.190 (n=300) |
| FPR on external compliant drafts, gated / ungated | n/a | n/a | 0.844 / 0.844 (n=90) |
| Harm classifier P / R / F1 / FPR | 0.430 / 0.183 / 0.257 / 0.243 | 0.430 / 0.183 / 0.257 / 0.243 | 0.404 / 0.183 / 0.252 / 0.208 |
| Failure drafts: screen only / classifier only / both / neither | 177 / 18 / 37 / 68 | 165 / 22 / 33 / 80 | 166 / 26 / 29 / 79 |
| I7 P / R / F1 | 1.000 / 0.909 / 0.952 | 1.000 / 0.909 / 0.952 | 1.000 / 0.818 / 0.900 |
| OVER_CAUTION P / R / F1 | 1.000 / 0.650 / 0.788 | 1.000 / 0.900 / 0.947 | 1.000 / 0.750 / 0.857 |
| I10 P / R / F1 | 0.500 / 0.667 / 0.571 | 0.536 / 0.714 / 0.612 | 0.214 / 0.714 / 0.330 |
| Per-category F1, range | 0.00 to 0.95 | 0.07 to 0.95 | 0.00 to 0.90 |
| Intended-label recall | 43.3% | 42.7% | 40.0% |
| Judge flags at confidence 0.95 or above, all drafts of the run | 180 of 309 | 189 of 296 | 248 of 370 |
| Prompt-only judge t=0.5 F1 | n/a | 0.728 | 0.669 |
| Prompt-only judge t=0.85 FPR | n/a | 0.067 | 0.167 |
| Prompt-only AUPRC, file order (deprecated) | n/a | 0.701 | 0.569 |
| Prompt-only average precision, tie-aware, gated | n/a | 0.727 | 0.568 |
| I10 F1, clause-grounded / prompt-only | n/a | 0.61 / 0.36 | 0.33 / 0.25 |
| I11 F1, clause-grounded / prompt-only | n/a | 0.60 / 0.43 | 0.50 / 0.35 |
| I14 F1, clause-grounded / prompt-only | n/a | 0.48 / 0.21 | 0.22 / 0.10 |
| 600 v1.1 drafts, Clause-grounded t=0.5 P / R / F1 / FPR | n/a | 0.825 / 0.660 / 0.733 / 0.140 | 0.841 / 0.650 / 0.733 / 0.123 |
| 600 v1.1 drafts, Clause-grounded t=0.85 P / R / F1 / FPR | n/a | 0.964 / 0.537 / 0.690 / 0.020 | 0.975 / 0.527 / 0.684 / 0.013 |
| 600 v1.1 drafts, Clause-grounded average precision, tie-aware, gated | n/a | 0.798 | 0.801 |
| 600 v1.1 drafts, Clause-grounded I1 P / R / F1 | n/a | 0.240 / 0.261 / 0.250 | 0.455 / 0.217 / 0.294 |
| 600 v1.1 drafts, Clause-grounded I10 P / R / F1 | n/a | 0.536 / 0.714 / 0.612 | 0.536 / 0.714 / 0.612 |
| 600 v1.1 drafts, Clause-grounded I11 P / R / F1 | n/a | 0.857 / 0.462 / 0.600 | 0.600 / 0.462 / 0.522 |
| 600 v1.1 drafts, Clause-grounded I14 P / R / F1 | n/a | 0.316 / 1.000 / 0.480 | 0.316 / 1.000 / 0.480 |
| 600 v1.1 drafts, Clause-grounded OVER_CAUTION P / R / F1 | n/a | 1.000 / 0.900 / 0.947 | 1.000 / 0.750 / 0.857 |
| 600 v1.1 drafts, Clause-grounded per-category F1, range | n/a | 0.07 to 0.95 | 0.00 to 0.90 |
| 600 v1.1 drafts, Clause-grounded intended-label recall | n/a | 42.7% | 40.0% |
| 600 v1.1 drafts, Clause-grounded harm classifier P / R / F1 / FPR | n/a | 0.430 / 0.183 / 0.257 / 0.243 | 0.430 / 0.183 / 0.257 / 0.243 |
| 600 v1.1 drafts, Clause-grounded failure drafts: screen only / classifier only / both / neither | n/a | 165 / 22 / 33 / 80 | 166 / 26 / 29 / 79 |
| 600 v1.1 drafts, Prompt-only t=0.5 P / R / F1 / FPR | n/a | 0.839 / 0.643 / 0.728 / 0.123 | 0.850 / 0.643 / 0.732 / 0.113 |
| 600 v1.1 drafts, Prompt-only t=0.85 P / R / F1 / FPR | n/a | 0.893 / 0.557 / 0.686 / 0.067 | 0.888 / 0.557 / 0.684 / 0.070 |
| 600 v1.1 drafts, Prompt-only average precision, tie-aware, gated | n/a | 0.727 | 0.725 |
| 600 v1.1 drafts, Prompt-only I1 P / R / F1 | n/a | 0.667 / 0.087 / 0.154 | 0.500 / 0.087 / 0.148 |
| 600 v1.1 drafts, Prompt-only I10 P / R / F1 | n/a | 0.714 / 0.238 / 0.357 | 0.667 / 0.191 / 0.296 |
| 600 v1.1 drafts, Prompt-only I11 P / R / F1 | n/a | 0.500 / 0.385 / 0.435 | 0.500 / 0.308 / 0.381 |
| 600 v1.1 drafts, Prompt-only I14 P / R / F1 | n/a | 0.154 / 0.333 / 0.210 | 0.154 / 0.333 / 0.210 |
| 600 v1.1 drafts, Prompt-only OVER_CAUTION P / R / F1 | n/a | 0.952 / 1.000 / 0.976 | 0.952 / 1.000 / 0.976 |
| Second judge (anthropic/claude-sonnet-5, 180 drafts) F1 | 0.698 | 0.719 | 0.723 |
| Second judge P / R / FPR | 0.747 / 0.656 / 0.222 | 0.779 / 0.667 / 0.189 | 0.789 / 0.667 / 0.178 |
| Utility retention, provider openai/gpt-4.1-mini, judge openai/gpt-4.1-mini | 96.7% | 100.0% | 96.7% |
| Utility retention, provider openai/gpt-4.1-mini, judge anthropic/claude-sonnet-5 | 26.7% | 50.0% | 53.3% |
| Utility retention, provider anthropic/claude-sonnet-5, judge openai/gpt-4.1-mini | 83.3% | 100.0% | 100.0% |
| Utility retention, provider anthropic/claude-sonnet-5, judge anthropic/claude-sonnet-5 | 10.0% | 36.7% | 50.0% |

Matched leakage is higher than covered leakage mainly because matching is one-to-one: when one detection spans two gold names
(a full name and the short form beside it), the second gold span counts as missed although both are substituted.
Covered leakage can in turn exceed the round-trip count, because a name detected under a quasi-identifier label (an employer, say)
is generalised by the sanitiser and does not reach the provider either.
