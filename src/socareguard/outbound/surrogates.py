"""Type-consistent, format-preserving surrogates.

A surrogate must look like the thing it replaces (a Malay name for a Malay name, a valid
NRIC for an NRIC, a plausible HDB address for an address) so that the model's draft keeps
its shape, and it must be injective within a session so that restoration is unambiguous.
"""

from __future__ import annotations

import random
import re
from datetime import date, datetime, timedelta

from socareguard.corpus import identifiers as ids
from socareguard.corpus import names as nm

_CHINESE_SURNAMES = {s.lower() for s in nm._CHINESE_SURNAMES}
_EURASIAN = {s.lower() for s in nm._EURASIAN_SURNAMES}
_WESTERN = {s.lower() for s in nm._WESTERN_SURNAMES}
# "dr" and "prof" carry no gender; a clinician's title stays on the surrogate ("Dr Amanda Wong" ->
# "Dr Soh Mei Ling"), so a reply that writes "Dr <surrogate>" restores to "Dr Amanda Wong" once.
_TITLES = ("mdm", "ms", "mr", "mrs", "master", "encik", "cik", "puan", "dr", "prof", "professor")
_LINK_TOKENS = {
    "bin",
    "binti",
    "binte",
    "bte",
    "s/o",
    "d/o",
    "a/l",
    "a/p",
    "mdm",
    "mr",
    "mrs",
    "master",
    "nur",
    "muhammad",
    "siti",
}


def guess_origin(name: str) -> str:
    n = name.lower()
    if re.search(r"\b(bin|binti|binte|bte|bt)\b", n):
        return "malay"
    if re.search(r"\b(s/o|d/o|a/l|a/p)\b", n):
        return "indian"
    toks = [t for t in re.split(r"[\s,]+", n) if t and t not in _TITLES]
    if any(t in _CHINESE_SURNAMES for t in toks):
        return "chinese"
    if any(t in _EURASIAN for t in toks):
        return "eurasian"
    if any(t in _WESTERN for t in toks):
        return "western"
    if any(
        t in {s.lower() for s in nm._MALAY_FATHERS}
        or t in {g.lower() for gl in nm._MALAY_GIVEN.values() for g in gl}
        for t in toks
    ):
        return "malay"
    if any(
        t in {s.lower() for s in nm._INDIAN_FATHERS}
        or t in {g.lower() for gl in nm._INDIAN_GIVEN.values() for g in gl}
        or t in _INDIAN_SURNAMES
        for t in toks
    ):
        return "indian"
    return "chinese"


# Family and caste names common among Singapore Indians, which the given-name and father-name
# pools do not hold: "Kavya Nair" is an Indian name, not a Chinese one.
_INDIAN_SURNAMES = {
    "nair", "menon", "pillai", "iyer", "iyengar", "naidu", "reddy", "rao", "sharma", "gupta",
    "singh", "kaur", "gill", "sandhu", "sidhu", "dhillon", "chettiar", "chettiyar", "panicker",
    "kurup", "nambiar", "shetty", "das", "rajan", "krishnan", "subramaniam", "subramanian",
    "ramasamy", "govindasamy", "suppiah", "thangaraj", "balakrishnan", "chandran", "gopal",
    "naidoo", "mudaliar", "thevar", "pandian", "ramachandran", "rajendran", "selvaraj",
}  # fmt: skip


# Pronouns that say which gender a person in the note is, when the name does not.
_PRONOUN = re.compile(r"\b(he|him|his|himself|she|her|hers|herself)\b", re.IGNORECASE)
_OTHER_PERSON = re.compile(
    r"\b(?:mother|father|mum|mom|dad|brother|sister|wife|husband|son|daughter|teacher|mentor"
    r"|officer|friends?|girlfriend|boyfriend|partner|grandmother|grandfather|grandma|grandpa"
    r"|aunt|uncle|cousin|youths?|boys?|girls?|man|woman|mak|ibu|ayah|bapa|amma|appa|Mr|Mrs|Ms"
    r"|Mdm|Madam)\b",
    re.IGNORECASE,
)


