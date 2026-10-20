# Terminology: one word per concept

Applies to the panel, the supervisor view, the README, the pack notes and the video captions. The paper keeps its own defined terms where the call's vocabulary or the literature requires them (pseudonymisation, quasi-identifier in the metrics table), but never in the interface.

| Use | Do not use | Meaning |
|---|---|---|
| flag | annotation, finding, hit | one conduct concern the screen raised on a draft |
| policy pack | pack, profile | the rule set for a client group (disability, domestic violence, youth offending) |
| practitioner | worker, user, staff | the person who typed the note and reads the draft |
| supervisor | reviewer, admin, manager | the person who releases a withheld draft or reviews actions |
| recipient | audience | who the draft is for: your own file, the client's care team, or someone outside |
| the client's care team | care-team audience, provider tier | the client's own service providers: day activity centre, clinic, school counsellor |
| details that identify someone when combined | quasi-identifier, quasi | a school, an age, an estate or a facility that identifies a person together |
| stand-in | surrogate, pseudonym, placeholder | the invented name or number that leaves the premises in place of the real one |
| generalised | banded, abstracted | a detail replaced by its kind, level or region and not restored |
| withheld | redacted, suppressed | a passage that never leaves the premises |
| restored | re-identified, de-pseudonymised | a stand-in turned back into the real detail in what you see |
| the screen | the judge, the conduct screen, the classifier | the check of the draft against the conduct taxonomy |
| the screen's model | the judge model, the LLM judge | the model that performs the screen |
| the screen's own confidence | judge confidence | the number the model reports for its flag |
| measured precision | accuracy, validated precision | the share of this category's flags that were correct on the synthetic drafts |
| checked by a person | attested | an identity confirmed by a key this deployment issued |
| typed in | self-asserted | an identity a visitor typed without a key |
| decision | verdict, outcome, action | pass, flagged (annotate), regenerate or escalate, the paper's four decisions |
| pass | clean, OK, approved | no flag; use the draft |
| flagged | annotated | one or more flags; read them, then use the rewrite or keep the passage with a reason. The banner's label adds the paper's name once, "Flagged (annotate)" |
| regenerate | retry, redo | ask the model again with the flags as instructions |
| escalate, withheld | blocked, held, quarantined | the draft is withheld until a supervisor releases it |
| keep with a reason | override | the practitioner keeps a flagged passage and records why |
| use this rewrite | accept, apply | replace the flagged passage with the screen's rewrite |
| release | unblock, approve | a supervisor lets a withheld draft through, with a reason |
| session id | session, case token | the code a practitioner gives a supervisor to find a withheld draft |
| the record | the ledger, the audit log | the append-only file of what left, to whom, and every decision |
| what left the premises | outbound, payload, column 2 | the text sent to the model provider |
| what the model replied (with stand-ins) | inbound, raw reply, column 3 | the reply before stand-ins are restored |
| what you see | restored draft, column 4 | the reply with stand-ins restored |
| the model provider | vendor, upstream, OpenAI | the hosted model that drafts the text |
| the harm classifier | moderation, baseline | the generic safety filter shown for contrast |

Rules: one term per concept; the first mention on a page may add the technical word in parentheses once ("stand-in (surrogate)"); headings and buttons use the plain term only; code identifiers keep their names.
