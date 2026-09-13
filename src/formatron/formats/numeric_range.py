"""Regular expressions for JSON numbers inside a numeric range.

JSON Schema's ``minimum`` / ``maximum`` / ``exclusiveMinimum`` / ``exclusiveMaximum`` are
turned into a regex over the decimal *text* of a number, so a constrained decoder can
enforce them token by token. Integers use the classic digit-prefix decomposition. Decimals
are handled by splitting on the integer part and comparing fractional digit strings, with
strict bounds expressed through "the remaining digits are (not) all zero" conditions.

Numbers with an exponent are not admitted when a bound is present: ``1e2`` has no textual
prefix that reveals its magnitude, so exponent forms cannot be range-checked by a regex.
"""

from __future__ import annotations

import decimal
import math
import typing

__all__ = ["integer_range_regex", "number_range_regex", "NumberBounds"]

Decimal = decimal.Decimal


# ----------------------------------------------------------------------------- integers


def _fixed_width(lo: str, hi: str) -> str:
    """Regex for all digit strings of ``len(lo)`` characters between ``lo`` and ``hi`` (inclusive)."""
    assert len(lo) == len(hi) and lo <= hi
    if not lo:
        return ""
    if lo == hi:
        return lo
    if set(lo) == {"0"} and set(hi) == {"9"}:
        return f"[0-9]{{{len(lo)}}}" if len(lo) > 1 else "[0-9]"
    if lo[0] == hi[0]:
        return lo[0] + _fixed_width(lo[1:], hi[1:])
    a, b = int(lo[0]), int(hi[0])
    rest = len(lo) - 1
    if rest == 0:
        return f"[{a}-{b}]"
    alternatives = [lo[0] + _fixed_width(lo[1:], "9" * rest)]
    if b - a >= 2:
        middle = f"[{a + 1}-{b - 1}]" if b - a > 2 else str(a + 1)
        alternatives.append(f"{middle}[0-9]{{{rest}}}" if rest > 1 else f"{middle}[0-9]")
    alternatives.append(hi[0] + _fixed_width("0" * rest, hi[1:]))
    return "(?:" + "|".join(alternatives) + ")"


def _unsigned_range(lo: int, hi: int) -> str:
    """Regex for canonical (no leading zeros) unsigned integers in ``[lo, hi]``."""
    assert 0 <= lo <= hi
    if lo == hi:
        return str(lo)
    lo_s, hi_s = str(lo), str(hi)
    if len(lo_s) == len(hi_s):
        return _fixed_width(lo_s, hi_s)
    parts = [_fixed_width(lo_s, "9" * len(lo_s))]
    for width in range(len(lo_s) + 1, len(hi_s)):
        parts.append(f"[1-9][0-9]{{{width - 1}}}" if width > 2 else "[1-9][0-9]")
    parts.append(_fixed_width("1" + "0" * (len(hi_s) - 1), hi_s))
    return "(?:" + "|".join(parts) + ")"


def _unsigned_at_least(lo: int) -> str:
    """Regex for canonical unsigned integers ``>= lo``."""
    assert lo >= 0
    if lo == 0:
        return "(?:0|[1-9][0-9]*)"
    width = len(str(lo))
    same_width = _fixed_width(str(lo), "9" * width)
    longer = f"[1-9][0-9]{{{width},}}"
    return f"(?:{same_width}|{longer})"


def integer_range_regex(lo: int | None, hi: int | None) -> str:
    """Regex for canonical JSON integers ``x`` with ``lo <= x <= hi`` (``None`` = unbounded)."""
    if lo is not None and hi is not None and lo > hi:
        raise ValueError(f"empty integer range [{lo}, {hi}]")
    parts = []
    # negative side: x = -y with y >= 1
    if lo is None or lo < 0:
        y_lo = 1 if hi is None or hi >= 0 else -hi
        if lo is None:
            parts.append("-" + _unsigned_at_least(y_lo))
        elif -lo >= y_lo:
            parts.append("-" + _unsigned_range(y_lo, -lo))
    # zero
    if (lo is None or lo <= 0) and (hi is None or hi >= 0):
        parts.append("0")
    # positive side
    if hi is None or hi > 0:
        x_lo = 1 if lo is None or lo <= 0 else lo
        if hi is None:
            parts.append(_unsigned_at_least(x_lo))
        elif hi >= x_lo:
            parts.append(_unsigned_range(x_lo, hi))
    return "(?:" + "|".join(parts) + ")"


