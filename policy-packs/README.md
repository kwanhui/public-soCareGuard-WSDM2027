# Policy packs (v1, draft)

One YAML file per practice setting. A policy pack declares which sensitive details, and which
details that identify someone when combined (quasi-identifiers), are generalised on the way
out, what must never leave the premises, which categories of the conduct taxonomy apply on the
way in and with what default action, and when a practitioner may keep a flagged passage with a
reason (the override policy). The conduct taxonomy is in `socareguard/taxonomy.py`, which adapts the
structure of Iftikhar et al. (AIES 2025) and re-anchors it on the SASW Code of
Professional Ethics, 3rd Revision (2017).

**Status: draft.** The schema was assembled by a computing researcher from published
documents and has not yet been reviewed by social-work practitioners. Items marked
`grounded: false` could not be traced to a clause, and they are flagged for that review rather
than dropped.

The packs are at v1. The outbound generalisation rules run in the proxy, and the inbound
categories and their default actions drive the conduct screen. The v0 packs from the corpus
build were declarative only.

In the youth-offending pack, an external document that names a young person protected under the
Children and Young Persons Act escalates on I14. This is the pack's design, and the supervisor
release is the need-to-know path for such a document.

The screen distinguishes three audiences, namely internal (the worker's own file or supervisor),
care-team and external. A care-team recipient is one of the client's own providers, such as a day
activity centre, the client's GP, polyclinic, clinic, doctor or psychiatrist, a school counsellor,
the form teacher of a young person, shelter staff, a co-case agency, or the medical social worker at
a named hospital. For such a recipient, the judge reads I10 within the recipient's role, so that
detail about what the client can do or needs is not disclosure, whereas a diagnosis or a history
is disclosure unless consent is recorded. This tier is a draft reading of SASW A.6.d pending
practitioner review, and it does not change the taxonomy. An instruction that also names any
other external recipient resolves as external, and a statutory recipient resolves as before. I14
still applies to a care-team recipient, so that a youth-offending letter that names the young
person and the offence to a school counsellor still escalates.

## Identifiers every pack substitutes

Every pack replaces the same direct identifiers with stand-ins, namely names, NRIC and FIN numbers, phone
numbers, addresses, dates of birth, case references, email addresses, passports, bank accounts,
social handles, hospital record numbers, ward and bed numbers, vehicle plates, and staff ids.
A staff id is recognised in the formats that the agencies use, which are a role prefix with a
number (`SW-1042`, `MSW-0457`, `FSW-2210`, `PO-2231`) or any id written after "staff id",
"officer id", "employee no." or a similar label. A staff id in another format is not recognised,
so it belongs in the panel's staff id field, which is kept in the local record (the ledger) and is
not sent to the model provider, rather than in the note.

Every pack also withholds a financial amount whose label is in the same clause, such as an
assistance scheme (ComCare, SMTA, LTA, MediFund, Silver Support), a CPF, Medisave or MediShield
balance, income, arrears, rent, a debt, or a bill. An amount without such a label ("items valued
at about $80") is sent as written.
