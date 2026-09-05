# Metrics

Generated 2026-09-05 at commit `36a3ca9` by `python3 -m socareguard.eval report` from the JSON files in this folder.
Corpus: `corpus-v1` (300 synthetic notes, 4,874 gold spans). Every number below is measured on synthetic material; see `corpus/README.md`.

These tables are the compliance artefact that PDPC's Advisory Guidelines on Use of Personal Data in Generative AI (section 8.3)
ask a System Provider to document: the rate at which personal identifiers are detected and redacted before a request leaves the premises.

## Outbound detection (full pipeline)

Detectors: sg, gazetteer, presidio, fastino/gliner2-privacy-filter-PII-multi. Latency per note p50 1.37 s, p95 6.18 s (CPU).

| Category | Exact P | Exact R | Exact F1 | Relaxed P | Relaxed R | Relaxed F1 | Gold |
|---|---|---|---|---|---|---|---|
| ADDRESS | 0.923 | 0.947 | 0.935 | 1.000 | 1.000 | 1.000 | 114 |
| AGE | 0.931 | 0.890 | 0.910 | 0.931 | 0.890 | 0.910 | 301 |
| ALL | 0.903 | 0.942 | 0.922 | 0.949 | 0.980 | 0.964 | 4173 |
| CASE_REF | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 214 |
| DOB | 0.990 | 1.000 | 0.995 | 0.990 | 1.000 | 0.995 | 101 |
| EMPLOYER | 0.431 | 0.590 | 0.498 | 0.584 | 0.800 | 0.675 | 100 |
| ESTATE | 0.896 | 0.987 | 0.939 | 0.896 | 0.987 | 0.939 | 313 |
| FACILITY | 0.950 | 0.990 | 0.970 | 0.960 | 1.000 | 0.980 | 290 |
| NAME | 0.841 | 0.906 | 0.873 | 0.947 | 0.983 | 0.965 | 1409 |
| NRIC | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 302 |
| PHONE | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 137 |
| SCHOOL | 0.907 | 0.985 | 0.945 | 0.921 | 1.000 | 0.959 | 199 |
| THIRD_PARTY_NAME | 1.000 | 0.971 | 0.985 | 1.000 | 0.994 | 0.997 | 693 |

**Leakage rate** (gold DIRECT spans with no overlapping detection): 28 of 2970 = 0.9%.
Per pack: disability 1.6%, domestic-violence 1.5%, youth-offending 0.0%.

**Recall by name origin** (relaxed, NAME and THIRD_PARTY_NAME): chinese 97.7% (n=428), eurasian 98.2% (n=385), indian 99.6% (n=456), malay 99.3% (n=413), western 98.6% (n=420).

**Attribute recall** (a gold ATTRIBUTE span counts as found when any attribute detection overlaps it): capacity 98.7% (n=78), diagnosis 100.0% (n=76), disability 85.0% (n=100), dv_disclosure 82.0% (n=100), minor 91.0% (n=100), offence 95.0% (n=100), ppo 100.0% (n=79), safety_plan 80.9% (n=68).

## Ablation: what each layer adds

| Configuration | Relaxed P | Relaxed R | Relaxed F1 | Leakage | p50 latency |
|---|---|---|---|---|---|
| Singapore recognisers + gazetteers only | 0.970 | 0.479 | 0.641 | 70.8% | 0.001 s |
| + Presidio | 0.970 | 0.966 | 0.968 | 2.4% | 0.051 s |
| + GLiNER2-PII (full) | 0.949 | 0.980 | 0.964 | 0.9% | 1.365 s |

The deterministic layer alone catches every NRIC, phone number and case reference at near-perfect precision but no names;
Presidio adds most names; GLiNER2-PII closes the remaining name and address gap at the cost of latency.

## Round trip (sanitise, then restore, no model in the loop)

| Consistency (one outbound form per original) | 98.3% |
|---|---|
| Injectivity (no two entities share an outbound form) | 97.7% |
| Surrogate fidelity (every substituted span restored verbatim, none left) | 88.0% |
| Exact text fidelity (whole note identical after restore) | 29.7% |
| Gold DIRECT strings still present in the outbound text | 0.1% (2 of 2970) |
| Gold ATTRIBUTE spans sent verbatim (not generalised) | 11.6% (81 of 701) |
| Spans substituted / generalised | 3005 / 2344 |
| Latency p50 / p95 | 1.48 s / 5.89 s |

Exact text fidelity is low by design: generalisation is one-way, so a note that carried a diagnosis or a
school name comes back with the generalised phrase unless the model reproduced it exactly. Surrogate fidelity
is the measure that matters for re-identification.

## Utility retention per provider

30 notes (10 per pack). For each provider, a case summary drafted from the raw note (never run in production) is compared
with the summary drafted through the guard and restored; both providers judge every pair on a 1 to 5 scale, blind to condition,
so each provider's drafts are scored by itself and by the other model. Retention is the share of pairs rated 4 or 5.

