import contextlib
import csv
import io
import tempfile
import unittest
from pathlib import Path

from src.clean_csv import ColumnRule, clean_csv, save_report
from src.sample_configs import SAMPLE_CONFIGS, SAMPLES, run_sample


class RulesAndSamplesTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def source(self, content):
        path = self.root / "input.csv"
        path.write_text(content, encoding="utf-8")
        return path

    def read(self, path):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    def sample(self, name):
        with contextlib.redirect_stdout(io.StringIO()):
            report = run_sample(name, self.root)
        return report, self.read(report.output_path) if report.output_path else []

    def test_sales_regression(self):
        report, rows = self.sample("sales")
        by_id = {row["invoice_id"]: row for row in rows}
        self.assertEqual((report.b_rows, report.a_rows, report.duplicates_removed), (34, 32, 2))
        self.assertEqual(by_id["INV-2005"]["units"], "2")
        self.assertEqual(by_id["INV-2028"]["discount_pct"], "10")
        for invoice in ("INV-2016", "INV-2017", "INV-2018", "INV-2028"):
            self.assertEqual(by_id[invoice]["unit_price"], "N/A")
        for invoice in ("INV-2020", "INV-2021"):
            self.assertEqual(by_id[invoice]["discount_pct"], "N/A")
        self.assertEqual(by_id["INV-2015"]["units"], "N/A")
        self.assertEqual(by_id["INV-2013"]["units"], "-2")
        self.assertEqual(by_id["INV-2023"]["unit_price"], "-1,299")
        self.assertEqual(by_id["INV-2001"]["payment_method"], "UPI")
        self.assertEqual(by_id["INV-2001"]["notes"], "Regular order")
        self.assertEqual(by_id["INV-2022"]["status"], "N/A")
        self.assertEqual(report.conflicts, 2)
        self.assertTrue(any(issue.issue == "Ambiguous date" for issue in report.issues))
        self.assertTrue(any("grouping" in issue.reason for issue in report.issues))

    def test_customers_regression_precision_identifiers_and_multiline_fields(self):
        report, rows = self.sample("customers")
        by_id = {row["customer_id"]: row for row in rows}
        self.assertEqual(report.status, "success")
        self.assertIn("000001", by_id)
        self.assertIn("9007199254740993", by_id)
        self.assertEqual(by_id["000001"]["postal_code"], "00123")
        self.assertEqual(by_id["9007199254740993"]["phone"], "0086 13800138000")
        self.assertEqual(by_id["C-004"]["notes"].splitlines(), ["Address line one", "Address line two"])
        for invoice in ("C-005", "C-006", "C-007"):
            self.assertEqual(by_id[invoice]["account_balance"], "1,299.50")
        self.assertEqual(by_id["C-012"]["account_balance"], "1,000")
        self.assertEqual(by_id["C-013"]["account_balance"], "-1,299.50")
        self.assertEqual(by_id["C-014"]["account_balance"], "12.50")
        self.assertEqual(by_id["C-015"]["signup_date"], "N/A")
        self.assertEqual(by_id["C-018"]["signup_date"], "18/10/2026")
        self.assertEqual(by_id["C-019"]["email"], "N/A")
        self.assertEqual(by_id["C-019"]["account_balance"], "99.999999")
        self.assertEqual(by_id["C-020"]["account_balance"], "0.12345678901234567890")
        self.assertEqual(by_id["C-009"]["postal_code"], "NA")
        self.assertEqual(by_id["C-022"]["notes"], "=1+1")
        self.assertEqual(by_id["C-007"]["full_name"], "Nisha Kapoor")
        self.assertEqual(report.conflicts, 2)

    def test_inventory_regression(self):
        report, rows = self.sample("inventory")
        by_id = {row["sku"]: row for row in rows}
        self.assertEqual((report.b_rows, report.a_rows, report.duplicates_removed), (18, 17, 1))
        self.assertEqual(by_id["SKU-002"]["warehouse"], "WH-B")
        self.assertEqual(by_id["SKU-002"]["description"], "desk LAMP")
        self.assertEqual(by_id["SKU-004"]["stock_on_hand"], "N/A")
        self.assertEqual(by_id["SKU-005"]["stock_on_hand"], "N/A")
        self.assertEqual(by_id["SKU-009"]["reorder_level"], "N/A")
        self.assertEqual(by_id["SKU-010"]["cost_inr"], "N/A")
        self.assertEqual(by_id["SKU-014"]["stock_on_hand"], "1,000")
        self.assertEqual(by_id["SKU-014"]["cost_inr"], "12.50")
        self.assertEqual(by_id["SKU-013"]["discontinued"], "N/A")
        self.assertEqual(len([row for row in rows if row["sku"] == "000045"]), 2)
        self.assertEqual(report.conflicts, 0)

    def test_malformed_file_has_failure_report_and_no_partial_export(self):
        sentinel = self.root / "04_malformed_unclosed_quote_cleaned.csv"
        sentinel.write_text("previous output", encoding="utf-8")
        report, rows = self.sample("malformed")
        self.assertEqual(report.status, "failed")
        self.assertIsNone(report.output_path)
        self.assertEqual(rows, [])
        self.assertEqual(report.issues[0].record, 2)
        self.assertEqual(report.issues[0].row, 3)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "previous output")
        saved = self.read(self.root / "04_malformed_unclosed_quote_report.csv")
        self.assertEqual(saved[0]["issue"], "File error")
        self.assertTrue(saved[0]["reason"])

    def test_source_fixtures_are_never_modified(self):
        before = {
            config.filename: (SAMPLES / config.filename).read_bytes() for config in SAMPLE_CONFIGS.values()
        }
        for name in SAMPLE_CONFIGS:
            self.sample(name)
        self.assertEqual(before, {name: (SAMPLES / name).read_bytes() for name in before})

    def test_actual_physical_line_numbers_with_blank_and_multiline_records(self):
        path = self.source('name,note\n\nalice,"one\ntwo"\nBOB,end\n')
        report = clean_csv(path, names=["name"])
        positions = {(issue.record, issue.row) for issue in report.issues}
        self.assertEqual(positions, {(1, 3), (2, 5)})

    def test_literal_missing_tokens_preserved_unless_configured(self):
        path = self.source("id,name\nNA,NULL\n00123,NA\n")
        report = clean_csv(path, trim_all=True, rules={"name": ColumnRule("name", missing_tokens=("NULL",))})
        rows = self.read(report.output_path)
        self.assertEqual(rows[0], {"id": "NA", "name": ""})
        self.assertEqual(rows[1]["id"], "00123")
        self.assertEqual(len(report.missing_values), 1)

    def test_headerless_output_remains_headerless(self):
        path = self.source("alice,000123\nBOB,000456\n")
        report = clean_csv(path, has_headers=False, rules={0: ColumnRule("name")})
        with report.output_path.open(newline="", encoding="utf-8") as stream:
            self.assertEqual(list(csv.reader(stream)), [["Alice", "000123"], ["Bob", "000456"]])

    def test_invalid_policy_keeps_original_but_records_failure_reason(self):
        path = self.source("amount\n2O99\n")
        report = clean_csv(path, numbers=[0], invalid_policy="keep")
        self.assertEqual(self.read(report.output_path)[0]["amount"], "2O99")
        self.assertEqual(report.invalid_values, 1)
        self.assertTrue(report.issues[0].reason)
        self.assertEqual(report.edited_columns, [])

    def test_explicit_rules_reject_ambiguous_dates_by_default(self):
        path = self.source("date\n03/04/2026\n")
        report = clean_csv(path, rules={"date": ColumnRule("date")})
        self.assertEqual(report.invalid_values, 1)
        self.assertIn("Ambiguous", report.issues[0].reason)

    def test_bad_schema_and_duplicate_headers_fail_before_writing(self):
        path = self.source("id,value\n1,2\n")
        for options in (
            {"numbers": [5]},
            {"names": ["missing"]},
            {"names": [-1]},
            {"rules": {"value": ColumnRule("category")}},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                clean_csv(path, **options)
        self.assertFalse((self.root / "input_cleaned.csv").exists())
        path.write_text("id,id\n1,2\n", encoding="utf-8")
        report = clean_csv(path)
        self.assertEqual(report.status, "failed")

    def test_required_values_and_delimiters(self):
        path = self.source("id;amount\n;12,50\n0001;2,50\n")
        report = clean_csv(
            path,
            delimiter=";",
            rules={"id": ColumnRule(required=True), "amount": ColumnRule("number", decimal_mark=",")},
            digit_separator="",
        )
        self.assertEqual(report.invalid_values, 1)
        with report.output_path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter=";"))
        self.assertEqual(rows[1], {"id": "0001", "amount": "2.50"})

    def test_failed_input_report_cannot_overwrite_source(self):
        path = self.source('name\n"unclosed\n')
        report = clean_csv(path)
        with self.assertRaises(ValueError):
            save_report(report, path)

    def test_invalid_keys_do_not_create_false_conflicts(self):
        path = self.source("id,note\nwrong,one\nwrong,two\n")
        report = clean_csv(path, rules={"id": ColumnRule("integer")}, unique_keys=["id"])
        self.assertEqual(report.invalid_values, 2)
        self.assertEqual(report.conflicts, 0)

    def test_empty_header_only_and_ragged_files(self):
        path = self.source("")
        self.assertEqual(clean_csv(path).status, "failed")
        path.write_text("id,name\n", encoding="utf-8")
        report = clean_csv(path, trim_all=True, unique_keys=["id"])
        self.assertEqual((report.b_rows, report.a_rows, report.status), (0, 0, "success"))
        path.write_text("id,name\n1,Alice,extra\n", encoding="utf-8")
        report = clean_csv(path)
        self.assertEqual(report.status, "failed")
        self.assertIn("Expected 2 fields; found 3", report.error)


if __name__ == "__main__":
    unittest.main()
