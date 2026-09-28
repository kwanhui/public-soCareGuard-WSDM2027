# Policy packs (v1, draft)

One YAML file per practice setting. A pack declares which sensitive attributes and
quasi-identifiers are generalised on the way out, what must never leave the premises,
which categories of the conduct taxonomy apply on the way in and with what default action,
and the override policy. The conduct taxonomy is in `socareguard/taxonomy.py`, which adapts the
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

The screen treats any external recipient as a disclosure risk, including the client's own service
providers. A letter to the client's day activity centre about transport can therefore raise I10
for details that the centre needs. A care-team tier, in which the client's own providers are
need-to-know recipients, is future work and needs a change to the taxonomy that the
co-investigators should make.

## Identifiers every pack substitutes

Every pack substitutes the same direct identifiers, namely names, NRIC and FIN numbers, phone
numbers, addresses, dates of birth, case references, email addresses, passports, bank accounts,
social handles, hospital record numbers, ward and bed numbers, vehicle plates, and staff ids.
A staff id is recognised in the formats that the agencies use, which are a role prefix with a
number (`SW-1042`, `MSW-0457`, `FSW-2210`, `PO-2231`) or any id written after "staff id",
"officer id", "employee no." or a similar label. A staff id in another format is not recognised,
so it belongs in the panel's staff id field, which is recorded in the local ledger and is not sent
to the model, rather than in the note.

Every pack also withholds a financial amount whose label is in the same clause, such as an
assistance scheme (ComCare, SMTA, LTA, MediFund, Silver Support), a CPF, Medisave or MediShield
balance, income, arrears, rent, a debt, or a bill. An amount without such a label ("items valued
at about $80") is sent as written.