| Provider | Judge | n | Mean score | Retention | Score histogram 1..5 | Per pack mean |
|---|---|---|---|---|---|---|
| openai/gpt-4.1-mini | openai/gpt-4.1-mini | 30 | 4.367 | 96.7% | 0/0/1/17/12 | disability 4.5, domestic-violence 4.1, youth-offending 4.5 |
| openai/gpt-4.1-mini | anthropic/claude-sonnet-5 | 30 | 3.067 | 26.7% | 0/6/16/8/0 | disability 3.3, domestic-violence 2.8, youth-offending 3.1 |
| anthropic/claude-sonnet-5 | openai/gpt-4.1-mini | 30 | 4.233 | 83.3% | 0/0/5/13/12 | disability 4.3, domestic-violence 4.3, youth-offending 4.1 |
| anthropic/claude-sonnet-5 | anthropic/claude-sonnet-5 | 30 | 2.833 | 10.0% | 0/8/19/3/0 | disability 2.9, domestic-violence 2.5, youth-offending 3.1 |

Leak-check pass rate on the guarded path: openai/gpt-4.1-mini 100.0%, anthropic/claude-sonnet-5 100.0%.

## Inbound conduct screen (labelled drafts)

600 drafts (300 written under a single-failure instruction, 300 compliant). Judge: `openai/gpt-4.1` at temperature 0 with the pack's SASW clause table; deterministic rules for over-caution; disclosure categories gated on an external audience in the instruction. Labels are generation-intent labels, so these are
behaviour on scripted material, not validated accuracy. F1, AUPRC and FPR are reported together, as for safety classifiers.

| Scope | Precision | Recall | F1 | FPR | AUPRC |
|---|---|---|---|---|---|
| Any conduct flag vs compliant | 0.814 | 0.713 | 0.760 | 0.163 | 0.815 |
| I1 Emotive or derogatory documentation language | 0.233 | 0.304 | 0.264 | 0.040 | 0.279 |
| I10 Disclosure or referral without consent | 0.500 | 0.667 | 0.571 | 0.024 | 0.262 |
| I11 Consent language inappropriate to capacity | 1.000 | 0.462 | 0.632 | 0.000 | 0.495 |
| I12 Advice contrary to organisational policy or prot | 0.667 | 0.100 | 0.174 | 0.002 | 0.144 |
| I13 Re-identifying detail reintroduced by the model | 0.000 | 0.000 | 0.000 | 0.003 | 0.036 |
| I14 Identifies a protected child or young person in  | 0.316 | 1.000 | 0.480 | 0.022 | 0.265 |
| I2 Disrespectful language about the client | 0.085 | 0.174 | 0.114 | 0.074 | 0.055 |
| I3 Fabricated or unsupported content in a case note | 0.455 | 0.682 | 0.545 | 0.031 | 0.489 |
| I4 Discriminatory or culturally insensitive framing | 0.800 | 0.182 | 0.296 | 0.002 | 0.249 |
| I5 Overrides client self-determination | 0.449 | 1.000 | 0.620 | 0.047 | 0.947 |
| I6 Treats imminent risk as ordinary autonomy | 0.500 | 0.091 | 0.154 | 0.004 | 0.095 |
| I7 Boundary-violating suggestion | 1.000 | 0.909 | 0.952 | 0.000 | 0.915 |
| I8 Out-of-scope clinical or legal advice | 0.364 | 0.182 | 0.242 | 0.012 | 0.147 |
| I9 Unrealistic expectation-setting about outcomes | 0.846 | 0.500 | 0.629 | 0.004 | 0.501 |
| OVER_CAUTION Over-cautious boilerplate that displaces the pro | 1.000 | 0.650 | 0.788 | 0.000 | 0.681 |

Intended-label recall (the instructed failure is among the flags raised): 43.3%.
Operating points by judge-confidence threshold (any flag vs compliant): t=0.5: P 0.81 / R 0.71 / F1 0.76 / FPR 0.16; t=0.7: P 0.81 / R 0.71 / F1 0.76 / FPR 0.16; t=0.85: P 0.96 / R 0.57 / F1 0.72 / FPR 0.02; t=0.95: P 0.97 / R 0.50 / F1 0.66 / FPR 0.01.

**Generic harm classifier on the same drafts** (openai omni-moderation-latest (any category >= 0.3)): precision 0.430, recall 0.183, F1 0.257, FPR 0.243.
Of the failure drafts, 177 were flagged by the conduct screen only, 37 by both, 18 by the harm classifier only, 68 by neither.
This is the H1 finding: professional-conduct failures are largely invisible to a harm taxonomy.

Per pack (any flag vs compliant): disability F1 0.753 / FPR 0.340, domestic-violence F1 0.785 / FPR 0.130, youth-offending F1 0.741 / FPR 0.020.

**Cross-provider check** (`anthropic/claude-sonnet-5`, 180 drafts): any-flag precision 0.747, recall 0.656, F1 0.698, FPR 0.222; intended-label recall 52.2%.
The drafts were generated by gpt-4.1-mini and the runtime judge is gpt-4.1, so this second judge from another provider guards against same-family leniency.

## Reading these numbers

- Gold spans are exact character offsets produced by injection, so exact-match scores are strict; relaxed (overlap) scores are the ones comparable to the de-identification literature.
- Cohen's kappa is not reported for spans; the corpus has no second annotator and span kappa is the wrong instrument (Deleger et al., 2012).
- Leakage counts a miss whenever a gold DIRECT span has no overlapping detection, whatever the reason.
- Dates of contact are not annotated in corpus v1 and are not scored.
