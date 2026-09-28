"""Polarity regression suite for the attribute generalisers: a generalised phrase may lose
detail but must never assert something the note does not."""

import pytest

from socareguard.outbound.generalise import generalise_attribute

CASES = [
    # (key, rule, text, must_contain, must_not_contain)
    ("offence", "category", "Prev warning Feb for fighting", "prior police warning", "current"),
    (
        "offence",
        "category",
        "Danial says he did not know it was stolen",
        "disputes",
        "current matter",
    ),
    ("offence", "category", "the charge was withdrawn", "was withdrawn", "current"),
    (
        "offence",
        "category",
        "his cousin has a prior conviction for theft",
        "family member",
        "is the subject",
    ),
    (
        "offence",
        "category",
        "peer-influenced offence of shop theft",
        "property offence",
        "family member",
    ),
    (
        "offence",
        "category",
        "picked up for shop theft on 19 Aug",
        "current matter",
        "family member",
    ),
    ("offence", "category", "denies any involvement in the theft", "disputes", "current matter"),
    (
        "offence",
        "category",
        "He has no previous record and no charge has been brought",
        "no prior offence record",
        "prior record of",
    ),
    (
        "offence",
        "category",
        "Order: 21 months probation, curfew 10pm, 40 hours CSO for the shop theft",
        "21 months",
        "is the subject",
    ),
    ("offence", "category", "caught vaping at school", "vaping", "drug"),
    (
        "offence",
        "category",
        "low prior risk, peer-influenced offence",
        "current matter",
        "prior record",
    ),
    (
        "offence",
        "category",
        "No offending history reported by father",
        "no prior offence record",
        "prior record of",
    ),
    (
        "offence",
        "category",
        "He has never been in trouble with the law before",
        "no prior offence record",
        "prior record of",
    ),
    (
        "offence",
        "category",
        "his brother was charged with housebreaking",
        "family member",
        "is the subject",
    ),
    (
        "offence",
        "category",
        "Order: 21 months probation, curfew 10pm, 40 hours CSO for fighting at the mall",
        "21 months",
        "violenceing",
    ),
    ("capacity", "status_only", "Deputyship: none, capacity presumed", "presumed", "in question"),
    (
        "diagnosis",
        "category",
        "the supervisor said she did not sign up for a special needs case and wants her swapped",
        "swapped",
        "has a health condition",
    ),
    ("capacity", "status_only", "Mother is not her deputy", "presumed", "in question"),
    ("capacity", "status_only", "there is no deputyship order", "presumed", "in question"),
    ("capacity", "status_only", "A deputy was appointed under the MCA", "in question", "presumed"),
    (
        "capacity",
        "status_only",
        "she has capacity to make this decision",
        "has capacity",
        "in question",
    ),
    ("minor", "age_band", "Intake, 4 Sep 2026, Youth Court diversion", "is a minor", "aged"),
    ("minor", "age_band", "Amirul, 15, a minor", "15 to 17", "3 to 5"),
    ("minor", "age_band", "aged 16, under investigation", "15 to 17", "3 to 5"),
    ("ppo", "status_only", "A PPO application was filed on 26 Aug", "pending", "in place"),
    ("ppo", "status_only", "A PPO application in 2025 was withdrawn", "earlier", "decided against"),
    (
        "ppo",
        "status_only",
        "Expedited order in force until 26 Sep",
        "expedited",
        "protection order is in place",
    ),
    (
        "ppo",
        "status_only",
        "no expedited order has been applied for",
        "no protection order application",
        "in place",
    ),
    (
        "ppo",
        "status_only",
        "Assessment: ongoing risk given the phone monitoring and the pending PPO hearing on 3 Oct",
        "ongoing risk",
        "is pending",
    ),
    ("ppo", "status_only", "She declined to apply for a PPO", "decided against", "in place"),
    ("ppo", "status_only", "PPO granted last year", "in place", "pending"),
    (
        "diagnosis",
        "category",
        "diagnosis of moderate intellectual disability",
        "developmental disability",
        "offence",
    ),
    (
        "safety_plan",
        "redact",
        "Safety plan: keep the shelter address off forms",
        "withheld",
        "shelter",
    ),
]


@pytest.mark.parametrize("key,rule,text,must,must_not", CASES)
def test_polarity(key, rule, text, must, must_not):
    out = generalise_attribute(
        key, text, rule, "youth-offending" if key in ("offence", "minor") else "disability"
    )
    assert must in out, out
    assert must_not not in out, out


