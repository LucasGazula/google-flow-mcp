"""Saldo da interface: agrupamentos de milhares e formatos inconclusivos."""

import unittest

from flow_credits import parse_credit_count, parse_http_credits


class CreditsTest(unittest.TestCase):
    def test_http_balance_rejects_unknown_and_keeps_zero(self):
        for balance in (0, 946, 1050):
            self.assertEqual(parse_http_credits([balance,1,2,2,None,balance,None]),balance)
        self.assertEqual(parse_http_credits([946,1,2,2,None,946,None,"campo novo"]), 946)
        for payload in (None, {}, [], [946], [-1,1,2,2,None,0,None],
                        [True,1,2,2,None,0,None], ["946",1,2,2,None,0,None]):
            with self.assertRaises(ValueError):
                parse_http_credits(payload)

    def test_observed_localized_balances(self):
        for label, expected in (
            ("1.050 créditos do Google Flow", 1050),
            ("1,050 Google Flow credits", 1050),
            ("1\u202f050 crédits", None),
            ("1\u00a0050 créditos do Google Flow", 1050),
            ("0 créditos do Google Flow", 0),
            ("1.000.000 créditos do Google Flow", 1000000),
        ):
            if expected is None:
                with self.assertRaises(ValueError):
                    parse_credit_count(label)
            else:
                self.assertEqual(parse_credit_count(label), expected)
        for label in ("50 additional Flow credits daily", "-1 Google Flow credits",
                      "1.5 Google Flow credits", "1,000.000 Google Flow credits", "", "Unlimited"):
            with self.assertRaises(ValueError):
                parse_credit_count(label)


if __name__ == "__main__":
    unittest.main()
