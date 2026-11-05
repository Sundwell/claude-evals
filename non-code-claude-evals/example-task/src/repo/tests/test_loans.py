import unittest
from datetime import date

from shelf.loans import fine, open_loan


class FineTest(unittest.TestCase):
    def test_no_fine_before_due(self):
        loan = open_loan("Dune", "ana", date(2026, 3, 1))
        self.assertEqual(fine(loan, date(2026, 3, 10)), 0)

    def test_fine_per_day(self):
        loan = open_loan("Dune", "ana", date(2026, 3, 1))
        self.assertEqual(fine(loan, date(2026, 3, 26)), 1.0)
