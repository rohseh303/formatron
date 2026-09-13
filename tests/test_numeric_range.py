"""Numeric range regexes: exhaustive checks against decimal arithmetic on small windows."""

import itertools
import random
import re
from decimal import Decimal

import pytest

from formatron.formats.numeric_range import NumberBounds, integer_range_regex, number_range_regex

CANONICAL = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?")


def _in_range(text, bounds):
    x = Decimal(text)
    if bounds.lo is not None and (x < bounds.lo or (bounds.lo_strict and x == bounds.lo)):
        return False
    if bounds.hi is not None and (x > bounds.hi or (bounds.hi_strict and x == bounds.hi)):
        return False
    return True


def _candidates(bounds):
    anchors = [b for b in (bounds.lo, bounds.hi) if b is not None] or [Decimal(0)]
    values = set()
    for anchor in anchors:
        base = int(anchor.to_integral_value())
        for i in range(base - 3, base + 4):
            values.add(str(i))
            for frac in ("0", "1", "5", "9", "01", "09", "49", "50", "51", "99", "001", "125", "999"):
                values.add(f"{i}.{frac}")
    values |= {"-" + v for v in list(values) if not v.startswith("-")}
    return [v for v in values if CANONICAL.fullmatch(v) and not re.fullmatch(r"-0(\.0+)?", v)]


@pytest.mark.parametrize("seed", range(6))
def test_number_range_regex_matches_arithmetic(seed):
    rng = random.Random(seed)

    def bound():
        if rng.random() < 0.25:
            return None
        if rng.random() < 0.4:
            return Decimal(rng.randint(-12, 12))
        return Decimal(rng.randint(-1200, 1200)) / (Decimal(10) ** rng.choice([1, 2, 3]))

    for _ in range(120):
        lo, hi = bound(), bound()
        if lo is not None and hi is not None and lo > hi:
            lo, hi = hi, lo
        bounds = NumberBounds(lo, hi, rng.random() < 0.4, rng.random() < 0.4)
        if lo is not None and hi is not None and lo == hi and (bounds.lo_strict or bounds.hi_strict):
            continue
        pattern = re.compile(number_range_regex(bounds))
        for text in _candidates(bounds):
            assert (pattern.fullmatch(text) is not None) == _in_range(text, bounds), (bounds, text)


@pytest.mark.parametrize("seed", range(4))
def test_integer_range_regex_matches_arithmetic(seed):
    rng = random.Random(seed)
    for _ in range(150):
        lo = None if rng.random() < 0.2 else rng.randint(-2500, 2500)
        hi = None if rng.random() < 0.2 else rng.randint(-2500, 2500)
        if lo is not None and hi is not None and lo > hi:
            lo, hi = hi, lo
        pattern = re.compile(integer_range_regex(lo, hi))
        lo_c = -2600 if lo is None else lo - 3
        hi_c = 2600 if hi is None else hi + 3
        probes = itertools.chain(range(lo_c, lo_c + 6), range(hi_c - 6, hi_c + 1), (rng.randint(lo_c, hi_c) for _ in range(12)))
        for x in probes:
            expected = (lo is None or x >= lo) and (hi is None or x <= hi)
            assert (pattern.fullmatch(str(x)) is not None) == expected, (lo, hi, x)
        for non_canonical in ("01", "-0", "1.0", "+1", "", "1e3"):
            assert pattern.fullmatch(non_canonical) is None


def test_specific_shapes():
    assert re.fullmatch(integer_range_regex(1, 100), "100")
    assert not re.fullmatch(integer_range_regex(1, 100), "0")
    assert re.fullmatch(integer_range_regex(None, None), "-987654321")
    assert re.fullmatch(number_range_regex(NumberBounds(Decimal("0.5"), None, False, False)), "0.5000")
    assert not re.fullmatch(number_range_regex(NumberBounds(Decimal("0.5"), None, True, False)), "0.5000")
    assert re.fullmatch(number_range_regex(NumberBounds(Decimal("0.5"), None, True, False)), "0.5001")
    assert re.fullmatch(number_range_regex(NumberBounds(Decimal(1), Decimal(1), False, False)), "1.00")
    with pytest.raises(ValueError):
        integer_range_regex(5, 4)
    with pytest.raises(ValueError):
        number_range_regex(NumberBounds(Decimal(1), Decimal(1), True, False))
