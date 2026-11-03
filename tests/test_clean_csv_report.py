import contextlib
import csv
import io
import tempfile
import unittest
from pathlib import Path

from src.clean_csv import Report, clean_csv, print_report, save_report


class CleaningReportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write_input(self, content, name="input.csv"):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def read_report(self, path):
        with path.open(newline="", encoding="utf-8-sig") as report_file:
            return list(csv.DictReader(report_file))

    def test_summary_and_audit_match_the_cleaned_data(self):
        content = (
            "name,date,amount,note\n"
            " alice ,2026-10-01,INR 799,keep\n"
            "alice,01/10/2026,799,keep\n"
            ",2026-10-02,,keep\n"
            "Bob,2026-02-30,free,keep\n"
        )
        source = self.write_input(content)
        report = clean_csv(source, trailing_spaces=[0, 1, 2], names=[0], dates=[1], numbers=[2])

        self.assertIsInstance(report, Report)
        self.assertEqual((report.b_rows, report.a_rows), (4, 3))
        self.assertEqual(report.duplicates_removed, 1)
        self.assertEqual(report.invalid_values, 2)
        self.assertEqual(report.edited_columns, ["name", "date", "amount"])
        self.assertEqual(
            {(position.row, position.col) for position in report.missing_values},
            {(4, "name"), (4, "amount")},
        )
        self.assertEqual(len(report.missing_values), 2)
        first_name = next(issue for issue in report.issues if issue.record == 1 and issue.column == "name")
        self.assertEqual(first_name.original_value, " alice ")
        self.assertEqual(first_name.cleaned_value, "Alice")
        self.assertIn("Trimmed whitespace", first_name.action)
        self.assertIn("Normalized name", first_name.action)
        duplicate = next(issue for issue in report.issues if issue.issue == "Duplicate row")
        self.assertEqual((duplicate.record, duplicate.row, duplicate.column), (2, 3, None))
        self.assertEqual(source.read_text(encoding="utf-8"), content)
        self.assertEqual(report.output_path.name, "input_cleaned.csv")
        with report.output_path.open(newline="", encoding="utf-8") as cleaned_file:
            cleaned_rows = list(csv.DictReader(cleaned_file))
        self.assertEqual(len(cleaned_rows), 3)
        self.assertEqual(cleaned_rows[0]["name"], "Alice")

        report_path = save_report(report)
        rows = self.read_report(report_path)
        self.assertEqual(report_path.name, "input_report.csv")
        self.assertEqual(len(rows), len(report.issues))
        self.assertEqual(
            list(rows[0]),
            ["record", "row", "column", "original_value", "cleaned_value", "issue", "action", "reason"],
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            print_report(report, report_path)
        self.assertIn("Rows: 4 -> 3", output.getvalue())
        self.assertIn("Duplicates removed: 1", output.getvalue())
        self.assertIn("Missing cells (selected columns): 2", output.getvalue())
        self.assertIn("Invalid values: 2", output.getvalue())
        self.assertIn(str(report_path), output.getvalue())

    def test_all_cleaners_track_missing_cells_once_with_headerless_input(self):
        source = self.write_input("alice,2026-10-01,123,00123\n,,,00999\n")
        report = clean_csv(
            source,
            has_headers=False,
            trailing_spaces=[0, 1, 2],
            names=[0],
            dates=[1],
            numbers=[2],
            remove_duplicates=False,
        )
        self.assertEqual(len(report.missing_values), 3)
        self.assertEqual(
            {(position.row, position.col) for position in report.missing_values},
            {(2, 0), (2, 1), (2, 2)},
        )
        missing = [issue for issue in report.issues if issue.issue == "Missing value"]
        self.assertEqual(len(missing), 3)
        self.assertTrue(all(issue.record == 2 and issue.row == 2 for issue in missing))

    def test_whitespace_only_values_are_reported_as_missing(self):
        source = self.write_input("name,tag\n   ,00123\n")
        report = clean_csv(source, trailing_spaces=[0], names=[0])
        self.assertEqual(len(report.missing_values), 1)
        self.assertEqual(len(report.issues), 1)
        self.assertEqual(report.issues[0].original_value, "   ")
        self.assertIsNone(report.issues[0].cleaned_value)
        self.assertEqual(report.edited_columns, ["name"])

    def test_invalid_numbers_are_reported_without_stopping_other_rows(self):
        source = self.write_input("amount\n1.2.3\n123.50\n")
        report = clean_csv(source, numbers=[0])
        self.assertEqual(report.invalid_values, 1)
        invalid = next(issue for issue in report.issues if issue.issue == "Invalid number")
        self.assertEqual((invalid.record, invalid.original_value, invalid.cleaned_value), (1, "1.2.3", "N/A"))
        self.assertEqual(report.a_rows, 2)

    def test_no_issues_still_saves_a_csv_header(self):
        source = self.write_input("name\nAlice\n")
        report = clean_csv(source, names=[0])
        self.assertEqual(report.issues, [])
        self.assertEqual(report.edited_columns, [])
        path = save_report(report)
        self.assertTrue(path.read_text(encoding="utf-8-sig").startswith("record,row,column,"))
        self.assertEqual(self.read_report(path), [])

    def test_output_and_report_cannot_overwrite_the_input_or_each_other(self):
        content = "name\nalice\n"
        source = self.write_input(content)
        with self.assertRaises(ValueError):
            clean_csv(source, output_path=source)
        report = clean_csv(source, names=[0])
        for path in (source, report.output_path):
            with self.subTest(path=path), self.assertRaises(ValueError):
                save_report(report, path)
        self.assertEqual(source.read_text(encoding="utf-8"), content)

    def test_duplicate_removal_can_be_disabled(self):
        source = self.write_input("name\nAlice\nAlice\n")
        report = clean_csv(source, names=[0], remove_duplicates=False)
        self.assertEqual((report.b_rows, report.a_rows), (2, 2))
        self.assertEqual(report.duplicates_removed, 0)
        self.assertEqual(report.issues, [])


if __name__ == "__main__":
    unittest.main()