def gender_from_pronouns(text: str, names: list[tuple[int, int, str]]) -> dict[str, str]:
    """For each name in ``names`` (start, end, text), the gender that the pronouns referring to
    that person indicate, where they agree. A pronoun refers to the nearest name before it in the
    same paragraph, unless its own sentence names another person first ("His mother said she ...").
    Short and full forms of one person ("Kai Ming", "Kai Ming Ong") pool their pronouns."""
    spans = sorted(names)
    counts: dict[frozenset[str], dict[str, int]] = {}
    for m in _PRONOUN.finditer(text):
        prev = next((n for n in reversed(spans) if n[1] <= m.start()), None)
        if prev is None:
            continue
        gap = text[prev[1] : m.start()]
        if "\n\n" in gap or len(gap) > 400:
            continue
        sentence = re.split(r"[.!?]\s+|\n", gap)[-1]
        g = "male" if m.group(1).lower() in ("he", "him", "his", "himself") else "female"
        others = [w.lower() for w in _OTHER_PERSON.findall(sentence)]
        if others and not all(_RELATION_GENDER.get(w) not in (None, g) for w in others):
            # "Wife ... said he has not been sleeping": a pronoun of the other gender from every
            # person the sentence names still refers to the name before it; otherwise skip
            continue
        key = _core_tokens(prev[2])
        counts.setdefault(key, {"male": 0, "female": 0})[g] += 1
    out: dict[str, str] = {}
    for _, _, name in spans:
        mine = _core_tokens(name)
        total = {"male": 0, "female": 0}
        for key, c in counts.items():
            if key and mine and (key <= mine or mine <= key):
                total["male"] += c["male"]
                total["female"] += c["female"]
        if total["male"] != total["female"]:
            out[name] = "male" if total["male"] > total["female"] else "female"
    return out


def title_token(name: str) -> str | None:
    """The token a title attaches to: surname for Chinese/Eurasian/Western, given name for Malay/Indian."""
    toks = [t for t in re.split(r"[\s,()]+", name.strip()) if t and t.lower() not in _TITLES]
    if not toks:
        return None
    origin = guess_origin(name)
    if origin in ("malay", "indian"):
        core = [t for t in toks if t.lower() not in _LINK_TOKENS]
        return core[0] if core else None
    if origin == "chinese":
        for t in toks[:2]:
            if t.lower() in _CHINESE_SURNAMES:
                return t
        return toks[0]
    return toks[-1]


def guess_gender(name: str) -> str:
    return gender_evidence(name) or "female"


def gender_evidence(name: str) -> str | None:
    """The gender a name or title indicates, or None when nothing in it does."""
    n = name.lower()
    if re.search(r"\b(binti|binte|bte|bt|d/o|a/p|mdm|ms|mrs|puan|cik|nur|siti)\b", n):
        return "female"
    if re.search(r"\b(bin|s/o|a/l|mr|master|encik|muhammad|mohamed|mohammad)\b", n):
        return "male"
    for g, pool in (
        (
            "female",
            nm._CHINESE_GIVEN["female"]
            + nm._CHINESE_ENGLISH["female"]
            + nm._EURASIAN_GIVEN["female"]
            + nm._WESTERN_GIVEN["female"]
            + nm._INDIAN_GIVEN["female"],
        ),
        (
            "male",
            nm._CHINESE_GIVEN["male"]
            + nm._CHINESE_ENGLISH["male"]
            + nm._EURASIAN_GIVEN["male"]
            + nm._WESTERN_GIVEN["male"]
            + nm._INDIAN_GIVEN["male"],
        ),
    ):
        if any(p.lower() in n for p in pool):
            return g
    # Malay and Muslim given names, which the pools above do not hold, compared as whole tokens
    toks = set(re.split(r"[\s,()]+", n))
    for g in ("male", "female"):
        if toks & _GIVEN_BY_GENDER[g]:
            return g
    return None


