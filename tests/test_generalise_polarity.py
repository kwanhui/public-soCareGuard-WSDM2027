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
    ("offence", "category", "the charge was withdrawn", "closed", "current"),
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