# ------------------------------------------------------------------------------ decimals


def _fraction_digits(value: Decimal) -> str:
    """Fractional digits of a non-negative decimal without trailing zeros ('' for integers)."""
    text = format(value, "f")
    if "." not in text:
        return ""
    return text.split(".", 1)[1].rstrip("0")


def _fraction_at_least(frac: str, strict: bool) -> str:
    """Regex for ``.digits`` such that ``0.digits >= 0.frac`` (or ``>`` when strict).

    ``frac`` has no trailing zeros. Returns the pattern for the fractional part *including*
    the leading dot; the caller decides whether "no fraction at all" is also acceptable.
    """
    d = len(frac)
    alternatives = []
    # Fewer digits than the bound: the padded value must clear the bound.
    for k in range(1, d):
        head, tail = frac[:k], frac[k:]
        lower = int(head) + (1 if (strict or any(c != "0" for c in tail)) else 0)
        if lower <= 10**k - 1:
            alternatives.append(_fixed_width(str(lower).zfill(k), "9" * k))
    # At least as many digits as the bound.
    if d == 0:
        alternatives.append("[0-9]*[1-9][0-9]*" if strict else "[0-9]+")
    else:
        above = int(frac) + 1
        if above <= 10**d - 1:
            alternatives.append(_fixed_width(str(above).zfill(d), "9" * d) + "[0-9]*")
        alternatives.append(frac + ("[0-9]*[1-9][0-9]*" if strict else "[0-9]*"))
    return "\\.(?:" + "|".join(alternatives) + ")"


def _fraction_at_most(frac: str, strict: bool) -> str:
    """Regex for ``.digits`` such that ``0.digits <= 0.frac`` (or ``<`` when strict)."""
    d = len(frac)
    alternatives = []
    for k in range(1, d):
        head = frac[:k]
        alternatives.append(_fixed_width("0" * k, head))
    if d == 0:
        if strict:
            return None  # nothing with a fraction is < an integer bound at the same integer part
        alternatives.append("0+")
    else:
        below = int(frac) - 1
        if below >= 0:
            alternatives.append(_fixed_width("0" * d, str(below).zfill(d)) + "[0-9]*")
        if not strict:
            alternatives.append(frac + "0*")
    return "\\.(?:" + "|".join(alternatives) + ")"


