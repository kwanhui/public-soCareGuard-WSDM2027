"""Singapore-format identifier generators.

Every value is synthetic. NRIC/FIN numbers carry a valid check letter so that a
checksum-validating detector is tested honestly. Case reference formats are fictional
and do not follow any agency's or court's real numbering scheme.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

_WEIGHTS = (2, 7, 6, 5, 4, 3, 2)
_ST_LETTERS = "JZIHGFEDCBA"
_FG_LETTERS = "XWUTRQPNMLK"
_M_LETTERS = "KLJNPQRTUWX"


def nric_check_letter(prefix: str, digits: str) -> str:
    """Return the check letter for a 7-digit NRIC/FIN body under the given series prefix."""
    if prefix not in "STFGM" or len(prefix) != 1:
        raise ValueError(f"unknown prefix {prefix!r}")
    if len(digits) != 7 or not digits.isdigit():
        raise ValueError("body must be 7 digits")
    total = sum(int(d) * w for d, w in zip(digits, _WEIGHTS, strict=True))
    if prefix in "TG":
        total += 4
    elif prefix == "M":
        total += 3
    r = total % 11
    if prefix in "ST":
        return _ST_LETTERS[r]
    if prefix in "FG":
        return _FG_LETTERS[r]
    return _M_LETTERS[10 - r]


def is_valid_nric(value: str) -> bool:
    v = value.strip().upper()
    if len(v) != 9 or v[0] not in "STFGM" or not v[1:8].isdigit() or not v[8].isalpha():
        return False
    return nric_check_letter(v[0], v[1:8]) == v[8]


def make_nric(rng: random.Random, birth_year: int | None = None, foreigner: bool = False) -> str:
    """Synthetic NRIC (S/T) or FIN (F/G/M) with a valid check letter."""
    if foreigner:
        prefix = rng.choice("FGM")
    else:
        prefix = "T" if (birth_year or 1990) >= 2000 else "S"
    body = "".join(rng.choice("0123456789") for _ in range(7))
    if prefix == "T" and birth_year:
        # T-series numbers begin with the last two digits of the birth year.
        body = f"{birth_year % 100:02d}" + body[2:]
    if prefix == "S" and birth_year and birth_year >= 1968:
        body = f"{birth_year % 100:02d}" + body[2:]
    return f"{prefix}{body}{nric_check_letter(prefix, body)}"


# Postal sector (first two digits) -> HDB town. A small, real mapping used so that a
# generated address is internally consistent with the estate quasi-identifier.
SECTORS: dict[str, list[str]] = {
    "Ang Mo Kio": ["56", "57"],
    "Bedok": ["46", "47", "48"],
    "Bukit Batok": ["65"],
    "Bukit Merah": ["15", "16"],
    "Bukit Panjang": ["67"],
    "Choa Chu Kang": ["68"],
    "Clementi": ["12"],
    "Geylang": ["38", "39"],
    "Hougang": ["53"],
    "Jurong East": ["60"],
    "Jurong West": ["64"],
    "Kallang/Whampoa": ["33"],
    "Pasir Ris": ["51"],
    "Punggol": ["82"],
    "Queenstown": ["14"],
    "Sembawang": ["75"],
    "Sengkang": ["54"],
    "Serangoon": ["55"],
    "Tampines": ["52"],
    "Toa Payoh": ["31", "32"],
    "Woodlands": ["73"],
    "Yishun": ["76", "77", "78"],
}

STREETS: dict[str, list[str]] = {
    "Ang Mo Kio": ["Ang Mo Kio Avenue 3", "Ang Mo Kio Avenue 10", "Ang Mo Kio Street 31"],
    "Bedok": ["Bedok North Street 3", "Bedok Reservoir Road", "Chai Chee Street"],
    "Bukit Batok": ["Bukit Batok West Avenue 6", "Bukit Batok Street 21"],
    "Bukit Merah": ["Jalan Bukit Merah", "Telok Blangah Crescent", "Henderson Road"],
    "Bukit Panjang": ["Bukit Panjang Ring Road", "Senja Road", "Fajar Road"],
    "Choa Chu Kang": ["Choa Chu Kang Avenue 4", "Teck Whye Lane"],
    "Clementi": ["Clementi Avenue 3", "West Coast Road"],
    "Geylang": ["Geylang East Avenue 1", "Sims Drive", "Circuit Road"],
    "Hougang": ["Hougang Avenue 8", "Hougang Street 91"],
    "Jurong East": ["Jurong East Street 21", "Toh Guan Road"],
    "Jurong West": ["Jurong West Street 42", "Boon Lay Drive", "Jurong West Street 91"],
    "Kallang/Whampoa": ["Whampoa Drive", "Bendemeer Road", "Jalan Tenteram"],
    "Pasir Ris": ["Pasir Ris Drive 6", "Elias Road"],
    "Punggol": ["Punggol Field", "Edgedale Plains", "Sumang Walk"],
    "Queenstown": ["Stirling Road", "Mei Ling Street", "Commonwealth Drive"],
    "Sembawang": ["Sembawang Crescent", "Canberra Road"],
    "Sengkang": ["Compassvale Drive", "Anchorvale Road", "Rivervale Crescent"],
    "Serangoon": ["Serangoon North Avenue 1", "Lorong Lew Lian"],
    "Tampines": ["Tampines Street 81", "Tampines Avenue 4"],
    "Toa Payoh": ["Toa Payoh Lorong 1", "Toa Payoh Lorong 7"],
    "Woodlands": ["Woodlands Drive 50", "Marsiling Rise", "Woodlands Street 41"],
    "Yishun": ["Yishun Ring Road", "Yishun Avenue 11", "Yishun Street 22"],
}


@dataclass(frozen=True)
class Address:
    block: str
    street: str
    unit: str
    postal: str
    estate: str

    def __str__(self) -> str:
        return f"Blk {self.block} {self.street} #{self.unit}, Singapore {self.postal}"


def make_address(rng: random.Random, estate: str | None = None) -> Address:
    estate = estate or rng.choice(sorted(SECTORS))
    sector = rng.choice(SECTORS[estate])
    block = str(rng.randint(101, 999))
    if rng.random() < 0.25:
        block += rng.choice("ABCD")
    floor = rng.randint(2, 16)
    unit = f"{floor:02d}-{rng.randint(1, 620):03d}"
    postal = f"{sector}{rng.randint(0, 9999):04d}"
    return Address(
        block=block, street=rng.choice(STREETS[estate]), unit=unit, postal=postal, estate=estate
    )


def make_phone(rng: random.Random, mobile: bool = True) -> str:
    first = rng.choice("89") if mobile else "6"
    rest = "".join(rng.choice("0123456789") for _ in range(7))
    return f"{first}{rest[:3]} {rest[3:]}"


def _sub_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # 29 Feb
        return d.replace(year=d.year - years, day=28)


def age_on(dob: date, reference: date) -> int:
    """Completed years between ``dob`` and ``reference``."""
    years = reference.year - dob.year
    if (reference.month, reference.day) < (dob.month, dob.day):
        years -= 1
    return years


def make_dob(rng: random.Random, age: int, reference: date) -> date:
    """A date of birth such that ``age_on(dob, reference) == age``."""
    latest = _sub_years(reference, age)
    earliest = _sub_years(reference, age + 1) + timedelta(days=1)
    span = (latest - earliest).days
    return earliest + timedelta(days=rng.randint(0, max(span, 0)))


DOB_FORMATS = ("%d/%m/%Y", "%d %b %Y", "%d %B %Y", "%Y-%m-%d")


def format_dob(rng: random.Random, dob: date) -> str:
    return dob.strftime(rng.choice(DOB_FORMATS))


def make_case_ref(rng: random.Random, pack: str, year: int) -> str:
    """Fictional case-reference formats. None mirrors a real agency or court scheme."""
    n = rng.randint(1, 4999)
    if pack == "youth-offending":
        return rng.choice(
            [f"YC/{year}/{n:04d}", f"JRC-{year}-{n:04d}", f"PROB/{year % 100:02d}/{n:04d}"]
        )
    if pack == "domestic-violence":
        return rng.choice(
            [f"FSC-{year}-{n:04d}", f"PPO/{year}/{n:04d}", f"FVSC-{year % 100:02d}-{n:04d}"]
        )
    return rng.choice(
        [f"DSC-{year}-{n:04d}", f"SSA/{year}/{n:04d}", f"CM-{year % 100:02d}-{n:04d}"]
    )


# School stems are invented; none matches a school in MOE's school list on data.gov.sg (checked
# 27 Sep 2026). Estates are real so the quasi-identifier under test is real.
SCHOOL_STEMS = [
    "Larkhaven",
    "Heronfield",
    "Riverbend",
    "Seletar Hills",
    "Maplewood",
    "Eastview",
    "Harbourfront",
    "Kranji Heights",
    "Pandan Valley",
    "Springleaf",
    "Tanglin Park",
    "Merlion",
    "Sandpiper",
    "Bendemeer Rise",
    "Sunrise",
    "Tidecrest",
    "Oakcrest",
]
SCHOOL_KINDS = {
    "primary": "Primary School",
    "secondary": "Secondary School",
    "special": "School (Special Education)",
    "ite": "Institute of Technical Education, {campus} Campus",
    "poly": "Polytechnic",
}


def make_school(rng: random.Random, age: int) -> str:
    stem = rng.choice(SCHOOL_STEMS)
    if age <= 12:
        return f"{stem} {SCHOOL_KINDS['primary']}"
    if age <= 16:
        return f"{stem} {SCHOOL_KINDS['secondary']}"
    if age <= 19:
        return rng.choice(
            [f"ITE College {rng.choice(['Central', 'East', 'West'])}", f"{stem} Polytechnic"]
        )
    return f"{stem} Secondary School"


# Facility names are invented too: no real shelter, FSC, day activity centre, home or hospital.
FACILITIES: dict[str, list[str]] = {
    "shelter": [
        "Casa Harapan Crisis Shelter",
        "Rumah Teduh Family Shelter",
        "Haven Crest Shelter",
        "Seaglass Shelter",
    ],
    "rehabilitation centre": [
        "Northgate Centre for Youth",
        "Meadowvale Boys' Home",
        "Riverside Youth Residence",
    ],
    "day activity centre": [
        "Sunbeam Day Activity Centre",
        "Bright Path DAC",
        "Willowbrook Day Activity Centre",
    ],
    "hospital": [
        "Eastgate General Hospital",
        "Woodvale General Hospital",
        "Sunrise Community Hospital",
        "Hillview Institute of Mental Health",
    ],
    "family service centre": [
        "Riverbend Family Service Centre",
        "Harbourlight FSC",
        "Meadowvale FSC",
        "Northgate Family Service Centre",
    ],
    "polyclinic": ["Riverbend Polyclinic", "Harbourlight Polyclinic", "Meadowvale Polyclinic"],
}


def make_facility(rng: random.Random, kind: str) -> str:
    return rng.choice(FACILITIES.get(kind, FACILITIES["family service centre"]))


EMPLOYERS = [
    "a logistics firm in Tuas",
    "a hawker stall at Chong Pang",
    "a cleaning contractor",
    "a coffee shop in Tampines",
    "a retail outlet at Northpoint City",
    "a security agency",
    "a food delivery platform",
    "a construction subcontractor",
    "a childcare centre",
    "an F&B outlet at Jewel",
    "a shipyard in Tuas",
    "a call centre in Changi Business Park",
]


def make_employer(rng: random.Random) -> str:
    return rng.choice(EMPLOYERS)
