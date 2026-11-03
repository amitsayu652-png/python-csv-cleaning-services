import unittest

from src.clean_csv import normalize_dates, normalize_name, normalize_numeric_values


class NumericTests(unittest.TestCase):
    def test_exact_decimal_precision_and_integer_size(self):
        for value in ("0.12345678901234567890", "9007199254740993", "99.999999", "0.00"):
            with self.subTest(value=value):
                self.assertEqual(normalize_numeric_values(value, separator=""), value)

    def test_currency_words_signs_and_scientific_notation(self):
        cases = {
            "INR1299": "1299",
            "₹12,999.00": "12999.00",
            "$-25.00": "-25.00",
            "-$25": "-25",
            "two": "2",
            "ten": "10",
            "1e3": "1000",
            "1.25e-2": "0.0125",
            "(1,299.50)": "-1299.50",
            "-2": "-2",
            ".5": "0.5",
            "5.": "5",
            "1299 INR": "1299",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(normalize_numeric_values(value, separator=""), expected)

    def test_auto_locale_does_not_strip_decimal_commas(self):
        cases = {
            "1\u202f299,50": "1299.50",
            "1.299,50": "1299.50",
            "12,50": "12.50",
            "1,299.50": "1299.50",
            "1,299": "1299",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(normalize_numeric_values(value, separator="", decimal_mark="auto"), expected)

    def test_explicit_locale_resolves_ambiguous_amounts(self):
        self.assertEqual(normalize_numeric_values("1,234", separator="", decimal_mark=","), "1.234")
        self.assertEqual(normalize_numeric_values("1,234", separator="", decimal_mark="."), "1234")

    def test_bad_letters_punctuation_and_nonfinite_numbers_are_rejected(self):
        for value in (
            "2O99",
            "$2O99",
            "INR 12R99",
            "1,2,99",
            "12/50",
            "12..50",
            "Infinity",
            "NaN",
            "1e",
            "two apples",
            "two 2O99",
            "(1)-",
            "1e1001",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_numeric_values(value, decimal_mark="auto")

    def test_rounding_requires_explicit_precision(self):
        self.assertEqual(normalize_numeric_values("99.999999", separator=""), "99.999999")
        self.assertEqual(normalize_numeric_values("99.999999", separator="", decimal_places=2), "100.00")
        self.assertEqual(normalize_numeric_values("1234.567", separator="_"), "1_234.567")


class DateAndNameTests(unittest.TestCase):
    def test_complete_mixed_date_formats(self):
        for value in ("2026-10-04", "2026/10/04", "04-10-2026", "4 Oct 2026", "October 4, 2026"):
            with self.subTest(value=value):
                self.assertEqual(normalize_dates(value), "04/10/2026")

    def test_incomplete_and_impossible_dates_are_not_invented(self):
        for value in ("10/2026", "October 2026", "2026-02-29", "2026-02-30", "2026-13-10", "not-a-date"):
            with self.subTest(value=value):
                self.assertEqual(normalize_dates(value), "N/A")
        self.assertEqual(normalize_dates("2024-02-29"), "29/02/2024")

    def test_explicit_format_day_order_and_named_output(self):
        self.assertEqual(normalize_dates("03/04/2026", day_first_output=False), "04/03/2026")
        self.assertEqual(normalize_dates("03/04/2026", input_format="%m/%d/%Y"), "04/03/2026")
        self.assertEqual(normalize_dates("2026-10-04", output_format="%d %B %Y"), "04 October 2026")
        self.assertEqual(normalize_dates("10/2026", input_format="%m/%Y"), "N/A")

    def test_names_handle_unicode_whitespace(self):
        self.assertEqual(normalize_name("  AARAV\u00a0SHARMA  "), "Aarav Sharma")
        self.assertEqual(normalize_name("Nisha\u200b Kapoor"), "Nisha Kapoor")
        self.assertEqual(normalize_name("JOSÉ ÁLVAREZ"), "José Álvarez")
        self.assertEqual(normalize_name("李小龙"), "李小龙")


if __name__ == "__main__":
    unittest.main()
