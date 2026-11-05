"""Loans of a small neighbourhood library: due dates and late fines."""
from dataclasses import dataclass
from datetime import date, timedelta

LOAN_DAYS = 21
FINE_PER_DAY = 0.25


@dataclass
class Loan:
    book: str
    reader: str
    start: date
    due: date
    returned: date | None = None


def open_loan(book, reader, today):
    return Loan(book=book, reader=reader, start=today, due=today + timedelta(days=LOAN_DAYS))


def days_late(loan, today):
    end = loan.returned or today
    return max(0, (end - loan.due).days)


def fine(loan, today):
    return round(days_late(loan, today) * FINE_PER_DAY, 2)