# A long clause keeps its sentence only when the phrase naming the condition, offence or order
# can be replaced whole, with its article and modifiers; the three sentences below came out
# ungrammatical before ("seated in a power a physical disability").
GRAMMAR = [
    (
        "disability",
        "category",
        "At time of visit I observed James seated in a power wheelchair near the front door",
        "At time of visit I observed James seated in a mobility aid near the front door",
    ),
    (
        "diagnosis",
        "category",
        (
            "Son has moderate intellectual disability and was diagnosed with autism spectrum disorder"
            " in childhood which affects his communication and self-care"
        ),
        (
            "Son has a developmental disability and was diagnosed with a developmental disability in"
            " childhood which affects his communication and self-care"
        ),
    ),
    (
        "ppo",
        "status_only",
        (
            "Wong Wan Ting is unsure whether to pursue a PPO and requested information about the"
            " process and its impact on her housing"
        ),
        (
            "Wong Wan Ting is unsure whether to pursue a protection order and requested information"
            " about the process and its impact on her housing"
        ),
    ),
    (
        "offence",
        "category",
        (
            "Was previously arrested in relation to a non-violent property offence and is on community"
            " supervision"
        ),
        "Was previously arrested in relation to a property offence and is on community supervision",
    ),
    (
        "offence",
        "category",
        (
            "I met with the client following a referral from the school regarding an alleged incident"
            " of shop theft"
        ),
        (
            "I met with the client following a referral from the school regarding an alleged incident"
            " of a property offence"
        ),
    ),
    (
        "ppo",
        "status_only",
        (
            "She has an active Personal Protection Order issued on 20 Jun 2026 which limits the"
            " partner's contact with her"
        ),
        "She has an active protection order issued which limits the partner's contact with her",
    ),
]


@pytest.mark.parametrize("key,rule,text,expected", GRAMMAR)
def test_long_clause_rewrite_is_grammatical(key, rule, text, expected):
    pack = "youth-offending" if key == "offence" else "disability"
    assert generalise_attribute(key, text, rule, pack) == expected


@pytest.mark.parametrize(
    "key,text,expected",
    [
        # "caught vaping" is a verb phrase: no noun phrase to replace, so the whole clause goes
        (
            "offence",
            "Was caught vaping on school premises and recorded as truant on several occasions",
            "is the subject of a current matter: a tobacco or vaping matter",
        ),
        # an adjective before a noun has no clean rewrite either
        (
            "disability",
            "Her son is an autistic boy who attends a special school near their flat every weekday",
            "has a developmental disability",
        ),
    ],
)
def test_long_clause_without_a_clean_rewrite_falls_back_to_the_statement(key, text, expected):
    pack = "youth-offending" if key == "offence" else "disability"
    assert generalise_attribute(key, text, "category", pack) == expected


# Round 3 (YOUTH-F3): the disposition of a matter is kept with its basis; a denial stays a denial.
DISPOSITIONS = [
    (
        (
            "The charge of shop theft against Aisyah was withdrawn by the prosecution on 15 Aug"
            " 2026 after CCTV footage showed she was not involved"
        ),
        ["a charge of a property offence was withdrawn by the prosecution", "not involved"],
        ["disputes", "allegation", "current matter", "no prior"],
    ),
    (
        "the charge of rioting was dropped for insufficient evidence",
        ["was dropped", "lack of evidence"],
        ["current matter", "disputes"],
    ),
    (
        "He was acquitted of the theft charge in March",
        ["acquitted of a charge of a property offence"],
        ["current matter", "prior record"],
    ),
    (
        "She was given a discharge amounting to an acquittal on the vandalism charge",
        ["discharge amounting to an acquittal"],
        ["current matter", "not amounting"],
    ),
    (
        "The fighting charge ended in a discharge not amounting to an acquittal",
        ["discharge not amounting to an acquittal"],
        ["current matter"],
    ),
    (
        "He was warned by the police for vaping at the void deck",
        ["warned by the police"],
        ["current matter", "withdrawn"],
    ),
    (
        "No further action was taken by the police on the shop theft report; he denies being there",
        ["closed with no further action", "denies involvement"],
        ["no prior offence record", "current matter"],
    ),
    (
        "Aisyah denies any involvement in the theft",
        ["allegation", "disputes"],
        ["withdrawn", "current matter"],
    ),
    (
        "his brother's charge for theft was dropped",
        ["family member"],
        ["the client"],
    ),
]


@pytest.mark.parametrize("text,must,must_not", DISPOSITIONS)
def test_offence_disposition_is_kept(text, must, must_not):
    got = generalise_attribute("offence", text, "category", "youth-offending")
    for m in must:
        assert m in got, (text, got)
    for m in must_not:
        assert m not in got, (text, got)
