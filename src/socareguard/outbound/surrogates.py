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
_TITLES = ("mdm", "ms", "mr", "mrs", "master", "encik", "cik", "puan")
_LINK_TOKENS = {
    "bin",
    "binti",
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
    if re.search(r"\b(bin|binti|bte|bt)\b", n):
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
        for t in toks
    ):
        return "indian"
    return "chinese"


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
    n = name.lower()
    if re.search(r"\b(binti|bte|bt|d/o|a/p|mdm|ms|mrs|puan|cik|nur|siti)\b", n):
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
    return "female"


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

    def name(self, original: str) -> str:
        """Full or short name. A short form of an already-mapped full name reuses that person."""
        low = original.strip().lower()
        title = next((t for t in _TITLES if low.startswith(t + " ")), None)
        bare = low[len(title) + 1 :] if title else low
        for orig, person in self.persons.items():
            if bare and (bare in orig or orig in bare) and bare != orig:
                if len(bare.split()) == 1:
                    sur_title = title_token(person.full) or person.short
                    orig_title = (title_token(orig) or "").lower()
                    single = sur_title if bare == orig_title else person.short
                    return f"{title.capitalize()} {sur_title}" if title else single
                return (
                    f"{title.capitalize()} {person.title.split(' ', 1)[1]}"
                    if title
                    else person.full
                )
        origin, gender = guess_origin(original), guess_gender(original)
        toks = [t for t in re.split(r"[\s,()]+", bare) if t]
        english_given = origin == "chinese" and len(toks) >= 3 and toks[0] not in _CHINESE_SURNAMES
        person = self._fresh_person(origin, gender, english_given=english_given)
        self.persons[bare] = person
        if title:
            return f"{title.capitalize()} {person.title.split(' ', 1)[1]}"
        return person.short if len(bare.split()) == 1 else person.full

    def _fresh_person(self, origin: str, gender: str, english_given: bool = False) -> nm.PersonName:
        for _ in range(400):
            p = nm.make_name(self.rng, origin, gender, 30)
            if origin == "chinese" and (len(p.full.split()) == 4) != english_given:
                continue
            toks = {t.lower() for t in re.split(r"[\s,()/]+", p.full) if len(t) >= 3} - _LINK_TOKENS
            if (
                p.full.lower() in self.used
                or p.full.lower() in self.forbidden
                or toks & self.forbidden_tokens
            ):
                continue
            self.used.update({p.full.lower(), p.short.lower()})
            return p
        raise RuntimeError("no fresh name")

    def nric(self, original: str) -> str:
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
        return self._fresh(lambda: str(ids.make_address(self.rng)))

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

    def email(self, original: str) -> str:
        return self._fresh(lambda: f"user{self.rng.randint(100, 99999)}@example.org")

    def generic(self, original: str) -> str:
        """Re-digit if there are digits, otherwise re-letter the same shape."""
        if re.search(r"\d", original):
            return self._fresh(
                lambda: re.sub(r"\d", lambda m: str(self.rng.randint(0, 9)), original)
            )
        return self._fresh(
            lambda: re.sub(
                r"[A-Za-z]", lambda m: self.rng.choice("abcdefghijklmnopqrstuvwxyz"), original
            )
        )
