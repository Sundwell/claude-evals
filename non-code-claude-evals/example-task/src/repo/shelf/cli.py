"""Command line of the library: python -m shelf.cli <command> <loan file>."""
import json
import sys
from datetime import date

from shelf.loans import Loan, fine


def load(path):
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return Loan(book=raw["book"], reader=raw["reader"], start=date.fromisoformat(raw["start"]),
                due=date.fromisoformat(raw["due"]),
                returned=date.fromisoformat(raw["returned"]) if raw.get("returned") else None)


def main(argv):
    cmd, path = argv[1], argv[2]
    loan = load(path)
    today = date.today()
    if cmd == "fine":
        print(f"{loan.reader} owes {fine(loan, today):.2f} EUR for {loan.book}")
    else:
        sys.exit(f"unknown command {cmd}")


if __name__ == "__main__":
    main(sys.argv)