_GIVEN_BY_GENDER = {
    "male": {g.lower() for g in nm._MALAY_GIVEN["male"] for g in g.split()}
    | {
        "danish", "danial", "ridzwan", "ridwan", "ridzuan", "irfan", "hafiz", "faris", "aiman",
        "arif", "ilham", "syahmi", "zulkifli", "rahim", "johari", "razak", "ismail", "ahmad",
        "rizal", "firdaus", "hakim", "haziq", "amir", "amirul", "imran", "rayyan", "harith",
        "khairul", "azman", "hamid", "salleh", "yusof", "karim", "zainal", "rosli", "hassan",
        "iskandar", "shafiq", "syafiq", "hidayat", "fadli", "azhar", "hisham", "kamal", "nazri",
    },
    "female": {g.lower() for g in nm._MALAY_GIVEN["female"] for g in g.split()}
    | {
        "farah", "aisyah", "aishah", "aisha", "nurul", "farhana", "suriati", "suriaty", "nabilah",
        "latifah", "rosnah", "fatimah", "amirah", "izzati", "hazirah", "syafiqah", "nadiah",
        "salmah", "zarina", "hidayah", "diyanah", "aliyah", "qistina", "batrisyia", "nurhaliza",
        "zainab", "khadijah", "maryam", "halimah", "norhayati", "rohani", "zaleha", "huda",
    },
}  # fmt: skip
_GIVEN_BY_GENDER["male"] -= {"nur", "muhammad"} | _GIVEN_BY_GENDER["female"]
_GIVEN_BY_GENDER["female"] -= {"nur", "muhammad", "siti"}

# A relationship or title word just before a name says which gender it is when the name does not.
_RELATION_GENDER = {
    **dict.fromkeys(
        ("son", "husband", "father", "brother", "boy", "grandson", "nephew", "uncle", "grandfather",
         "stepfather", "stepson", "mr", "encik", "master", "he"),
        "male",
    ),
    **dict.fromkeys(
        ("daughter", "wife", "mother", "sister", "girl", "granddaughter", "niece", "aunt",
         "grandmother", "stepmother", "stepdaughter", "mdm", "madam", "ms", "mrs", "cik", "puan",
         "she"),
        "female",
    ),
}  # fmt: skip


def gender_from_context(before: str) -> str | None:
    """The gender a relationship word in the three words before a name indicates ("her husband
    Ridzwan", "Son Danial")."""
    for w in reversed(re.findall(r"[A-Za-z]+", before)[-3:]):
        g = _RELATION_GENDER.get(w.lower())
        if g:
            return g
    return None


def _core_tokens(name: str) -> frozenset[str]:
    """Lower-case name tokens without titles or link words ("bin", "binti", "bte", "s/o")."""
    return frozenset(
        t for t in re.split(r"[\s,()]+", name.lower()) if t and t not in _TITLES and t not in _LINKS
    )


_LINKS = {"bin", "binti", "binte", "bte", "bt", "s/o", "d/o", "a/l", "a/p"}


