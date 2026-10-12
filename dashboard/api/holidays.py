"""2026 Indonesian national public holidays.

Source: SKB 3 Menteri No. 1497/2/5 of 2025 (setneg.go.id). Cuti bersama is collective
leave, not a public holiday, and stays a weekday: 16 Feb, 18 Mar, 20 Mar, 23 Mar,
24 Mar, 15 May, 28 May, 24 Dec.
"""
from datetime import date

HOLIDAYS = frozenset({
    date(2026, 1, 1),
    date(2026, 1, 16),
    date(2026, 2, 17),
    date(2026, 3, 19),
    date(2026, 3, 21),
    date(2026, 3, 22),
    date(2026, 4, 3),
    date(2026, 4, 5),
    date(2026, 5, 1),
    date(2026, 5, 14),
    date(2026, 5, 27),
    date(2026, 5, 31),
    date(2026, 6, 1),
    date(2026, 6, 16),
    date(2026, 8, 17),
    date(2026, 8, 25),
    date(2026, 12, 25),
})


def is_weekend(day: date) -> bool:
    """Saturday, Sunday, or a national public holiday. Cuti bersama stays a weekday."""
    return day.weekday() >= 5 or day in HOLIDAYS


def sql_date_list() -> str:
    """BigQuery DATE literals for HOLIDAYS, in calendar order."""
    return ", ".join(f"DATE '{day.isoformat()}'" for day in sorted(HOLIDAYS))
