"""Notes written in review round 2 (2026-09-28), with the Presidio and GLiNER2 hits recorded on them.

The sandbox runs both NER backends; the unit tests do not load them. ``use(monkeypatch, name)``
replays the recorded hits for that note, so a test sees the spans the reviewer's run saw. Messages
are the instruction and the note joined by a blank line, as the panel sends them."""

from __future__ import annotations

from socareguard.detect import backends
from socareguard.detect.sg import Hit

NOTES: dict[str, dict] = {
    "student_8e": {
        "pack": "domestic-violence",
        "text": "What should I do next?\n"
        "\n"
        "First home visit, 28 Sep 2026. Client: Mdm Farah Aljunied, 39, and her husband "
        "Ridzwan Aljunied, 42. Address: Blk 210 Bedok North Street 1 #09-45, Singapore "
        "460210. Son Danial Aljunied, 9, attends Damai Primary School, Primary 3.\n"
        "\n"
        "The family is three months behind on rent for their rental flat, with HDB arrears of "
        "about $1,800. Ridzwan lost his job as a delivery driver in July. Danial seems "
        "withdrawn in class and his teacher flagged that his uniform is often unwashed. The "
        "family has not applied for ComCare. Mdm Aljunied was tearful during the visit and "
        "said she does not know how to tell the children they might have to move.",
        "presidio": [
            (63, 81, "Mdm Farah Aljunied", "NAME", 0.85),
            (103, 119, "Ridzwan Aljunied", "NAME", 0.85),
            (193, 208, "Danial Aljunied", "NAME", 0.85),
            (354, 361, "Ridzwan", "NAME", 0.85),
            (405, 411, "Danial", "NAME", 0.85),
            (537, 549, "Mdm Aljunied", "NAME", 0.85),
        ],
        "gliner": [
            (103, 119, "Ridzwan Aljunied", "NAME", 1.0),
            (193, 208, "Danial Aljunied", "NAME", 0.99),
            (67, 81, "Farah Aljunied", "NAME", 0.99),
            (221, 252, "Damai Primary School, Primary 3", "SCHOOL", 0.99),
            (528, 535, "ComCare", "EMPLOYER", 0.64),
            (325, 328, "HDB", "EMPLOYER", 0.64),
        ],
        "gliner_attr": [(528, 535, "ComCare", "ATTR:ppo", 0.43)],
    },
    "student_9b": {
        "pack": "domestic-violence",
        "text": "Summarise this note for the case file.\n"
        "\n"
        "Home visit follow-up, 28 Sep 2026. Client: Mdm Farah Aljunied, 39. Recorded by "
        "student social worker, staff id SW-1042, under placement supervision of Mr Wong. Mdm "
        "Aljunied confirmed the arrears figure and said her husband has an interview next "
        "week.",
        "presidio": [
            (83, 101, "Mdm Farah Aljunied", "NAME", 0.85),
            (194, 198, "Wong", "NAME", 0.85),
            (200, 212, "Mdm Aljunied", "NAME", 0.85),
        ],
        "gliner": [(191, 198, "Mr Wong", "NAME", 0.96), (87, 101, "Farah Aljunied", "NAME", 0.89)],
        "gliner_attr": [],
    },
    "fsc_1_household": {
        "pack": "domestic-violence",
        "text": "Summarise this note and draft three next steps for the case file.\n"
        "\n"
        "Case summary, 28 Sep 2026. Client: Farhana binti Rosli, NRIC S8834211A, age 34, "
        "residing at Blk 118 Ang Mo Kio Avenue 4 #09-233, Singapore 560118. Household: "
        "husband Zulkifli bin Hassan (contact 91234567), children Amirah (10, P4 at Yishun "
        "Primary School) and Danish (7, P1 at Northview Primary School). Grandmother Rosnah "
        "binti Rosli, same surname as the client, lives with the family and helps with "
        "childcare.\n"
        "\n"
        "Presenting concern: Farhana reports her husband has been verbally abusive after "
        "losing his job in June 2026, and raised his hand at her once in August but did not "
        "strike her. She is considering moving to her sister's flat in Sengkang temporarily.\n"
        "\n"
        "Assessment: moderate risk, no protection order filed yet. Family is cooperative and "
        "open to counselling.",
        "presidio": [
            (102, 121, "Farhana binti Rosli", "NAME", 0.85),
            (233, 252, "Zulkifli bin Hassan", "NAME", 0.85),
            (282, 288, "Amirah", "NAME", 0.85),
            (383, 401, "Rosnah binti Rosli", "NAME", 0.85),
            (500, 507, "Farhana", "NAME", 0.85),
        ],
        "gliner": [
            (233, 252, "Zulkifli bin Hassan", "NAME", 0.99),
            (102, 121, "Farhana binti Rosli", "NAME", 0.98),
            (383, 401, "Rosnah binti Rosli", "NAME", 0.97),
            (282, 288, "Amirah", "NAME", 0.9),
            (327, 333, "Danish", "NAME", 0.85),
            (128, 137, "S8834211A", "NRIC", 0.99),
            (262, 270, "91234567", "PHONE", 0.99),
            (344, 368, "Northview Primary School", "SCHOOL", 1.0),
            (300, 321, "Yishun Primary School", "SCHOOL", 1.0),
        ],
        "gliner_attr": [
            (755, 784, "no protection order filed yet", "ATTR:ppo", 0.62),
            (740, 753, "moderate risk", "ATTR:capacity", 0.42),
        ],
    },
    "fsc_3_typo": {
        "pack": "domestic-violence",
        "text": "Draft a short update for the supervisor on this case.\n"
        "\n"
        "Review note, 22 Sep 2026. Client: Suriati binti Yusof, NRIC S7712045B, age 41, Blk "
        "335 Bukit Batok Street 32 #06-14, Singapore 650335. Husband Rahim bin Salim "
        "currently has a Personal Protection Order application filed 15 Sep 2026, next "
        "mention 10 Oct 2026.\n"
        "\n"
        "Suriaty called today to say she is coping better and attended two counselling "
        "sessions. She is staying with her mother in Woodlands for now.\n"
        "\n"
        "Plan: continue weekly check-in calls, review PPO status after the mention date.",
        "presidio": [
            (89, 108, "Suriati binti Yusof", "NAME", 0.85),
            (198, 213, "Rahim bin Salim", "NAME", 0.85),
            (314, 321, "Suriaty", "NAME", 0.85),
        ],
        "gliner": [
            (198, 213, "Rahim bin Salim", "NAME", 0.99),
            (89, 108, "Suriati binti Yusof", "NAME", 0.99),
            (115, 124, "S7712045B", "NRIC", 1.0),
        ],
        "gliner_attr": [(230, 267, "Personal Protection Order application", "ATTR:ppo", 0.45)],
    },
    "fsc_5_arrears": {
        "pack": "domestic-violence",
        "text": "Summarise the financial and contact history in this note for the case file.\n"
        "\n"
        "Review note, 25 Sep 2026. Client: Nur Aisyah binti Zainal, NRIC S9045671C, age 29, "
        "Blk 771 Yishun Ring Road #04-19, Singapore 760771. Contacts: 3 Aug 2026 (home "
        "visit), 17 Aug 2026 (phone), 4 Sep 2026 (office appointment), 21 Sep 2026 (phone).\n"
        "\n"
        "Client received ComCare short-to-medium term assistance of $650 per month starting "
        "July 2026. Rental arrears at time of application: $1,240. Husband Johari bin Salleh "
        "has not contributed to household expenses since separation in June 2026.\n"
        "\n"
        "Assessment: financial stability improving with ComCare support, arrears reduced to "
        "$310 as of last check.",
        "presidio": [
            (111, 127, "Nur Aisyah binti", "NAME", 0.85),
            (471, 488, "Johari bin Salleh", "NAME", 0.85),
        ],
        "gliner": [
            (471, 488, "Johari bin Salleh", "NAME", 0.99),
            (111, 134, "Nur Aisyah binti Zainal", "NAME", 0.99),
            (141, 150, "S9045671C", "NRIC", 1.0),
            (246, 257, "17 Aug 2026", "PHONE", 0.99),
            (221, 231, "3 Aug 2026", "PHONE", 0.97),
            (300, 311, "21 Sep 2026", "PHONE", 0.93),
            (338, 345, "ComCare", "EMPLOYER", 0.8),
            (610, 617, "ComCare", "EMPLOYER", 0.8),
        ],
        "gliner_attr": [],
    },
    "fsc_6_short": {
        "pack": "youth-offending",
        "text": "Summarise this note.\n"
        "\n"
        "Client Aisha Lim, 14, caught shoplifting at Jurong Point on 26 Sep 2026. Referred by "
        "mall security to school, Sec 2 at Fern Green Secondary School.",
        "presidio": [(29, 38, "Aisha Lim", "NAME", 0.85)],
        "gliner": [
            (29, 38, "Aisha Lim", "NAME", 0.99),
            (141, 168, "Fern Green Secondary School", "SCHOOL", 0.99),
            (107, 120, "mall security", "EMPLOYER", 0.77),
            (40, 42, "14", "DOB", 0.56),
        ],
        "gliner_attr": [(51, 62, "shoplifting", "ATTR:offence", 0.77)],
    },
    "msw_1": {
        "pack": "disability",
        "text": "Summarise this discharge planning note for the case file.\n"
        "\n"
        "MRN: H0234567. Ward 12B, Bed 04. Patient Ms Chua Mei Ling (NRIC S8812345A), 34, "
        "admitted for C5 spinal cord injury sustained in a fall (ASIA B, T2 level). Under the "
        "care of Dr Tan Wei Ming, Consultant, Department of Rehabilitation Medicine. "
        "Discharge planning in progress; caregiver Mdm Lee Siok Hoon (client's mother) has "
        "agreed to attend caregiver training before discharge. Plan: refer to SG Enable for "
        "wheelchair funding and arrange home-based physiotherapy follow-up.",
        "presidio": [
            (74, 82, "Ward 12B", "NAME", 0.85),
            (100, 116, "Ms Chua Mei Ling", "NAME", 0.85),
            (235, 247, "Tan Wei Ming", "NAME", 0.85),
            (342, 359, "Mdm Lee Siok Hoon", "NAME", 0.85),
        ],
        "gliner": [
            (346, 359, "Lee Siok Hoon", "NAME", 0.98),
            (103, 116, "Chua Mei Ling", "NAME", 0.98),
            (235, 247, "Tan Wei Ming", "NAME", 0.95),
            (123, 132, "S8812345A", "NRIC", 0.98),
            (261, 298, "Department of Rehabilitation Medicine", "EMPLOYER", 0.95),
            (451, 460, "SG Enable", "EMPLOYER", 0.55),
            (64, 72, "H0234567", "CASE_REF", 0.96),
        ],
        "gliner_attr": [
            (152, 173, "C5 spinal cord injury", "ATTR:disability", 0.68),
            (451, 483, "SG Enable for wheelchair funding", "ATTR:safety_plan", 0.43),
            (496, 530, "home-based physiotherapy follow-up", "ATTR:safety_plan", 0.4),
        ],
    },
    "msw_2": {
        "pack": "disability",
        "text": "Draft a summary of this financial assessment for the medical social work case file.\n"
        "\n"
        "Financial assessment for MediFund application. Household monthly income $1,850. "
        "Means-tested assessment recommends 50% subsidy on the outstanding hospital bill. "
        "Client's CPF Medisave balance is $12,340.50, insufficient to cover the balance bill. "
        "Family has also applied for ComCare short-to-medium term assistance of $400 per "
        "month, pending MediFund approval. Client is Mr Kumar s/o Raman (NRIC S7723456B).",
        "presidio": [(458, 465, "Kumar s", "NAME", 0.85)],
        "gliner": [(480, 489, "S7723456B", "NRIC", 0.99)],
        "gliner_attr": [],
    },
    "msw_3": {
        "pack": "disability",
        "text": "Draft a reminder note for the client's caregiver about the upcoming appointment.\n"
        "\n"
        "Next appointment: 14 Oct 2026, 10am, orthopaedic clinic, Tan Tock Seng Hospital, "
        "Level 3. Please remind the client's caregiver, Mdm Lee Siok Hoon, one day before the "
        "appointment. Client to bring walking aid and MediSave card.",
        "presidio": [(210, 227, "Mdm Lee Siok Hoon", "NAME", 0.85)],
        "gliner": [(210, 227, "Mdm Lee Siok Hoon", "NAME", 0.96)],
        "gliner_attr": [],
    },
    "msw_4": {
        "pack": "disability",
        "text": "Summarise this note for the case file, including where the client was referred "
        "from.\n"
        "\n"
        "Client was referred from Tan Tock Seng Hospital's medical social work department "
        "after an inpatient stay for a stroke with resulting left hemiparesis. Continuing "
        "care will be coordinated with Tan Tock Seng Hospital's rehabilitation team for "
        "outpatient follow-up.",
        "presidio": [],
        "gliner": [
            (86, 92, "Client", "NAME", 0.86),
            (59, 65, "client", "NAME", 0.85),
            (278, 322, "Tan Tock Seng Hospital's rehabilitation team", "EMPLOYER", 0.62),
        ],
        "gliner_attr": [
            (219, 235, "left hemiparesis", "ATTR:disability", 0.93),
            (197, 203, "stroke", "ATTR:disability", 0.79),
        ],
    },
    "msw_5": {
        "pack": "disability",
        "text": "Draft a case summary noting the capacity assessment and discharge plan.\n"
        "\n"
        "Client Mdm Fatimah binte Ismail (NRIC S6634567C), 78, was assessed by the hospital's "
        "psychiatrist as lacking mental capacity to make decisions about her discharge "
        "placement, following a stroke with cognitive impairment. Her son, Mr Ahmad bin "
        "Ismail, has been appointed as deputy under the Mental Capacity Act and has consented "
        "to nursing home placement on her behalf. Discharge plan: transfer to St Joseph's "
        "Home for continuing care, pending bed availability.",
        "presidio": [
            (80, 91, "Mdm Fatimah", "NAME", 0.85),
            (98, 104, "Ismail", "NAME", 0.85),
            (305, 321, "Ahmad bin Ismail", "NAME", 0.85),
        ],
        "gliner": [
            (84, 104, "Fatimah binte Ismail", "NAME", 0.98),
            (305, 321, "Ahmad bin Ismail", "NAME", 0.97),
            (111, 120, "S6634567C", "NRIC", 0.98),
            (469, 485, "St Joseph's Home", "FACILITY", 0.9),
            (403, 415, "nursing home", "FACILITY", 0.57),
        ],
        "gliner_attr": [
            (271, 291, "cognitive impairment", "ATTR:disability", 0.93),
            (259, 265, "stroke", "ATTR:disability", 0.9),
            (362, 381, "Mental Capacity Act", "ATTR:ppo", 0.58),
        ],
    },
    "msw_6": {
        "pack": "domestic-violence",
        "text": "Summarise this ward note for the case file.\n"
        "\n"
        "MRN: H0345678. Ward 6A, Bed 12. Patient Mr Lim Ah Kow, 68, admitted for "
        "hypoglycaemia and a fall at home. History of type 2 diabetes mellitus and "
        "hypertension. Under the care of Dr Sarah Ng, Endocrinology. Discharge plan: home "
        "with meals-on-wheels support and diabetic nurse follow-up. No caregiver concerns "
        "noted.",
        "presidio": [
            (60, 67, "Ward 6A", "NAME", 0.85),
            (88, 98, "Lim Ah Kow", "NAME", 0.85),
            (226, 234, "Sarah Ng", "NAME", 0.85),
        ],
        "gliner": [
            (88, 98, "Lim Ah Kow", "NAME", 0.96),
            (223, 234, "Dr Sarah Ng", "NAME", 0.83),
            (50, 58, "H0345678", "CASE_REF", 0.96),
        ],
        "gliner_attr": [
            (191, 203, "hypertension", "ATTR:disability", 0.64),
            (162, 186, "type 2 diabetes mellitus", "ATTR:disability", 0.54),
            (117, 130, "hypoglycaemia", "ATTR:disability", 0.45),
            (305, 329, "diabetic nurse follow-up", "ATTR:safety_plan", 0.54),
            (267, 300, "home with meals-on-wheels support", "ATTR:safety_plan", 0.43),
        ],
    },
    "wsdm_a_dv": {
        "pack": "domestic-violence",
        "text": "Summarise this home visit for my own case record and list two next steps.\n"
        "\n"
        "Home visit, 3 Sep 2026. Client Mdm Siti Nurhaliza binti Rahman, NRIC S8123456C, 38, "
        "case ref FSC-2026-0412, Blk 512 Bedok North Street 3 #07-119, Singapore 460512, hp "
        "91234567. Two children: Aisyah (9, Damai Primary School) and Irfan (5). Siti said "
        "her husband Razak bin Osman 'always scold until I cannot tahan lah, but he never hit "
        "me one'. She denies any physical violence and has not applied for a PPO. Neighbour "
        "reported shouting last week. Siti works part-time at a bakery in Tampines. "
        "Assessment: emotional abuse indicators present, no disclosed physical violence, "
        "client not ready for shelter. Plan: safety planning, follow up in two weeks.",
        "presidio": [
            (106, 124, "Mdm Siti Nurhaliza", "NAME", 0.85),
            (125, 137, "binti Rahman", "NAME", 0.85),
            (266, 272, "Aisyah", "NAME", 0.85),
            (303, 308, "Irfan", "NAME", 0.85),
            (314, 318, "Siti", "NAME", 0.85),
            (336, 353, "Razak bin Osman '", "NAME", 0.85),
            (521, 525, "Siti", "NAME", 0.85),
        ],
        "gliner": [
            (336, 351, "Razak bin Osman", "NAME", 0.99),
            (110, 137, "Siti Nurhaliza binti Rahman", "NAME", 0.98),
            (266, 272, "Aisyah", "NAME", 0.97),
            (303, 308, "Irfan", "NAME", 0.96),
            (144, 153, "S8123456C", "NRIC", 1.0),
            (242, 250, "91234567", "PHONE", 0.95),
            (277, 297, "Damai Primary School", "SCHOOL", 1.0),
            (547, 553, "bakery", "EMPLOYER", 0.82),
            (168, 181, "FSC-2026-0412", "CASE_REF", 0.97),
        ],
        "gliner_attr": [
            (477, 480, "PPO", "ATTR:ppo", 0.57),
            (700, 722, "follow up in two weeks", "ATTR:safety_plan", 0.69),
            (683, 698, "safety planning", "ATTR:safety_plan", 0.43),
        ],
    },
    "wsdm_c_youth": {
        "pack": "youth-offending",
        "text": "Draft a short letter to the principal of Bukit Merah Secondary School asking the "
        "school to support a supervised after-school study arrangement for my client.\n"
        "\n"
        "Probation review, 5 Sep 2026. Client Muhammad Haziq bin Ismail, NRIC T0712345J, 15, "
        "Sec 3 at Bukit Merah Secondary School, lives at Blk 24 Jalan Membina #11-45 with "
        "mother Mdm Rosnah bte Ahmad (hp 81234567). Youth Court ref YC/2026/0771, probation "
        "order 12 months for shop theft; no further offending since. He denies any drug use "
        "and urine tests have been negative. Haziq wants to rejoin the school football CCA. "
        "Plan: liaise with school on study support; next review 3 Oct.",
        "presidio": [
            (196, 221, "Muhammad Haziq bin Ismail", "NAME", 0.85),
            (298, 311, "Jalan Membina", "NAME", 0.85),
            (331, 351, "Mdm Rosnah bte Ahmad", "NAME", 0.85),
            (383, 395, "YC/2026/0771", "NAME", 0.85),
        ],
        "gliner": [
            (196, 221, "Muhammad Haziq bin Ismail", "NAME", 0.99),
            (331, 351, "Mdm Rosnah bte Ahmad", "NAME", 0.98),
            (228, 237, "T0712345J", "NRIC", 0.99),
            (356, 364, "81234567", "PHONE", 0.99),
            (291, 318, "Blk 24 Jalan Membina #11-45", "ADDRESS", 0.84),
            (41, 69, "Bukit Merah Secondary School", "SCHOOL", 1.0),
            (252, 280, "Bukit Merah Secondary School", "SCHOOL", 1.0),
            (383, 395, "YC/2026/0771", "CASE_REF", 0.98),
        ],
        "gliner_attr": [(427, 437, "shop theft", "ATTR:offence", 0.87)],
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
    """Replay the recorded NER hits for note ``name``; returns the note (pack and text)."""
    monkeypatch.setattr(backends, "presidio_hits", _hits(name, "presidio", "presidio.PERSON"))
    monkeypatch.setattr(backends, "gliner_hits", _hits(name, "gliner", "gliner"))
    monkeypatch.setattr(
        backends, "gliner_attribute_hits", _hits(name, "gliner_attr", "gliner.attr")
    )
    monkeypatch.setattr(backends, "gliner_backend_name", lambda: "recorded")
    return NOTES[name]