def within_one_edit(a: str, b: str) -> bool:
    """Whether two words differ by at most one substitution, insertion or deletion."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i + (len(a) == len(b)) :] == b[i + 1 :]


def name_variant(a: str, b: str) -> bool:
    """Two name tokens that name the same person: equal, or one edit apart when both have five or
    more letters and share the first letter."""
    a, b = a.lower(), b.lower()
    return a == b or (len(a) >= 5 and len(b) >= 5 and a[0] == b[0] and within_one_edit(a, b))


def _fuzzy_subset(small: frozenset[str], big: frozenset[str]) -> bool:
    return bool(small) and all(any(name_variant(t, u) for u in big) for t in small)


class SurrogateFactory:
    """Generates surrogates for one session. ``used`` guarantees injectivity."""

    def __init__(self, seed: int, forbidden: set[str] | None = None):
        self.rng = random.Random(seed)
        self.used: set[str] = set()
        self.forbidden = {f.lower() for f in (forbidden or set())}
        self.forbidden_tokens = {
            t
            for f in self.forbidden
            for t in re.split(r"[\s,()/]+", f)
            if len(t) >= 3 and t not in _LINK_TOKENS
        }
        self.persons: dict[str, nm.PersonName] = {}

    def _fresh(self, make, tries: int = 50) -> str:
        v = ""
        for _ in range(tries):
            v = make()
            if v.lower() not in self.used and v.lower() not in self.forbidden:
                self.used.add(v.lower())
                return v
        # The generator cannot vary this shape (e.g. a reference whose only digits are a year):
        # append a random digit so the surrogate is still unused rather than failing the request.
        for _ in range(1000):
            w = f"{v}{self.rng.randint(0, 9)}"
            if w.lower() not in self.used and w.lower() not in self.forbidden:
                self.used.add(w.lower())
                return w
        raise RuntimeError("could not find an unused surrogate")

    def name(self, original: str, gender_hint: str | None = None) -> str:
        """Full or short name. Every variant of one person in a session (full name, given name,
        titled form, "bin"/"binti" or "bte" spelling) maps to forms of the same surrogate. The
        surrogate's gender follows the name, or ``gender_hint`` when the name does not say."""
        poss = re.search(r"['\u2019]s$", original.strip())
        if poss and len(original.strip()) > 2:
            # "Wei Ming's" is a form of "Wei Ming": the same surrogate, with the possessive back
            return self.name(original.strip()[: poss.start()], gender_hint) + poss.group(0)
        low = original.strip().lower()
        m_title = re.match(r"([a-z]+)\.?\s+", low)
        title = m_title.group(1) if m_title and m_title.group(1) in _TITLES else None
        bare = low[m_title.end() :] if title and m_title else low
        match = self._same_person(bare, title)
        if match is not None:
            orig, person = match
            return self._form(person, orig, bare, title, new=False)
        origin = guess_origin(original)
        gender = gender_evidence(original) or gender_hint or "female"
        toks = [t for t in re.split(r"[\s,()]+", bare) if t]
        english_given = origin == "chinese" and len(toks) >= 3 and toks[0] not in _CHINESE_SURNAMES
        person = self._fresh_person(origin, gender, english_given=english_given)
        self.persons[bare] = person
        return self._form(person, bare, bare, title, new=True)

    def _same_person(self, bare: str, title: str | None) -> tuple[str, nm.PersonName] | None:
        """The person already mapped in this session that ``bare`` names, if any: one token set
        contains the other once titles and link words are set aside. When a surname fits more
        than one person, the one whose gender matches the title is chosen."""
        b = _core_tokens(bare)
        if not b:
            return None
        found = [
            (orig, person)
            for orig, person in self.persons.items()
            if (o := _core_tokens(orig)) and (b <= o or o <= b)
        ]
        if not found:
            # a one-letter slip in a name of five or more letters ("Suriaty" for "Suriati") is the
            # same person, not a second identity
            found = [
                (orig, person)
                for orig, person in self.persons.items()
                if (o := _core_tokens(orig)) and (_fuzzy_subset(b, o) or _fuzzy_subset(o, b))
            ]
        if not found:
            return None
        want = (
            "male"
            if title in ("mr", "master", "encik")
            else "female"
            if title in ("mdm", "ms", "mrs", "cik", "puan")
            else None
        )
        # a person whose own name indicates the other gender is not the one a title points to
        by_gender = [f for f in found if want and gender_evidence(f[0]) in (want, None)]
        by_title = [f for f in by_gender or found if (title_token(f[0]) or "").lower() == bare]
        return (by_title or by_gender or found)[0]

    @staticmethod
    def _form(person: nm.PersonName, orig: str, bare: str, title: str | None, new: bool) -> str:
        """The form of ``person`` that matches how ``bare`` names the original ``orig``."""
        full = person.full
        if len(_core_tokens(bare)) >= 2:
            return f"{title.capitalize()} {full}" if title else full
        sur_title = title_token(full) or person.short
        if new:  # a one-word name seen for the first time
            return f"{title.capitalize()} {sur_title}" if title else person.short
        single = sur_title if bare == (title_token(orig) or "").lower() else person.short
        return f"{title.capitalize()} {single}" if title else single

    def _fresh_person(self, origin: str, gender: str, english_given: bool = False) -> nm.PersonName:
        for _ in range(400):
            p = nm.make_name(self.rng, origin, gender, 30)
            if origin == "chinese" and (len(p.full.split()) == 4) != english_given:
                continue
            toks = {t.lower() for t in re.split(r"[\s,()/]+", p.full) if len(t) >= 3} - _LINK_TOKENS
            tt = (title_token(p.full) or "").lower()
            if (
                p.full.lower() in self.used
                or p.short.lower() in self.used
                or (tt and tt in self.used)
                or p.full.lower() in self.forbidden
                or p.short.lower() in self.forbidden
                or toks & self.forbidden_tokens
                or toks & self.used
            ):
                continue
            # Two people in one session never share a full name, a short form or a title token.
            self.used.update({p.full.lower(), p.short.lower()} | toks | ({tt} if tt else set()))
            return p
        raise RuntimeError("no fresh name")

    def nric(self, original: str) -> str:
        original = re.sub(r"[\s-]", "", original).upper()
        prefix = original[0].upper() if original and original[0].upper() in "STFGM" else "S"
        birth_year = None
        if prefix == "T" and original[1:3].isdigit():
            birth_year = 2000 + int(original[1:3])
        return self._fresh(
            lambda: ids.make_nric(self.rng, birth_year=birth_year, foreigner=prefix in "FGM")
        )

    def phone(self, original: str) -> str:
        digits = re.sub(r"\D", "", original)
        mobile = (
            not digits.endswith(tuple("0123456789")) or digits[-8] in "89"
            if len(digits) >= 8
            else True
        )
        v = self._fresh(lambda: ids.make_phone(self.rng, mobile=mobile))
        return v if " " in original or len(original) > 9 else v.replace(" ", "")

    def address(self, original: str) -> str:
        """A whole address for a whole address. The surrogate has the parts that the original has,
        so a block and street alone ("Blk 203 Sengkang East Way") receives a block and street."""
        has_unit = bool(re.search(r"#\s?\d", original))
        has_postal = bool(re.search(r"(?<!\d)\d{6}(?!\d)", original))

        def make() -> str:
            a = ids.make_address(self.rng)
            out = f"Blk {a.block} {a.street}"
            if has_unit:
                out += f" #{a.unit}"
            if has_postal:
                out += f", Singapore {a.postal}"
            return out

        if has_unit and has_postal:
            return self._fresh(lambda: str(ids.make_address(self.rng)))
        return self._fresh(make)

    def postal(self, original: str) -> str:
        return self._fresh(
            lambda: (
                f"{self.rng.choice([s for v in ids.SECTORS.values() for s in v])}{self.rng.randint(0, 9999):04d}"
            )
        )

    def unit(self, original: str) -> str:
        return self._fresh(lambda: f"#{self.rng.randint(2, 16):02d}-{self.rng.randint(1, 620):03d}")

    def block(self, original: str) -> str:
        word = original.split()[0]
        return self._fresh(lambda: f"{word} {self.rng.randint(101, 999)}")

    def case_ref(self, original: str) -> str:
        """Re-digit the serial part; keep a plausible year token (19xx/20xx) when other digits exist."""
        tokens = re.findall(r"\d+", original)
        keep_year = any(not re.fullmatch(r"(19|20)\d{2}", t) for t in tokens)

        def make() -> str:
            def sub(m: re.Match[str]) -> str:
                tok = m.group(0)
                if keep_year and re.fullmatch(r"(19|20)\d{2}", tok):
                    return tok
                return "".join(str(self.rng.randint(0, 9)) for _ in tok)

            return re.sub(r"\d+", sub, original)

        return self._fresh(make)

    def dob(self, original: str) -> str:
        parsed: tuple[date, str] | None = None
        for fmt in ids.DOB_FORMATS + ("%d/%m/%y", "%d-%m-%Y"):
            try:
                parsed = (datetime.strptime(original, fmt).date(), fmt)  # noqa: DTZ007
                break
            except ValueError:
                continue
        if parsed is None:
            return self._fresh(
                lambda: re.sub(r"\d", lambda m: str(self.rng.randint(0, 9)), original)
            )
        d, fmt = parsed

        def make() -> str:
            shifted = d + timedelta(days=self.rng.choice([-1, 1]) * self.rng.randint(20, 120))
            return shifted.strftime(fmt)

        return self._fresh(make)

    def school(self, original: str) -> str:
        age = 14 if "secondary" in original.lower() else 9 if "primary" in original.lower() else 18
        return self._fresh(lambda: ids.make_school(self.rng, age))

    def facility(self, original: str) -> str:
        t = original.lower()
        kind = (
            "shelter"
            if "shelter" in t
            else "day activity centre"
            if "activity" in t
            else "hospital"
            if "hospital" in t
            else "polyclinic"
            if "polyclinic" in t
            else "rehabilitation centre"
            if ("home" in t or "youth" in t)
            else "family service centre"
        )
        return self._fresh(lambda: ids.make_facility(self.rng, kind))

    def work_permit(self, original: str) -> str:
        """A FIN-shaped permit number takes a FIN in the same series, and a numeric one is
        re-digited."""
        if re.fullmatch(r"[FGMfgm][\s-]?\d{7}[\s-]?[A-Za-z]", original):
            return self.nric(original)
        return self.generic(original)

    def email(self, original: str) -> str:
        return self._fresh(lambda: f"user{self.rng.randint(100, 99999)}@example.org")

    def passport(self, original: str) -> str:
        prefix = original[0].upper() if original and original[0].isalpha() else "E"
        return self._fresh(
            lambda: (
                prefix
                + "".join(str(self.rng.randint(0, 9)) for _ in range(7))
                + self.rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ")
            )
        )

    def handle(self, original: str) -> str:
        """A social handle is replaced by a neutral one: the original often carries a real name."""
        return self._fresh(lambda: f"@user{self.rng.randint(1000, 999999)}")

    def url(self, original: str) -> str:
        """A link of the same shape: its scheme and "www." as written, a public platform's domain
        kept (it names no one), any other domain replaced, and each path segment replaced by a
        neutral token, so "https://facebook.com/johnlim1998" leaves as
        "https://facebook.com/user48213"."""
        m = re.match(r"(?i)(https?://)?(www\.)?([^/?#]+)(/[^?#]*)?(\?[^#]*)?(#.*)?$", original)
        if not m:
            return self._fresh(lambda: f"https://example.org/page{self.rng.randint(1000, 99999)}")
        scheme, www, host, path, query, frag = m.groups()
        keep = host.lower() in _PLATFORMS

        def make() -> str:
            out = (scheme or "") + (www or "") + (host if keep else "example.org")
            segs = (path or "").split("/")[1:]
            for i, seg in enumerate(segs):
                word = "user" if i == 0 else "page"
                out += "/" + (f"{word}{self.rng.randint(1000, 99999)}" if seg else "")
            if query:
                out += f"?id={self.rng.randint(1000, 99999)}"
            if frag:
                out += "#top"
            return out

        return self._fresh(make)

    def generic(self, original: str) -> str:
        """Re-digit if there are digits, otherwise re-letter the same shape."""
        if re.search(r"\d", original):
            return self._fresh(
                lambda: re.sub(r"\d", lambda m: str(self.rng.randint(0, 9)), original)
            )
        # Letters only: a re-lettered string reads as gibberish and a numbered placeholder
        # ("an organisation (6)") reaches the draft as written, so the surrogate is an invented
        # organisation name that keeps the original's kind ("mall security" -> "Kestrel Security").
        kind = next(
            (w.capitalize() for w in reversed(original.lower().split()) if w in _ORG_KINDS),
            "Services",
        )
        return self._fresh(lambda: f"{self.rng.choice(_ORG_STEMS)} {kind}")