def _unsigned_decimal_range(
    lo: Decimal | None,
    hi: Decimal | None,
    lo_strict: bool,
    hi_strict: bool,
) -> list[str]:
    """Alternatives for non-negative decimals ``x`` with ``lo (<|<=) x (<|<=) hi``; bounds ``>= 0``."""
    any_fraction = "(?:\\.[0-9]+)?"
    parts: list[str] = []
    lo_int = None if lo is None else int(lo.to_integral_value(rounding=decimal.ROUND_FLOOR))
    hi_int = None if hi is None else int(hi.to_integral_value(rounding=decimal.ROUND_FLOOR))
    lo_frac = "" if lo is None else _fraction_digits(lo)
    hi_frac = "" if hi is None else _fraction_digits(hi)

    if lo is not None and hi is not None and lo_int == hi_int:
        # Same integer part: the fraction is bounded on both sides.
        head = str(lo_int)
        if lo_frac == "" and hi_frac == "":  # lo == hi == an integer
            return [] if (lo_strict or hi_strict) else [head + "(?:\\.0+)?"]
        if lo_frac == "" and not lo_strict:
            parts.append(head)  # exactly the integer, no fraction
        d = max(len(lo_frac), len(hi_frac))
        alternatives = []
        for k in range(1, d + 1):
            lo_head, lo_tail = lo_frac[:k].ljust(k, "0"), lo_frac[k:]
            hi_head, hi_tail = hi_frac[:k].ljust(k, "0"), hi_frac[k:]
            lo_tail_positive = any(c != "0" for c in lo_tail)
            hi_tail_positive = any(c != "0" for c in hi_tail)
            if k < d:
                # Exactly k fraction digits: the zero-padded value must fall inside the bounds.
                lower = int(lo_head) + (1 if (lo_strict or lo_tail_positive) else 0)
                upper = int(hi_head) - (0 if hi_tail_positive else (1 if hi_strict else 0))
                if lower <= upper:
                    alternatives.append(_fixed_width(str(lower).zfill(k), str(upper).zfill(k)))
            else:
                # First d digits, then any remainder; boundary strings carry their own conditions.
                lower_eq, upper_eq = int(lo_head), int(hi_head)
                if lower_eq + 1 <= upper_eq - 1:
                    alternatives.append(
                        _fixed_width(str(lower_eq + 1).zfill(d), str(upper_eq - 1).zfill(d)) + "[0-9]*"
                    )
                if lower_eq < upper_eq:
                    alternatives.append(lo_head + ("[0-9]*[1-9][0-9]*" if lo_strict else "[0-9]*"))
                    if not hi_strict:
                        alternatives.append(hi_head + "0*")
                elif not lo_strict and not hi_strict:
                    alternatives.append(lo_head + "0*")
        if alternatives:
            parts.append(head + "\\.(?:" + "|".join(alternatives) + ")")
        return parts

    # Lower boundary integer part.
    if lo is not None:
        head = str(lo_int)
        if lo_frac == "":
            if lo_strict:
                parts.append(head + "\\.[0-9]*[1-9][0-9]*")
            else:
                parts.append(head + any_fraction)
        else:
            parts.append(head + _fraction_at_least(lo_frac, lo_strict))
    # Whole integer parts strictly between the boundaries.
    mid_lo = 0 if lo is None else lo_int + 1
    mid_hi = None if hi is None else hi_int - 1
    if mid_hi is None:
        parts.append(_unsigned_at_least(mid_lo) + any_fraction)
    elif mid_lo <= mid_hi:
        parts.append(_unsigned_range(mid_lo, mid_hi) + any_fraction)
    # Upper boundary integer part.
    if hi is not None and (lo is None or hi_int > lo_int):
        head = str(hi_int)
        if hi_frac == "":
            if not hi_strict:
                parts.append(head + "(?:\\.0+)?")
            # strict: x < hi with integer part hi is impossible unless fraction... none allowed
            else:
                pass
        else:
            parts.append(head)  # the integer itself is below hi
            parts.append(head + _fraction_at_most(hi_frac, hi_strict))
    return parts


class NumberBounds(typing.NamedTuple):
    lo: Decimal | None
    hi: Decimal | None
    lo_strict: bool
    hi_strict: bool


def number_range_regex(bounds: NumberBounds) -> str:
    """Regex for JSON decimals (no exponent) inside ``bounds``; ``None`` sides are unbounded."""
    lo, hi, lo_strict, hi_strict = bounds
    if lo is not None and hi is not None and (lo > hi or (lo == hi and (lo_strict or hi_strict))):
        raise ValueError(f"empty numeric range {bounds}")
    parts: list[str] = []
    # Negative side: x = -y, y > 0.  x >= lo  <=>  y <= -lo ;  x <= hi  <=>  y >= -hi.
    if lo is None or lo < 0:
        y_hi = None if lo is None else -lo
        y_hi_strict = lo_strict
        if hi is None or hi >= 0:
            y_lo, y_lo_strict = Decimal(0), True
        else:
            y_lo, y_lo_strict = -hi, hi_strict
        for alt in _unsigned_decimal_range(y_lo, y_hi, y_lo_strict, y_hi_strict):
            parts.append("-" + alt)
    # Zero and the positive side (x >= 0).
    if hi is None or hi > 0 or (hi == 0 and not hi_strict):
        pos_lo = None if lo is None or lo < 0 else lo
        pos_lo_strict = lo_strict if pos_lo is not None else False
        if lo is not None and lo < 0:
            pos_lo, pos_lo_strict = Decimal(0), False
        parts.extend(_unsigned_decimal_range(pos_lo, hi, pos_lo_strict, hi_strict))
    return "(?:" + "|".join(parts) + ")"
