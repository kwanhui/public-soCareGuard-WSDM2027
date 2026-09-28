"""Gender- and origin-tagged synthetic name pools for Singapore.

Origins: chinese, malay, indian, eurasian, western. Names are common patterns, not real
people. Malay and Indian names use patronymic forms (bin / binti, s/o / d/o) so that the
detector is tested on the full local variety.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

ORIGINS = ("chinese", "malay", "indian", "eurasian", "western")

_CHINESE_SURNAMES = [
    "Tan",
    "Lim",
    "Lee",
    "Ng",
    "Ong",
    "Wong",
    "Goh",
    "Chua",
    "Chan",
    "Koh",
    "Teo",
    "Ang",
    "Yeo",
    "Tay",
    "Ho",
    "Low",
    "Toh",
    "Sim",
    "Chong",
    "Chia",
    "Wee",
    "Neo",
    "Seah",
    "Quek",
    "Pang",
    "Foo",
    "Heng",
    "Khoo",
    "Loh",
    "Soh",
]
_CHINESE_GIVEN = {
    "female": [
        "Jia Hui",
        "Xin Yi",
        "Hui Ling",
        "Zi Xuan",
        "Mei Ling",
        "Shu Fen",
        "Li Ting",
        "Yi Xuan",
        "Siew Lan",
        "Ai Ling",
        "Pei Shan",
        "Wan Ting",
        "Hui Min",
        "Jia Yi",
        "Xiu Mei",
        "Li Hua",
        "Yan Ling",
        "Su Lin",
        "Jing Wen",
        "Kai Lin",
    ],
    "male": [
        "Wei Ming",
        "Kai Xiang",
        "Jun Jie",
        "Yu Xuan",
        "Hao Ran",
        "Wen Jun",
        "Jia Le",
        "Ming Hui",
        "Boon Keng",
        "Zhi Wei",
        "Jun Hao",
        "Wei Jie",
        "Kian Hock",
        "Chee Keong",
        "Yong Sheng",
        "Jian Wei",
        "Han Wei",
        "Zi Yang",
        "Guo Wei",
        "Tze Wei",
    ],
}
_CHINESE_ENGLISH = {
    "female": ["Jasmine", "Michelle", "Rachel", "Cheryl", "Serene", "Joanne", "Vivian", "Grace"],
    "male": ["Kelvin", "Darren", "Marcus", "Ryan", "Jason", "Benjamin", "Alvin", "Desmond"],
}

_MALAY_GIVEN = {
    "female": [
        "Nur Aisyah",
        "Siti Nurhaliza",
        "Farhana",
        "Nabilah",
        "Amirah",
        "Nurul Huda",
        "Syafiqah",
        "Nadiah",
        "Aqilah",
        "Hazirah",
        "Sarah",
        "Aisyah",
        "Fatin",
        "Nur Izzati",
        "Diyanah",
    ],
    "male": [
        "Muhammad Danish",
        "Aiman",
        "Irfan",
        "Haziq",
        "Syafiq",
        "Hakim",
        "Muhammad Firdaus",
        "Ariff",
        "Zulkifli",
        "Amirul",
        "Danial",
        "Fairuz",
        "Hafiz",
        "Ridzuan",
        "Khairul",
    ],
}
_MALAY_FATHERS = [
    "Rosli",
    "Hamid",
    "Ismail",
    "Abdullah",
    "Rahman",
    "Yusof",
    "Osman",
    "Kamal",
    "Salleh",
    "Zainal",
    "Hassan",
    "Rashid",
    "Jaafar",
    "Mohamed",
    "Ibrahim",
]

_INDIAN_GIVEN = {
    "female": [
        "Priya",
        "Kavitha",
        "Devi",
        "Lakshmi",
        "Selvi",
        "Meena",
        "Nithya",
        "Shanti",
        "Vijaya",
        "Rani",
        "Anitha",
        "Kamala",
        "Malar",
        "Saraswathi",
        "Thanam",
    ],
    "male": [
        "Kumar",
        "Vishnu",
        "Rajesh",
        "Anand",
        "Muthu",
        "Arun",
        "Suresh",
        "Karthik",
        "Ganesh",
        "Bala",
        "Ravi",
        "Prakash",
        "Selvam",
        "Ramesh",
        "Dinesh",
    ],
}
_INDIAN_FATHERS = [
    "Ramasamy",
    "Subramaniam",
    "Krishnan",
    "Muthusamy",
    "Govindasamy",
    "Rajan",
    "Pillai",
    "Nathan",
    "Velu",
    "Sivalingam",
    "Perumal",
    "Chandran",
    "Shanmugam",
    "Palaniappan",
]

_EURASIAN_SURNAMES = [
    "Pereira",
    "de Souza",
    "Oliveiro",
    "Rodrigues",
    "Fernandez",
    "Klass",
    "Westerhout",
    "Scully",
    "Shepherdson",
    "Tessensohn",
    "Nonis",
    "Minjoot",
    "de Silva",
    "Aeria",
]
_EURASIAN_GIVEN = {
    "female": [
        "Melissa",
        "Nicole",
        "Vanessa",
        "Andrea",
        "Sheryl",
        "Charmaine",
        "Bernadette",
        "Denise",
    ],
    "male": [
        "Jonathan",
        "Gabriel",
        "Dominic",
        "Clarence",
        "Nicholas",
        "Adrian",
        "Bernard",
        "Christopher",
    ],
}

_WESTERN_SURNAMES = [
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Taylor",
    "Anderson",
    "Thomas",
    "Jackson",
    "White",
    "Harris",
    "Martin",
    "Clarke",
    "Walker",
    "Robinson",
]
_WESTERN_GIVEN = {
    "female": ["Sarah", "Emily", "Rachel", "Laura", "Hannah", "Emma", "Olivia", "Sophie"],
    "male": ["James", "Michael", "David", "Daniel", "Matthew", "Thomas", "Andrew", "Oliver"],
}


@dataclass(frozen=True)
class PersonName:
    origin: str
    gender: str
    full: str
    short: str
    title: str  # e.g. "Mdm Tan", "Mr Kumar"

    def form(self, key: str) -> str:
        if key.endswith("_NAME"):
            return self.full
        if key.endswith("_FIRST"):
            return self.short
        return self.title


def _title(gender: str, age: int, married_hint: bool) -> str:
    if gender == "female":
        return "Mdm" if (age >= 30 or married_hint) else "Ms"
    return "Mr" if age >= 18 else "Master"


def make_name(
    rng: random.Random,
    origin: str,
    gender: str,
    age: int = 30,
    married_hint: bool = False,
    fixed_surname: str | None = None,
    fixed_father: str | None = None,
) -> PersonName:
    """A synthetic name. ``fixed_surname`` (Chinese, Eurasian, Western) or ``fixed_father`` (Malay,
    Indian) replaces the drawn surname or father-name, so that members of one household can share
    it. The random draws are the same with or without them, so a name that fixes nothing is the
    name the same generator state gave before."""
    if origin not in ORIGINS:
        raise ValueError(origin)
    t = _title(gender, age, married_hint)
    if origin == "chinese":
        surname = rng.choice(_CHINESE_SURNAMES)
        surname = fixed_surname or surname
        given = rng.choice(_CHINESE_GIVEN[gender])
        if rng.random() < 0.35:
            eng = rng.choice(_CHINESE_ENGLISH[gender])
            return PersonName(origin, gender, f"{eng} {surname} {given}", eng, f"{t} {surname}")
        return PersonName(origin, gender, f"{surname} {given}", given, f"{t} {surname}")
    if origin == "malay":
        given = rng.choice(_MALAY_GIVEN[gender])
        link = "binti" if gender == "female" else "bin"
        father = rng.choice(_MALAY_FATHERS)
        father = fixed_father or father
        short = given.split()[-1] if given.startswith(("Muhammad ", "Nur ")) else given.split()[0]
        return PersonName(origin, gender, f"{given} {link} {father}", short, f"{t} {short}")
    if origin == "indian":
        given = rng.choice(_INDIAN_GIVEN[gender])
        link = "d/o" if gender == "female" else "s/o"
        father = rng.choice(_INDIAN_FATHERS)
        father = fixed_father or father
        return PersonName(origin, gender, f"{given} {link} {father}", given, f"{t} {given}")
    if origin == "eurasian":
        surname = rng.choice(_EURASIAN_SURNAMES)
        surname = fixed_surname or surname
        given = rng.choice(_EURASIAN_GIVEN[gender])
        return PersonName(origin, gender, f"{given} {surname}", given, f"{t} {surname}")
    surname = rng.choice(_WESTERN_SURNAMES)
    surname = fixed_surname or surname
    given = rng.choice(_WESTERN_GIVEN[gender])
    return PersonName(origin, gender, f"{given} {surname}", given, f"{t} {surname}")


def pick_origin(rng: random.Random, weights: dict[str, float]) -> str:
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]