# Public platforms whose domain in a link names no one; the path after it may.
_PLATFORMS = {
    "facebook.com", "fb.com", "m.facebook.com", "instagram.com", "tiktok.com", "youtube.com",
    "youtu.be", "linkedin.com", "x.com", "twitter.com", "t.me", "wa.me", "reddit.com",
    "carousell.sg", "threads.net", "telegram.me", "discord.gg", "snapchat.com",
}  # fmt: skip
# Invented organisation stems; none is a Singapore company or agency name checked in September 2026.
_ORG_STEMS = [
    "Kestrel", "Amberlane", "Tidewell", "Larkspur", "Copperfield", "Wrenhaven", "Bellmoor",
    "Silverbirch", "Harrowgate", "Pinecrest", "Marlowe", "Fernleigh", "Ashcombe", "Brightwater",
    "Coralbay", "Duskfield", "Elmstead", "Foxglove", "Glenmoor", "Hollybank",
]  # fmt: skip
_ORG_KINDS = {
    "security", "services", "service", "logistics", "cleaning", "contractor", "contractors",
    "trading", "enterprise", "enterprises", "holdings", "group", "company", "agency", "centre",
    "clinic", "cafe", "restaurant", "bakery", "store", "shop", "mart", "supermarket", "school",
}  # fmt: skip
