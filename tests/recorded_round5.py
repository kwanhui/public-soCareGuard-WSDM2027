"""Notes written in review round 5 (2026-09-28), with the Presidio and GLiNER2 hits recorded on them.

Recorded by running both NER backends on each message as the proxy sends it (the instruction and
the note joined by a blank line). ``use(monkeypatch, name)`` replays the recorded hits, so a test
sees the spans the reviewer's run saw without loading the models. The disability case manager's
notes and the meta-reviewer's note are verbatim from the round-5 review. Where a report elides
part of a note (the gang note, the employer letter, the age-band note), the elided identifiers are
invented to the same shape. The DPO's URL note is rebuilt from the outbound text and its spans.
One note is a control: an internal note that refers to the young person by initials."""

from __future__ import annotations

from socareguard.detect import backends
from socareguard.detect.sg import Hit

NOTES: dict[str, dict] = {
    "dcm_consent": {
        "pack": "disability",
        "text": "Draft a note for the case file recording consent for the day activity centre placement.\n\nClient Mr Faizal bin Rahman, 36, has a moderate intellectual disability. No capacity assessment has been done and no deputy or donee has been appointed. His mother, Mdm Zainab, signed the consent form on his behalf for his placement at the day activity centre, as she always has. Mr Faizal nodded when asked if he wanted to go.",
        "presidio": [
            (99, 116, "Faizal bin Rahman", "NAME", 0.85),
            (254, 264, "Mdm Zainab", "NAME", 0.85),
            (372, 378, "Faizal", "NAME", 0.85),
        ],
        "gliner": [
            (99, 116, "Faizal bin Rahman", "NAME", 0.94),
            (254, 264, "Mdm Zainab", "NAME", 0.87),
            (57, 76, "day activity centre", "FACILITY", 0.53),
            (329, 348, "day activity centre", "FACILITY", 0.52),
            (329, 348, "day activity centre", "EMPLOYER", 0.78),
            (57, 76, "day activity centre", "EMPLOYER", 0.73),
        ],
        "gliner_attr": [
            (128, 160, "moderate intellectual disability", "ATTR:disability", 0.53),
        ],
    },
    "dcm_capacity": {
        "pack": "disability",
        "text": "Draft a capacity assessment note for the case file.\n\nCapacity assessment for Mdm Noraini binte Yusof, 58. Following a capacity assessment on 12 Sep 2026, Mdm Noraini has capacity to decide on her day-to-day activities and where she wants to spend her free time. However, the same assessment found she lacks capacity to manage her financial affairs and property matters, due to short-term memory impairment. No deputy has yet been appointed for the financial decisions; an application is being prepared.",
        "presidio": [
            (77, 88, "Mdm Noraini", "NAME", 0.85),
            (89, 100, "binte Yusof", "NAME", 0.85),
            (154, 165, "Mdm Noraini", "NAME", 0.85),
        ],
        "gliner": [
            (77, 100, "Mdm Noraini binte Yusof", "NAME", 0.82),
            (154, 165, "Mdm Noraini", "NAME", 0.77),
        ],
        "gliner_attr": [
            (377, 405, "short-term memory impairment", "ATTR:disability", 0.97),
        ],
    },
    "dcm_careplan": {
        "pack": "disability",
        "text": "Draft a care plan review summary for the case file, noting the current supports and the deputy arrangement.\n\nClient Ms Tan Wei Ling, 42, NRIC S8234567A. Diagnosed with moderate intellectual disability and epilepsy. Currently on Sodium Valproate 500mg twice daily for seizure control, prescribed by Dr Lionel Koh, neurologist. Attends Sunshine Day Activity Centre three days a week for vocational training. Primary caregiver is her sister, Ms Tan Wei Hui, who assists with daily living and medication reminders. Her brother, Mr Tan Jun Wei, has been appointed as her deputy for property and financial affairs by the Family Court under the Mental Capacity Act. Plan: continue day activity centre placement, review medication compliance at next visit, liaise with deputy on respite funding application.",
        "presidio": [
            (116, 131, "Ms Tan Wei Ling", "NAME", 0.85),
            (301, 311, "Lionel Koh", "NAME", 0.85),
            (326, 346, "Attends Sunshine Day", "NAME", 0.85),
            (439, 453, "Ms Tan Wei Hui", "NAME", 0.85),
            (527, 538, "Tan Jun Wei", "NAME", 0.85),
        ],
        "gliner": [
            (119, 131, "Tan Wei Ling", "NAME", 0.95),
            (442, 453, "Tan Wei Hui", "NAME", 0.92),
            (524, 538, "Mr Tan Jun Wei", "NAME", 0.91),
            (298, 311, "Dr Lionel Koh", "NAME", 0.7),
            (142, 151, "S8234567A", "NRIC", 0.98),
            (334, 362, "Sunshine Day Activity Centre", "FACILITY", 0.97),
            (615, 627, "Family Court", "EMPLOYER", 0.93),
        ],
        "gliner_attr": [
            (205, 213, "epilepsy", "ATTR:disability", 0.97),
            (168, 200, "moderate intellectual disability", "ATTR:disability", 0.76),
            (638, 657, "Mental Capacity Act", "ATTR:ppo", 0.72),
            (638, 657, "Mental Capacity Act", "ATTR:capacity", 0.4),
        ],
    },
    "dcm_ownwords": {
        "pack": "disability",
        "text": "Draft a case note recording the client's own account from today's visit.\n\nHome visit with Mr Alvin Teo, 24, who has a physical disability following a motorbike accident. When asked how he was coping, he said: \"I know I'm just a burden to my family now, I can't even bathe myself, I'm useless like this.\" He also said he wants to go back to his warehouse job once his leg heals.",
        "presidio": [
            (93, 102, "Alvin Teo", "NAME", 0.85),
        ],
        "gliner": [
            (93, 102, "Alvin Teo", "NAME", 0.98),
            (344, 357, "warehouse job", "EMPLOYER", 0.75),
        ],
        "gliner_attr": [
            (118, 137, "physical disability", "ATTR:disability", 0.78),
            (367, 376, "leg heals", "ATTR:disability", 0.46),
        ],
    },
    "dpo_url": {
        "pack": "disability",
        "text": "Draft a note for an employer about the client support needs.\n\nClient John Lim, date of birth 14 March 1998, has an online support group profile at https://facebook.com/johnlim1998 where he discusses his experience with autism.",
        "presidio": [
            (69, 77, "John Lim", "NAME", 0.85),
        ],
        "gliner": [
            (69, 77, "John Lim", "NAME", 0.99),
            (20, 28, "employer", "EMPLOYER", 0.61),
            (93, 106, "14 March 1998", "DOB", 1.0),
        ],
        "gliner_attr": [
            (219, 225, "autism", "ATTR:disability", 0.98),
        ],
    },
    "wsdm_dv": {
        "pack": "domestic-violence",
        "text": "Write a short letter to the school counsellor at Dhanush's school asking for support with his sleep and attention in class. Do not share more than the school needs.\n\nHome visit, 27 Sep 2026. Client Mdm Kavitha d/o Rajendran, NRIC S 8765432 F, 34, hp 8123 4567, case ref FSC-2026-1188, Blk 214 Serangoon Avenue 4 #09-233, Singapore 550214. Two children: Dhanush (8, Zhonghua Primary School) and Meera (3). Kavitha's husband Suresh s/o Muthu drinks after work and 'talk very loud one, but he never touch me or the kids'. She denies any physical violence and there is no PPO. Dhanush's teacher called about him falling asleep in class. Kavitha attends Serangoon Polyclinic for her anxiety and takes sertraline 50mg. She works part-time at a hawker stall in Toa Payoh. Assessment: verbal aggression by husband, no physical violence disclosed, children's sleep disrupted; client not seeking shelter. Plan: sleep routine for Dhanush, speak to school counsellor, review in two weeks.",
        "presidio": [
            (49, 56, "Dhanush", "NAME", 0.85),
            (198, 209, "Mdm Kavitha", "NAME", 0.85),
            (353, 360, "Dhanush", "NAME", 0.85),
            (394, 399, "Meera", "NAME", 0.85),
            (405, 412, "Kavitha", "NAME", 0.85),
            (423, 439, "Suresh s/o Muthu", "NAME", 0.85),
            (573, 580, "Dhanush", "NAME", 0.85),
            (633, 640, "Kavitha", "NAME", 0.85),
            (649, 669, "Serangoon Polyclinic", "NAME", 0.85),
            (754, 763, "Toa Payoh", "NAME", 0.85),
            (919, 926, "Dhanush", "NAME", 0.85),
        ],
        "gliner": [
            (49, 56, "Dhanush", "NAME", 0.99),
            (353, 360, "Dhanush", "NAME", 0.99),
            (573, 580, "Dhanush", "NAME", 0.98),
            (919, 926, "Dhanush", "NAME", 0.98),
            (394, 399, "Meera", "NAME", 0.97),
            (202, 209, "Kavitha", "NAME", 0.97),
            (423, 429, "Suresh", "NAME", 0.96),
            (405, 412, "Kavitha", "NAME", 0.92),
            (633, 640, "Kavitha", "NAME", 0.92),
            (214, 223, "Rajendran", "NAME", 0.54),
            (230, 241, "S 8765432 F", "NRIC", 0.99),
            (365, 388, "Zhonghua Primary School", "SCHOOL", 0.99),
            (649, 669, "Serangoon Polyclinic", "SCHOOL", 0.86),
            (649, 669, "Serangoon Polyclinic", "FACILITY", 0.93),
            (738, 750, "hawker stall", "EMPLOYER", 0.62),
            (434, 439, "Muthu", "EMPLOYER", 0.55),
            (270, 283, "FSC-2026-1188", "CASE_REF", 0.95),
        ],
        "gliner_attr": [
            (568, 571, "PPO", "ATTR:ppo", 0.44),
            (956, 975, "review in two weeks", "ATTR:safety_plan", 0.42),
        ],
    },
    "youth_initials": {
        "pack": "youth-offending",
        "text": "Write a letter to the school's discipline master about this case, referring to the young person only by initials to protect identity.\n\nClient known here as F.B., age 15, a probation client at Fernvale Secondary School, Sec 3. F.B. was cautioned for shop theft on 5 Aug 2026 as a diversion outcome and has since completed 20 hours of community service without incident. F.B.'s form teacher has raised concern about recent lateness. Requesting the school's support to monitor attendance without disclosing the offence to classmates.",
        "presidio": [
            (156, 160, "F.B.", "NAME", 0.85),
            (226, 230, "F.B.", "NAME", 0.85),
            (369, 373, "F.B.", "NAME", 0.85),
        ],
        "gliner": [
            (226, 230, "F.B.", "NAME", 1.0),
            (369, 373, "F.B.", "NAME", 1.0),
            (156, 160, "F.B.", "NAME", 1.0),
            (192, 217, "Fernvale Secondary School", "SCHOOL", 0.99),
        ],
        "gliner_attr": [
            (249, 259, "shop theft", "ATTR:offence", 0.97),
        ],
    },
    "youth_initials_internal": {
        "pack": "youth-offending",
        "text": "Write a note for my own case file on this week's check-in.\n\nClient known here as F.B., age 15, Sec 3. F.B. was cautioned for shop theft on 5 Aug 2026 as a diversion outcome and has since completed 20 hours of community service without incident. Attendance has improved this week and F.B. says the mentoring sessions help.",
        "presidio": [
            (81, 85, "F.B.", "NAME", 0.85),
            (102, 106, "F.B.", "NAME", 0.85),
            (283, 287, "F.B.", "NAME", 0.85),
        ],
        "gliner": [
            (102, 106, "F.B.", "NAME", 1.0),
            (283, 287, "F.B.", "NAME", 1.0),
            (81, 85, "F.B.", "NAME", 0.99),
        ],
        "gliner_attr": [
            (125, 135, "shop theft", "ATTR:offence", 0.95),
        ],
    },
    "youth_gang": {
        "pack": "youth-offending",
        "text": "Write a referral letter to the school counsellor about this case, including relevant context from his peer associations.\n\nClient: Danial Bin Rosli, NRIC T1054321H, DOB 14/05/2010, age 16, Yishun Secondary School, Sec 3. Address: Blk 325 Yishun Ring Road #05-142, Singapore 760325. Danial was arrested for vandalism in Yishun on 3 Sep 2026 with two members of a group called the 'Red Eagles'. Officers found spray cans linked to Red Eagles tags in his bag. Danial says Red Eagles members recruited him after school and he wants to leave the group. His mother is worried Red Eagles will retaliate if he stops attending their gatherings.",
        "presidio": [
            (130, 146, "Danial Bin Rosli", "NAME", 0.85),
            (281, 287, "Danial", "NAME", 0.85),
            (318, 324, "Yishun", "NAME", 0.85),
            (456, 462, "Danial", "NAME", 0.85),
        ],
        "gliner": [
            (130, 146, "Danial Bin Rosli", "NAME", 0.98),
            (153, 162, "T1054321H", "NRIC", 1.0),
            (188, 211, "Yishun Secondary School", "SCHOOL", 1.0),
            (168, 178, "14/05/2010", "DOB", 1.0),
        ],
        "gliner_attr": [
            (305, 314, "vandalism", "ATTR:offence", 0.83),
        ],
    },
    "youth_employer": {
        "pack": "youth-offending",
        "text": "Write a letter to his employer's HR department confirming his probation order status, now that he has turned 18.\n\nClient: Wei Jie Tan, NRIC T0812345C, DOB 02/08/2007, now age 18 (turned 18 last month), formerly Bedok Green Secondary School. Address: Blk 412 Bedok North Avenue 2 #06-221, Singapore 460412. Wei Jie was placed on a probation order at age 16 for shop theft; 3 months of community service remain. He has started full-time work at a warehouse and his employer's HR department has asked for written confirmation of his current probation status.",
        "presidio": [
            (122, 133, "Wei Jie Tan", "NAME", 0.85),
            (306, 313, "Wei Jie", "NAME", 0.85),
        ],
        "gliner": [
            (122, 133, "Wei Jie Tan", "NAME", 0.96),
            (140, 149, "T0812345C", "NRIC", 1.0),
            (211, 239, "Bedok Green Secondary School", "SCHOOL", 1.0),
            (463, 487, "employer's HR department", "EMPLOYER", 0.72),
            (22, 46, "employer's HR department", "EMPLOYER", 0.62),
            (155, 165, "02/08/2007", "DOB", 1.0),
        ],
        "gliner_attr": [
            (330, 345, "probation order", "ATTR:ppo", 0.65),
            (62, 77, "probation order", "ATTR:ppo", 0.64),
            (360, 370, "shop theft", "ATTR:offence", 0.95),
            (384, 401, "community service", "ATTR:offence", 0.48),
        ],
    },
    "youth_charge": {
        "pack": "youth-offending",
        "text": 'Write a note for my own case file, quoting the charge sheet exactly for the record.\n\nClient: Farhan Bin Zulkifli, NRIC T1176543J, DOB 21/06/2011, age 14, Sec 2, Yio Chu Kang Secondary School. Address: Blk 501 Ang Mo Kio Avenue 5 #04-210, Singapore 560501. The charge sheet reads: "The offender did commit theft in dwelling under section 380 of the Penal Code on or about 4 Sep 2026 at Blk 501 Ang Mo Kio Avenue 5." Farhan has been cooperative since the charge was laid and attends all scheduled check-ins.',
        "presidio": [
            (93, 112, "Farhan Bin Zulkifli", "NAME", 0.85),
            (161, 190, "Yio Chu Kang Secondary School", "NAME", 0.85),
            (415, 421, "Farhan", "NAME", 0.85),
        ],
        "gliner": [
            (93, 112, "Farhan Bin Zulkifli", "NAME", 0.98),
            (119, 128, "T1176543J", "NRIC", 1.0),
            (161, 190, "Yio Chu Kang Secondary School", "SCHOOL", 1.0),
            (134, 144, "21/06/2011", "DOB", 1.0),
            (371, 381, "4 Sep 2026", "DOB", 0.83),
        ],
        "gliner_attr": [
            (305, 322, "theft in dwelling", "ATTR:offence", 0.71),
        ],
    },
    "uiux_band": {
        "pack": "youth-offending",
        "text": "Write a note for my own case file summarising the young person's compliance with the programme; use the term the young person throughout, exactly as written, and repeat the medication line exactly as given.\n\nClient: Hafiz bin Rosman, NRIC T2205511B, DOB 12 Jun 2010, age 15 to 17, Sec 3 at a neighbourhood secondary school. Address: Blk 23 Circuit Road #04-117, Singapore 370023. Hafiz was convicted of shop theft on 2 Jul 2026 and placed on a probation order with community service. He is currently prescribed Risperidone 1mg nightly for sleep, reviewed by the clinic. He has completed 20 of 60 hours and attends all sessions on time. His mentor reports good engagement and no new incidents.",
        "presidio": [
            (216, 232, "Hafiz bin Rosman", "NAME", 0.85),
            (380, 385, "Hafiz", "NAME", 0.85),
        ],
        "gliner": [
            (216, 232, "Hafiz bin Rosman", "NAME", 0.96),
            (239, 248, "T2205511B", "NRIC", 1.0),
            (292, 322, "neighbourhood secondary school", "SCHOOL", 0.85),
            (465, 482, "community service", "EMPLOYER", 0.57),
            (254, 265, "12 Jun 2010", "DOB", 1.0),
            (417, 427, "2 Jul 2026", "DOB", 0.54),
        ],
        "gliner_attr": [
            (444, 459, "probation order", "ATTR:ppo", 0.64),
            (403, 413, "shop theft", "ATTR:offence", 0.96),
        ],
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
