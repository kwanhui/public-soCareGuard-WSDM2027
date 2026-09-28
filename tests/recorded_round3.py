"""Round-3 reviewers' notes (2026-09-28) with the Presidio and GLiNER2 hits recorded on them.

Recorded by running both NER backends on each message, as the proxy sends it (the instruction and
the note joined by a blank line). ``use(monkeypatch, name)`` replays the recorded hits, so a test
sees the spans the reviewer's run saw without loading the models. The coach's handover note is a
reconstruction from the evidence files (the report quotes the outbound text, not the note)."""

from __future__ import annotations

from socareguard.detect import backends
from socareguard.detect.sg import Hit

NOTES: dict[str, dict] = {
    "youth_malay": {
        "pack": "youth-offending",
        "text": "Write a referral letter to the school counsellor about this case, in the practitioner's usual working notes style.\n\nNama: Ahmad Danish bin Yusof, NRIC T1121098D, umur 15 tahun, sekolah Fernvale Secondary, Sec 3. Duduk Blk 302 Fernvale Link #06-034, Singapore 790302. Mak dia, Zainab binte Osman, single mother, kerja shift kilang. Ahmad kena tangkap sebab shop theft kat Sengkang mall on 8 Sep 2026, dia ambil barang harga around $30. This is his first time lah, dia cakap 'saya tau salah, tapi kawan-kawan ajak'. Sekolah punya form teacher pun concern sikit sebab attendance okay but recently a bit moody. Family cooperative, mak datang every session on time.",
        "presidio": [
            (122, 144, "Ahmad Danish bin Yusof", "NAME", 0.85),
            (177, 203, "sekolah Fernvale Secondary", "NAME", 0.85),
            (267, 274, "Mak dia", "NAME", 0.85),
            (276, 294, "Zainab binte Osman", "NAME", 0.85),
            (331, 341, "Ahmad kena", "NAME", 0.85),
            (367, 379, "kat Sengkang", "NAME", 0.85),
            (463, 466, "dia", "NAME", 0.85),
            (474, 488, "saya tau salah", "NAME", 0.85),
            (490, 500, "tapi kawan", "NAME", 0.85),
            (507, 511, "ajak", "NAME", 0.85),
            (627, 637, "mak datang", "NAME", 0.85),
        ],
        "gliner": [
            (276, 294, "Zainab binte Osman", "NAME", 1.0),
            (122, 144, "Ahmad Danish bin Yusof", "NAME", 0.99),
            (151, 160, "T1121098D", "NRIC", 1.0),
            (185, 203, "Fernvale Secondary", "SCHOOL", 0.93),
        ],
        "gliner_attr": [
            (356, 366, "shop theft", "ATTR:offence", 0.8),
        ],
    },
    "youth_offender": {
        "pack": "youth-offending",
        "text": "Write a note for my own case file summarising the offender's compliance with the programme; use the term the offender throughout as our internal file convention requires.\n\nClient: Haziq bin Rahman, NRIC T1143210C, DOB 07/02/2010, age 16, Sunrise Secondary School, Sec 4. Address: Blk 145 Clementi Avenue 2 #07-089, Singapore 120145. Haziq was convicted of shop theft on 10 Jun 2026 and placed on a probation order with community service. He has completed 40 of 60 hours and attends all sessions on time. His mentor reports good engagement and no new incidents.",
        "presidio": [
            (180, 196, "Haziq bin Rahman", "NAME", 0.85),
        ],
        "gliner": [
            (180, 196, "Haziq bin Rahman", "NAME", 0.97),
            (203, 212, "T1143210C", "NRIC", 1.0),
            (238, 262, "Sunrise Secondary School", "SCHOOL", 0.99),
            (218, 228, "07/02/2010", "DOB", 1.0),
        ],
        "gliner_attr": [
            (398, 413, "probation order", "ATTR:ppo", 0.53),
            (356, 366, "shop theft", "ATTR:offence", 0.96),
        ],
    },
    "youth_withdrawn": {
        "pack": "youth-offending",
        "text": "Write a referral letter to the school counsellor about this case.\n\nClient: Aisyah binte Karim, NRIC T1165789Z, DOB 22/04/2011, age 15, Meadowvale Secondary School, Sec 3. Address: Blk 341 Toa Payoh Lorong 6 #03-114, Singapore 310341. The charge of shop theft against Aisyah was withdrawn by the prosecution on 15 Aug 2026 after CCTV footage showed she was not involved; the case was closed with no further action. Aisyah has consistently denied any involvement from the start. She remains anxious that classmates believe she was guilty and would like support to settle back into school.",
        "presidio": [
            (75, 93, "Aisyah binte Karim", "NAME", 0.85),
            (414, 420, "Aisyah", "NAME", 0.85),
        ],
        "gliner": [
            (75, 93, "Aisyah binte Karim", "NAME", 0.98),
            (100, 109, "T1165789Z", "NRIC", 1.0),
            (135, 162, "Meadowvale Secondary School", "SCHOOL", 1.0),
            (115, 125, "22/04/2011", "DOB", 1.0),
        ],
        "gliner_attr": [
            (248, 258, "shop theft", "ATTR:offence", 0.95),
        ],
    },
    "youth_gang": {
        "pack": "youth-offending",
        "text": "Write a referral letter to the school counsellor about this case, including relevant context from his social media activity.\n\nClient: Kai Ming Ong, NRIC T1132109C, DOB 14/12/2010, age 15, Northlight Secondary School, Sec 3. Address: Blk 220 Hougang Avenue 8 #11-067, Singapore 530220. Kai Ming was arrested for shop theft in Hougang on 5 Sep 2026 along with two older youths believed to be linked to a group called the '18 Tigers'. His Instagram handle is @kaiming_18t and he has posted photos with group symbols. Kai Ming says he wants to distance himself from the group and has asked for help finding a part-time job away from the area.",
        "presidio": [
            (134, 146, "Kai Ming Ong", "NAME", 0.85),
            (285, 293, "Kai Ming", "NAME", 0.85),
            (514, 522, "Kai Ming", "NAME", 0.85),
        ],
        "gliner": [
            (134, 146, "Kai Ming Ong", "NAME", 0.96),
            (514, 522, "Kai Ming", "NAME", 0.83),
            (285, 293, "Kai Ming", "NAME", 0.75),
            (153, 162, "T1132109C", "NRIC", 1.0),
            (188, 215, "Northlight Secondary School", "SCHOOL", 0.99),
            (168, 178, "14/12/2010", "DOB", 1.0),
        ],
        "gliner_attr": [
            (311, 321, "shop theft", "ATTR:offence", 0.91),
        ],
    },
    "youth_spent": {
        "pack": "youth-offending",
        "text": "Write a letter to a prospective employer supporting this young person's job application; his youth record is spent and should not be disclosed.\n\nClient: Marcus Tan Wei Jie, NRIC T1076543E, DOB 05/01/2009, age 17 (about to turn 18), formerly Hillview Secondary School. Address: Blk 88 Bedok North Street 4 #12-233, Singapore 460088. He was cautioned for theft at age 14 (2023); the matter was dealt with under a diversion and is spent under the Children and Young Persons Act. He has completed his N-levels and is applying for a warehouse assistant role at a logistics company. He has been in stable part-time work for eight months and has strong references from his CCA coach.",
        "presidio": [
            (153, 171, "Marcus Tan Wei Jie", "NAME", 0.85),
        ],
        "gliner": [
            (153, 171, "Marcus Tan Wei Jie", "NAME", 0.98),
            (178, 187, "T1076543E", "NRIC", 1.0),
            (241, 266, "Hillview Secondary School", "SCHOOL", 1.0),
            (558, 575, "logistics company", "EMPLOYER", 0.93),
            (20, 40, "prospective employer", "EMPLOYER", 0.53),
            (193, 203, "05/01/2009", "DOB", 1.0),
        ],
        "gliner_attr": [
            (444, 474, "Children and Young Persons Act", "ATTR:ppo", 0.71),
            (353, 358, "theft", "ATTR:offence", 0.74),
        ],
    },
    "coach_medication": {
        "pack": "disability",
        "text": "Draft an email to the hardware store manager, Mr Lim Chee Hock at Ace Hardware Tampines, introducing Rajesh for a trial shift and explaining what support he needs.\n\nClient Rajesh s/o Kumar, 31, NRIC S2345678D. Diagnosed with schizophrenia, stable on medication. Takes Risperidone 2mg at night, prescribed by Dr Amanda Wong, psychiatrist at the Institute of Mental Health. Wants to try a part-time role at a hardware store.",
        "presidio": [
            (49, 62, "Lim Chee Hock", "NAME", 0.85),
            (101, 107, "Rajesh", "NAME", 0.85),
            (172, 180, "Rajesh s", "NAME", 0.85),
            (311, 322, "Amanda Wong", "NAME", 0.85),
        ],
        "gliner": [
            (101, 107, "Rajesh", "NAME", 0.96),
            (172, 178, "Rajesh", "NAME", 0.96),
            (49, 62, "Lim Chee Hock", "NAME", 0.93),
            (311, 322, "Amanda Wong", "NAME", 0.86),
            (199, 208, "S2345678D", "NRIC", 1.0),
            (66, 87, "Ace Hardware Tampines", "EMPLOYER", 0.99),
            (344, 370, "Institute of Mental Health", "EMPLOYER", 0.99),
        ],
        "gliner_attr": [
            (225, 238, "schizophrenia", "ATTR:disability", 0.71),
        ],
    },
    "coach_handover": {
        "pack": "disability",
        "text": "Draft a handover note to my colleague Alicia, the other job coach on this case, covering Farah's trial shift at the cafe and what she needs from the team.\n\nCase note, 18 Sep 2026. Client Farah Binte Rahman, 26, NRIC S8812345D, lives in Tampines. Attends Sunbeam Day Activity Centre three days a week. Farah has a diagnosis of a developmental disability and is sensitive to loud noise. She needs written instructions rather than verbal ones and prefers a quiet corner during breaks.\n\nPlan: trial shift at Kopi Corner Cafe, Tampines Hub, on 22 Sep 2026, supervised by manager Mr Tan Wei Ming.",
        "presidio": [
            (38, 44, "Alicia", "NAME", 0.85),
            (89, 94, "Farah", "NAME", 0.85),
            (187, 205, "Farah Binte Rahman", "NAME", 0.85),
            (301, 306, "Farah", "NAME", 0.85),
            (574, 589, "Mr Tan Wei Ming", "NAME", 0.85),
        ],
        "gliner": [
            (187, 205, "Farah Binte Rahman", "NAME", 0.99),
            (38, 44, "Alicia", "NAME", 0.96),
            (574, 589, "Mr Tan Wei Ming", "NAME", 0.79),
            (89, 94, "Farah", "NAME", 0.71),
            (301, 306, "Farah", "NAME", 0.6),
            (216, 225, "S8812345D", "NRIC", 1.0),
            (236, 244, "Tampines", "ADDRESS", 0.63),
            (254, 281, "Sunbeam Day Activity Centre", "SCHOOL", 0.99),
            (504, 520, "Kopi Corner Cafe", "SCHOOL", 0.73),
        ],
        "gliner_attr": [
            (328, 352, "developmental disability", "ATTR:disability", 0.91),
        ],
    },
    "wsdm_dv": {
        "pack": "domestic-violence",
        "text": "Write a short referral letter to the intake officer at the crisis shelter. Give the family's current address on one line and say why the placement is urgent.\n\nContact note, 26 Sep 2026. Client Ms Tan Mei Ling, NRIC S9012345A, 31, hp 98765432, case ref FSC-2026-0919, living at Blk 730 Yishun Street 71 #12-334, Singapore 760730 with son Kaiden (6, Naval Base Primary School). She reports that her partner Marcus Lim Wei Jie slapped her on 20 Sep and has threatened to take Kaiden to his mother's flat in Sengkang. She denies that he has ever hit the child. No PPO yet; she is not ready to apply. She works as a cashier at FairPrice Northpoint. Assessment: escalating physical violence, child present, safety plan agreed (keep bag packed, neighbour at #12-336 aware). Plan: shelter referral today, follow-up call tomorrow.",
        "presidio": [
            (193, 208, "Ms Tan Mei Ling", "NAME", 0.85),
            (337, 343, "Kaiden", "NAME", 0.85),
            (405, 423, "Marcus Lim Wei Jie", "NAME", 0.85),
            (473, 479, "Kaiden", "NAME", 0.85),
        ],
        "gliner": [
            (405, 423, "Marcus Lim Wei Jie", "NAME", 0.99),
            (196, 208, "Tan Mei Ling", "NAME", 0.98),
            (337, 343, "Kaiden", "NAME", 0.97),
            (473, 479, "Kaiden", "NAME", 0.95),
            (215, 224, "S9012345A", "NRIC", 0.99),
            (233, 241, "98765432", "NRIC", 0.67),
            (348, 373, "Naval Base Primary School", "SCHOOL", 1.0),
            (59, 73, "crisis shelter", "FACILITY", 0.95),
            (622, 642, "FairPrice Northpoint", "EMPLOYER", 1.0),
            (252, 265, "FSC-2026-0919", "CASE_REF", 0.96),
            (439, 445, "20 Sep", "DOB", 0.97),
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
