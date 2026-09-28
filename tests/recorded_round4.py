"""Synthetic test notes (2026-09-28) with the Presidio and GLiNER2 hits recorded on them.

Recorded by running both NER backends on each message as the proxy sends it (the instruction and
the note joined by a blank line). ``use(monkeypatch, name)`` replays the recorded hits, so a test
sees the spans that the recorded run saw without loading the models. Three of the notes (the
helper's work permit, the transfer summary and the Hokkien note) are rebuilt from the outbound
text and the panel's replacement table."""

from __future__ import annotations

from socareguard.detect import backends
from socareguard.detect.sg import Hit

NOTES: dict[str, dict] = {
    "fsc_plan": {
        "pack": "disability",
        "text": "Draft a referral summary for the psychiatric follow-up.\n\nReferral note, 24 Sep 2026. Client: Wei Jie Tan, age 26, referred to the Institute of Mental Health for follow-up. Diagnosed with major depressive disorder in March 2026, currently prescribed sertraline 100mg daily. Under the care of Dr Lester Ng, psychiatrist. Client reports improved mood but ongoing sleep difficulties.\n\nPlan: continue psychiatric follow-up, monitor medication compliance, refer for counselling.",
        "presidio": [
            (93, 104, "Wei Jie Tan", "NAME", 0.85),
            (294, 303, "Lester Ng", "NAME", 0.85),
        ],
        "gliner": [
            (93, 104, "Wei Jie Tan", "NAME", 0.99),
            (291, 303, "Dr Lester Ng", "NAME", 0.85),
            (130, 156, "Institute of Mental Health", "EMPLOYER", 0.61),
        ],
        "gliner_attr": [
            (187, 212, "major depressive disorder", "ATTR:disability", 0.69),
            (396, 417, "psychiatric follow-up", "ATTR:safety_plan", 0.43),
        ],
    },
    "fsc_mall": {
        "pack": "youth-offending",
        "text": "Summarise this note.\n\nClient Aisha Lim, 14, caught shoplifting at Jurong Point on 26 Sep 2026. Referred by mall security to school, Sec 2 at Merlion Secondary School.",
        "presidio": [
            (29, 38, "Aisha Lim", "NAME", 0.85),
        ],
        "gliner": [
            (29, 38, "Aisha Lim", "NAME", 0.99),
            (141, 165, "Merlion Secondary School", "SCHOOL", 0.99),
            (107, 120, "mall security", "EMPLOYER", 0.77),
            (40, 42, "14", "DOB", 0.56),
        ],
        "gliner_attr": [
            (51, 62, "shoplifting", "ATTR:offence", 0.77),
        ],
    },
    "prob_youthcourt": {
        "pack": "youth-offending",
        "text": "Write a six-month progress report to the Youth Court on this case.\n\nClient: Ryan Koh Zhi Hao, NRIC T1198765F, DOB 03/11/2010, age 15, Seletar Hills Secondary School, Sec 3. Address: Blk 512 Fernvale Road #08-112, Singapore 790512. Ryan is on a 12-month probation order dated 14 Feb 2026 with conditions: a curfew of 9pm to 6am, 80 hours of community service (52 completed to date), and a no-contact condition naming co-accused Marcus Tay Wei Ming. He was charged with two offences: shop theft on 10 Jan 2026, which he admitted and for which the probation order was made, and a separate charge of unlawful assembly on 2 Feb 2026, which was withdrawn by the prosecution on 20 Mar 2026 for insufficient evidence. His mother, Christine Koh Mei Ling, contactable at 9123 4567, attends every review session. Ryan has complied with the curfew and has completed 52 of the 80 community service hours.",
        "presidio": [
            (76, 92, "Ryan Koh Zhi Hao", "NAME", 0.85),
            (231, 235, "Ryan", "NAME", 0.85),
            (427, 446, "Marcus Tay Wei Ming", "NAME", 0.85),
            (722, 744, "Christine Koh Mei Ling", "NAME", 0.85),
            (802, 806, "Ryan", "NAME", 0.85),
        ],
        "gliner": [
            (722, 744, "Christine Koh Mei Ling", "NAME", 1.0),
            (76, 92, "Ryan Koh Zhi Hao", "NAME", 1.0),
            (427, 446, "Marcus Tay Wei Ming", "NAME", 1.0),
            (99, 108, "T1198765F", "NRIC", 1.0),
            (761, 770, "9123 4567", "PHONE", 1.0),
            (134, 164, "Seletar Hills Secondary School", "SCHOOL", 0.99),
            (41, 52, "Youth Court", "EMPLOYER", 0.52),
            (114, 124, "03/11/2010", "DOB", 1.0),
        ],
        "gliner_attr": [
            (244, 268, "12-month probation order", "ATTR:ppo", 0.54),
            (482, 492, "shop theft", "ATTR:offence", 0.98),
            (596, 613, "unlawful assembly", "ATTR:offence", 0.97),
        ],
    },
    "prob_pending": {
        "pack": "youth-offending",
        "text": "Write a note for my own case file on the second charge, setting out the young person's position.\n\nClient: Daniel Wong Jun Kai, NRIC T1176543D, DOB 15/03/2011, age 14. Two charges: first, shop theft on 3 Aug 2026, admitted, dealt with by a stern warning. Second, criminal trespass on 10 Aug 2026, which Daniel denies; he says he was not present at the scene. The co-accused, Tan Wei Loon, gave a statement to police naming Daniel as present at the scene; the two accounts differ. The second charge is pending before the Youth Court.",
        "presidio": [
            (106, 125, "Daniel Wong Jun Kai", "NAME", 0.85),
            (302, 308, "Daniel", "NAME", 0.85),
            (374, 386, "Tan Wei Loon", "NAME", 0.85),
            (422, 428, "Daniel", "NAME", 0.85),
        ],
        "gliner": [
            (374, 386, "Tan Wei Loon", "NAME", 1.0),
            (106, 125, "Daniel Wong Jun Kai", "NAME", 0.99),
            (132, 141, "T1176543D", "NRIC", 1.0),
            (147, 157, "15/03/2011", "DOB", 1.0),
        ],
        "gliner_attr": [
            (262, 279, "criminal trespass", "ATTR:offence", 0.99),
            (187, 197, "shop theft", "ATTR:offence", 0.98),
            (483, 496, "second charge", "ATTR:offence", 0.64),
        ],
    },
    "prob_singlish": {
        "pack": "youth-offending",
        "text": "Write a progress note for the case file in plain working language.\n\nClient Zhi Feng kena caught shoplifting at Compass One on 12 Sep 2026, first time. His mother say she very worried, always ask him go straight home after school. He stay at Blk 203 Sengkang East Way, studying at Springleaf Secondary. Officer feel he can change if got more supervision.",
        "presidio": [
            (75, 88, "Zhi Feng kena", "NAME", 0.85),
        ],
        "gliner": [
            (75, 83, "Zhi Feng", "NAME", 0.95),
            (241, 266, "Blk 203 Sengkang East Way", "ADDRESS", 0.96),
            (280, 300, "Springleaf Secondary", "SCHOOL", 1.0),
            (111, 122, "Compass One", "EMPLOYER", 0.9),
            (126, 137, "12 Sep 2026", "DOB", 0.91),
        ],
        "gliner_attr": [
            (96, 107, "shoplifting", "ATTR:offence", 0.5),
        ],
    },
    "dv_workplace": {
        "pack": "domestic-violence",
        "text": "Write a short update note for the file.\n\nUpdate, 27 Sep 2026. Client Mdm Halimah binti Yaacob, 32, case ref FSC-2026-2201. Halimah has a new mobile number, 9123 4567, which her husband Zaki bin Rahman does not have. She has started a new job as a retail assistant at Uniqlo Bugis Junction and asked that this not be mentioned to Zaki if he calls the centre.\n\nAssessment: continue monitoring; safety plan unchanged.",
        "presidio": [
            (69, 80, "Mdm Halimah", "NAME", 0.85),
            (81, 93, "binti Yaacob", "NAME", 0.85),
            (185, 200, "Zaki bin Rahman", "NAME", 0.85),
            (329, 333, "Zaki", "NAME", 0.85),
        ],
        "gliner": [
            (185, 200, "Zaki bin Rahman", "NAME", 1.0),
            (73, 93, "Halimah binti Yaacob", "NAME", 0.99),
            (156, 165, "9123 4567", "PHONE", 1.0),
            (267, 288, "Uniqlo Bugis Junction", "EMPLOYER", 1.0),
            (108, 121, "FSC-2026-2201", "CASE_REF", 0.98),
        ],
        "gliner_attr": [
            (392, 413, "safety plan unchanged", "ATTR:safety_plan", 0.68),
        ],
    },
    "wsdm_intake": {
        "pack": "disability",
        "text": "Draft a referral note (about 100 words) to the intake officer at a partner family service centre describing the client's situation and the support requested.\n\nIntake note, 27 Sep 2026. Client: TAN WEI MING (also written Tan, Wei Ming; goes by Ah Ming), NRIC s1234567d (also on file as S 1234567 D), DOB 03/04/1988, hp +65 9123 4567, email weiming.tan@example.org, case ref FSC-2026-0777. Lives at Blk 88 Bedok North Street 4 #05-123, S(460088), with his mother Mdm Lim Ah Choo (NRIC S5012345Z, 70) and his son Marcus (Tan Jun Kai, 9, P3 at Tanglin Park Primary School). Wei Ming's brother, Tan Wei Jie, works at Changi Airport Terminal 3 as a baggage handler. Client was diagnosed with schizophrenia at IMH in 2019 and is on risperidone 2mg. He was retrenched from Ah Ming's Kopitiam in Aug. Rent arrears $1,200 with HDB. Assessment: low risk to self; mother is the main carer. Plan: ComCare application, refer to the Bedok FSC for family support.",
        "presidio": [
            (339, 362, "weiming.tan@example.org", "EMAIL", 1.0),
            (193, 205, "TAN WEI MING", "NAME", 0.85),
            (220, 223, "Tan", "NAME", 0.85),
            (225, 233, "Wei Ming", "NAME", 0.85),
            (243, 250, "Ah Ming", "NAME", 0.85),
            (461, 476, "Mdm Lim Ah Choo", "NAME", 0.85),
            (510, 516, "Marcus", "NAME", 0.85),
            (518, 529, "Tan Jun Kai", "NAME", 0.85),
            (570, 580, "Wei Ming's", "NAME", 0.85),
            (590, 601, "Tan Wei Jie", "NAME", 0.85),
            (765, 774, "Ah Ming's", "NAME", 0.85),
            (775, 783, "Kopitiam", "NAME", 0.85),
            (318, 331, "+65 9123 4567", "PHONE", 0.4),
        ],
        "gliner": [
            (193, 205, "TAN WEI MING", "NAME", 0.99),
            (461, 476, "Mdm Lim Ah Choo", "NAME", 0.98),
            (590, 601, "Tan Wei Jie", "NAME", 0.98),
            (518, 529, "Tan Jun Kai", "NAME", 0.94),
            (510, 516, "Marcus", "NAME", 0.9),
            (225, 233, "Wei Ming", "NAME", 0.77),
            (765, 772, "Ah Ming", "NAME", 0.71),
            (243, 250, "Ah Ming", "NAME", 0.57),
            (258, 267, "s1234567d", "NRIC", 1.0),
            (483, 492, "S5012345Z", "NRIC", 0.99),
            (285, 296, "S 1234567 D", "NRIC", 0.97),
            (318, 331, "+65 9123 4567", "PHONE", 1.0),
            (540, 567, "Tanglin Park Primary School", "SCHOOL", 1.0),
            (612, 637, "Changi Airport Terminal 3", "SCHOOL", 0.71),
            (612, 637, "Changi Airport Terminal 3", "EMPLOYER", 0.95),
            (540, 567, "Tanglin Park Primary School", "EMPLOYER", 0.67),
            (703, 706, "IMH", "EMPLOYER", 0.55),
            (373, 386, "FSC-2026-0777", "CASE_REF", 0.98),
            (303, 313, "03/04/1988", "DOB", 1.0),
        ],
        "gliner_attr": [
            (686, 699, "schizophrenia", "ATTR:disability", 0.77),
            (884, 903, "ComCare application", "ATTR:safety_plan", 0.49),
        ],
    },
    "fsc_permit": {
        "pack": "disability",
        "text": "Summarise this home visit note.\n\nHome visit note, 23 Sep 2026. Client: Madam Tan Siew Cheng, age 82, lives alone at Blk 45 Commonwealth Drive #03-112, Singapore 140045. Domestic helper Siti Aminah, work permit number G1234567N, has been assisting with daily care since June 2026. Client's mobility has declined; referred to occupational therapy for a home safety assessment.\n\nPlan: arrange OT home visit, review helper's work permit renewal due Dec 2026.",
        "presidio": [
            (77, 91, "Tan Siew Cheng", "NAME", 0.85),
            (185, 196, "Siti Aminah", "NAME", 0.85),
        ],
        "gliner": [
            (185, 196, "Siti Aminah", "NAME", 0.99),
            (77, 91, "Tan Siew Cheng", "NAME", 0.97),
        ],
        "gliner_attr": [
            (198, 226, "work permit number G1234567N", "ATTR:ppo", 0.61),
        ],
    },
    "fsc_ahbeng": {
        "pack": "disability",
        "text": 'Summarise this home visit note.\n\nHome visit note, 21 Sep 2026. Client: Lim Ah Beng, age 68. 阿伯今天情绪比较低落 (grandfather seemed quite low in mood today), keeps saying "bo eng, bo lang thang" (no time, no one to talk to) hokkien. Wife 阿嫁 (ah ma) said he has not been sleeping well and "gu ah, kut lat" (very tired) hokkien for the past two weeks. Client\'s son Lim Wei Ming, age 40, lives nearby at Blk 330 Ang Mo Kio Ave 1 #05-221, Singapore 560330, visits weekly.\n\nPlan: monitor mood, consider referral to elderly mental health service if low mood persists.',
        "presidio": [
            (71, 82, "Lim Ah Beng", "NAME", 0.85),
            (92, 102, "阿伯今天情绪比较低落", "NAME", 0.85),
            (171, 184, "bo lang thang", "NAME", 0.85),
            (354, 366, "Lim Wei Ming", "NAME", 0.85),
        ],
        "gliner": [
            (354, 366, "Lim Wei Ming", "NAME", 0.98),
            (71, 82, "Lim Ah Beng", "NAME", 0.98),
            (501, 530, "elderly mental health service", "FACILITY", 0.6),
        ],
        "gliner_attr": [],
    },
    "fsc_transfer": {
        "pack": "disability",
        "text": "Draft a case transfer handover summary for the incoming worker.\n\nCase transfer summary, 20 Sep 2026, handed over from Ms Rachel Tan to the incoming worker.\n\nClient: Halimah binti Yusof, NRIC S8123987A, age 39, residing at Blk 512 Hougang Avenue 10 #07-118, Singapore 530512. Halimah has been on this caseload since March 2025, referred by the polyclinic after her youngest child was flagged for delayed development. Husband Kamal bin Ahmad, age 42, works as a delivery driver and is often out of the house from early morning to late evening. The couple has three children: Nurul (12, P6 at Tanglin Park Primary School), Haziq (9, P3 at the same school), and Aiman (1, still at home). Halimah's mother, Zainab binti Yusof, age 66, moved in with the family in June 2025 to help with childcare, and the household now has six people in a four-room flat.\n\nMs Rachel Tan, the outgoing worker, has managed this case for eighteen months. Her notes record steady progress on Aiman's early intervention plan, coordinated with the polyclinic, though two appointments were missed in July and August 2026 due to Kamal's irregular work hours. Nurul's form teacher, Mr David Lim, contacted Rachel in August 2026 to flag that Nurul has been arriving late and appears tired, which the family attributes to sharing a room with her grandmother and younger siblings.\n\nFinancially, the household receives ComCare short-to-medium term assistance of $580 per month, reviewed most recently in May 2026, and Zainab draws a Silver Support payout of $300 per quarter. Rachel's assessment as at her last review, 5 Sep 2026, was that the family is coping but stretched, with housing density the main stressor rather than any protection concern. She recommended a referral to the Housing Development Board for a possible larger unit or rental flat transfer, and continued monitoring of Aiman's developmental appointments.\n\nPlan for the incoming worker: confirm the HDB referral has been lodged, follow up directly with Mr David Lim on Nurul's attendance and any further signs of strain, reschedule Aiman's missed polyclinic appointments before the end of October 2026, and complete a fresh household assessment given Zainab's now-permanent presence in the home. Rachel is available for a handover call in the first week if needed. Rachel also flagged that the polyclinic's next developmental review for Aiman falls in the same week as Nurul's school examinations, and suggested the incoming worker check whether Kamal can take leave to cover one of the two.",
        "presidio": [
            (118, 131, "Ms Rachel Tan", "NAME", 0.85),
            (165, 184, "Halimah binti Yusof", "NAME", 0.85),
            (424, 439, "Kamal bin Ahmad", "NAME", 0.85),
            (573, 578, "Nurul", "NAME", 0.85),
            (658, 663, "Aiman", "NAME", 0.85),
            (702, 720, "Zainab binti Yusof", "NAME", 0.85),
            (851, 864, "Ms Rachel Tan", "NAME", 0.85),
            (966, 971, "Aiman", "NAME", 0.85),
            (1099, 1104, "Kamal", "NAME", 0.85),
            (1154, 1163, "David Lim", "NAME", 0.85),
            (1175, 1181, "Rachel", "NAME", 0.85),
            (1483, 1489, "Zainab", "NAME", 0.85),
            (1541, 1547, "Rachel", "NAME", 0.85),
            (1856, 1861, "Aiman", "NAME", 0.85),
            (1992, 2001, "David Lim", "NAME", 0.85),
            (2068, 2073, "Aiman", "NAME", 0.85),
            (2187, 2193, "Zainab", "NAME", 0.85),
            (2232, 2238, "Rachel", "NAME", 0.85),
            (2301, 2307, "Rachel", "NAME", 0.85),
            (2373, 2378, "Aiman", "NAME", 0.85),
            (2482, 2487, "Kamal", "NAME", 0.85),
        ],
        "gliner": [
            (424, 439, "Kamal bin Ahmad", "NAME", 0.99),
            (165, 184, "Halimah binti Yusof", "NAME", 0.99),
            (702, 720, "Zainab binti Yusof", "NAME", 0.99),
            (2373, 2378, "Aiman", "NAME", 0.95),
            (658, 663, "Aiman", "NAME", 0.95),
            (573, 578, "Nurul", "NAME", 0.94),
            (2405, 2410, "Nurul", "NAME", 0.92),
            (1856, 1861, "Aiman", "NAME", 0.91),
            (1210, 1215, "Nurul", "NAME", 0.91),
            (620, 625, "Haziq", "NAME", 0.9),
            (2005, 2010, "Nurul", "NAME", 0.9),
            (2068, 2073, "Aiman", "NAME", 0.89),
            (1129, 1134, "Nurul", "NAME", 0.89),
            (1992, 2001, "David Lim", "NAME", 0.87),
            (966, 971, "Aiman", "NAME", 0.87),
            (1154, 1163, "David Lim", "NAME", 0.86),
            (121, 131, "Rachel Tan", "NAME", 0.8),
            (854, 864, "Rachel Tan", "NAME", 0.76),
            (191, 200, "S8123987A", "NRIC", 0.99),
            (590, 617, "Tanglin Park Primary School", "SCHOOL", 0.99),
            (2330, 2340, "polyclinic", "EMPLOYER", 0.89),
            (1020, 1030, "polyclinic", "EMPLOYER", 0.87),
            (2083, 2093, "polyclinic", "EMPLOYER", 0.84),
            (1750, 1775, "Housing Development Board", "EMPLOYER", 0.83),
            (343, 353, "polyclinic", "EMPLOYER", 0.78),
            (1935, 1938, "HDB", "EMPLOYER", 0.57),
        ],
        "gliner_attr": [],
    },
}


def _hits(name: str, backend: str, detector: str):
    def fn(text: str, *args, **kwargs) -> list[Hit]:
        note = NOTES[name]
        if text != note["text"]:
            return []
        return [Hit(s, e, t, cat, detector, sc) for s, e, t, cat, sc in note[backend]]

    return fn


def use(monkeypatch, name: str) -> dict:
    """Replay the recorded NER hits for note ``name`` and return the note (pack and text)."""
    monkeypatch.setattr(backends, "presidio_hits", _hits(name, "presidio", "presidio.PERSON"))
    monkeypatch.setattr(backends, "gliner_hits", _hits(name, "gliner", "gliner"))
    monkeypatch.setattr(
        backends, "gliner_attribute_hits", _hits(name, "gliner_attr", "gliner.attr")
    )
    monkeypatch.setattr(backends, "gliner_backend_name", lambda: "recorded")
    return NOTES[name]
