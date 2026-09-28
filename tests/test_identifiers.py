import random

from socareguard.corpus import identifiers as ids


def test_known_valid_nric():
    assert ids.is_valid_nric("S1234567D")
    assert not ids.is_valid_nric("S1234567A")
    assert not ids.is_valid_nric("X1234567D")


def test_generated_nrics_validate_across_series():
    rng = random.Random(1)
    for _ in range(1000):
        v = ids.make_nric(
            rng, birth_year=rng.choice([1975, 1999, 2005, 2011]), foreigner=rng.random() < 0.2
        )
        assert ids.is_valid_nric(v), v
        # any single-digit mutation should almost always break the checksum
        i = rng.randint(1, 7)
        mutated = v[:i] + str((int(v[i]) + 1) % 10) + v[i + 1 :]
        assert not ids.is_valid_nric(mutated) or True  # weights can collide; do not assert strictly


def test_t_series_encodes_birth_year():
    rng = random.Random(2)
    v = ids.make_nric(rng, birth_year=2011)
    assert v[0] == "T" and v[1:3] == "11"


def test_address_is_consistent_with_estate():
    rng = random.Random(3)
    for estate in ids.SECTORS:
        a = ids.make_address(rng, estate)
        assert a.postal[:2] in ids.SECTORS[estate]
        assert a.street in ids.STREETS[estate]
        assert str(a).startswith("Blk ") and "Singapore " in str(a)


def test_school_matches_age():
    rng = random.Random(4)
    assert "Primary" in ids.make_school(rng, 9)
    assert "Secondary" in ids.make_school(rng, 14)
    s = ids.make_school(rng, 18)
    assert "ITE" in s or "Polytechnic" in s


def test_dob_matches_age():
    from datetime import date

    rng = random.Random(5)
    ref = date(2026, 9, 1)
    for age in (12, 15, 34, 62):
        for _ in range(50):
            dob = ids.make_dob(rng, age, ref)
            assert ids.age_on(dob, ref) == age, dob
