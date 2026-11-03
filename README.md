# CSV cleaner with audit reports

A Python project for cleaning CSV files with explicit column rules. Normalize
names, dates, numbers, emails, booleans, and category labels while preserving
identifiers and keeping a report of changes and invalid values.

Column types are chosen by the caller. The cleaner does not guess whether a
number-looking field is an ID, phone number, amount, or date.

## Setup

Requires Python 3.10 or newer. From the repository root in Windows PowerShell:

```powershell
py -3 -m venv .pvenv
.\.pvenv\Scripts\python.exe -m pip install -r requirements.txt
.\.pvenv\Scripts\python.exe -B src\clean_csv.py
```

On macOS or Linux, create the environment with `python3 -m venv .pvenv` and use
`.pvenv/bin/python` in place of `.\.pvenv\Scripts\python.exe`.

The default run cleans the sales sample. It prints a summary and writes
`01_messy_sales_cleaned.csv` and `01_messy_sales_report.csv` under `data/output/`.
Input samples are never overwritten. Generated outputs and private data are
ignored by Git. Running a sample again replaces its previous generated outputs.

There are no command-line arguments. Configure the Python functions directly.

## Run the test samples

From a Python session at the repository root:

```python
from src.sample_configs import run_sample

report = run_sample("sales")
# Other presets: "customers", "inventory", "malformed"
```

Or run all four:

```powershell
.\.pvenv\Scripts\python.exe -B -c "from src.sample_configs import SAMPLE_CONFIGS, run_sample; [run_sample(name) for name in SAMPLE_CONFIGS]"
```

Presets live in `src/sample_configs.py`. Each declares types and validation rules
for that file's headers; the engine itself has no sales-specific assumptions.
`run_sample(name, output_dir=...)` accepts a different output directory and creates
it if necessary.

| Sample | Input → output records | Duplicates removed | Missing cells | Invalid cells | Records with conflicting keys |
| --- | --- | --- | --- | --- | --- |
| Sales | 34 → 32 | 2 | 15 | 12 | 2 |
| Customers | 24 → 24 | 0 | 40 | 6 | 2 |
| Inventory | 18 → 17 | 1 | 6 | 11 | 0 |
| Malformed quote | File failure | — | — | — | — |

Counts are for the checked-in fixtures and presets. Missing and invalid counts
refer to original records, including records later removed as duplicates. A
missing required value counts as both missing and invalid.

The malformed sample deliberately has an unclosed quote. Its run saves a failed
report and writes no cleaned CSV; it does not guess how to repair the file. An
older cleaned file, if present at that output path, is left untouched and is not
listed as an output of the failed run.

## Clean another CSV

```python
from pathlib import Path
from src.clean_csv import ColumnRule, clean_csv, print_report, save_report

report = clean_csv(
    csv_path=Path("data/test_samples/01_messy_sales.csv"),
    output_path=Path("data/test_samples/example_cleaned.csv"),
    trim_all=True,
    rules={
        "invoice_id": ColumnRule("text", required=True),
        "customer": ColumnRule("name"),
        "sale_date": ColumnRule("date", ambiguous_dates="day_first"),
        "units": ColumnRule("integer"),
        "unit_price": ColumnRule("number"),
        "discount_pct": ColumnRule("number", minimum=0, maximum=100),
        "payment_method": ColumnRule("category", choices={"upi": "UPI", "card": "Card", "cash": "Cash"}),
    },
    unique_keys=["invoice_id"],
)

report_path = save_report(report)
print_report(report, report_path)
if report.status == "failed":
    print(report.error)
```

`clean_csv()` saves the cleaned CSV and returns a `Report`. It does not save or
print the audit automatically; use `save_report()` and `print_report()` as above.
For custom paths, their parent directories must already exist. The source,
cleaned output, and report must have different paths.

Header names or zero-based positions can be used as selectors. For headerless
files, use `has_headers=False` and positions such as `rules={0: ColumnRule("name")}`.
Headerless input stays headerless on export by default. Set `output_headers=True`
to add numeric column labels if desired. Duplicate or blank input headers are
rejected rather than silently renamed.

## Column rules

| `kind` | Behavior |
| --- | --- |
| `text` | Preserves text; optionally trims its boundaries. Use for IDs, phones, postal codes, notes, and product descriptions. |
| `name` | Normalizes human-name capitalization and Unicode whitespace. Avoid this rule for acronyms, notes, and product codes. |
| `email` | Trims, lowercases, and performs a basic address-shape check. Does not check deliverability. |
| `date` | Requires a complete day, month and four-digit year; normalizes the output layout. |
| `number` | Parses amounts with `Decimal`, retaining source decimal precision unless rounding is requested. |
| `integer` | Requires a whole number; accepts scientific notation when its value is integral. |
| `boolean` | Maps true/false, yes/no, y/n and 1/0 to `true` or `false`, ignoring case. |
| `category` | Uses a case-insensitive `choices` mapping; unknown labels are flagged. |

| Rule option | Default | Purpose |
| --- | --- | --- |
| `trim` | `True` | Trim leading and trailing whitespace before normalization. |
| `required` | `False` | Flag a missing value as invalid. |
| `missing_tokens` | `()` | Extra missing tokens for this column, matched case-insensitively. |
| `decimal_mark` | `"."` | Numeric decimal convention: `"."`, `","`, or `"auto"`. |
| `decimal_places` | `None` | Preserve precision; an integer explicitly requests rounding and a fixed decimal scale. |
| `minimum`, `maximum` | `None` | Optional inclusive numeric bounds. String or `Decimal` bounds avoid float conversion. |
| `allow_words` | `True` | Permit English number words such as `two` and `ten`. |
| `input_format` | `None` | Explicit date input format such as `%m/%d/%Y`; it must describe a complete date. |
| `output_format` | `%d/%m/%Y` | Date output layout; for example `%Y-%m-%d` for ISO dates. |
| `ambiguous_dates` | `"reject"` | Reject ambiguous day/month input, or explicitly choose `"day_first"` or `"month_first"`. |
| `choices` | `None` | Required mapping for category rules, such as `{"upi": "UPI"}`. |

Only selected columns are normalized. `trim_all=True` additionally trims every
column without applying name casing or numeric conversion. Free text and quoted
multiline fields otherwise retain their content. Blank cells are missing; literal
tokens such as `NA`, `NULL`, and `N/A` remain text unless explicitly configured as
missing for a selected column. This preserves a postal code such as `NA`.

## Numeric parsing

Numeric strings are parsed with `Decimal`, not binary floating point. Signs,
scientific notation, accounting parentheses, common currency symbols/codes/names,
and valid three-digit grouping are supported. Currency markers are removed;
amounts are not converted between currencies. Unexpected letters, malformed
grouping, infinity, and NaN are rejected. Number words are checked before calling
`word2number`; arbitrary words mixed with digits are not silently discarded.

| Input | Result with the relevant rule |
| --- | --- |
| `INR 1299` or `INR1299` | `1,299` |
| `₹12,999.00` | `12,999.00` |
| `two` / `ten` | `2` / `10` |
| `1e3` | `1,000` |
| `(1,299.50)` | `-1,299.50` |
| `1.299,50` or `1 299,50` with `decimal_mark="auto"` | `1,299.50` |
| `12,50` with `decimal_mark=","` or `"auto"` | `12.50` |
| `0.12345678901234567890` | Precision retained, including the final zero. |
| `2O99`, `1,2,99`, `12/50`, `12..50` | Flagged as invalid. |

Auto locale mode is a documented heuristic: when both separators occur, the last
is treated as decimal; a comma-only value matching three-digit grouping is
treated as grouped integer, otherwise a single comma may be decimal. Thus
`1,234` means 1234 in auto mode. Choose `decimal_mark=","` to declare that it means
1.234. A dot-only value is treated as decimal. Indian-style grouping such as
`1,29,999` is not supported. Do not rely on auto mode for ambiguous conventions.

Output grouping is controlled by `digit_separator`: `","` (default), `"_"`, or
`""` for no grouping. Decimal output always uses a dot. `decimal_places=None`
preserves parsed scale; `decimal_places=2` explicitly rounds using Decimal's
round-half-even convention. Numeric results in a CSV are text representations,
not stored Python types. Parsing limits are 2000 input characters and an exponent
between -1000 and 1000.

The sales preset allows negative quantities and prices for returns/credits,
requires whole units, and bounds discounts to 0–100. The inventory preset rejects
negative stock, reorder levels, and costs. These are editable sample policies.

## Dates

Automatic date parsing accepts complete numeric dates, common English month-name
dates, and ISO dates/timestamps. Impossible dates and incomplete values such as
`10/2026` become invalid instead of borrowing today's day. Two-digit years are
not inferred in automatic mode.

A `ColumnRule("date")` rejects `03/04/2026` by default. The sample presets choose
day-first interpretation and also report such values as `Ambiguous date` so the
choice remains visible. An explicit `input_format` takes precedence.

Timestamp output uses the calendar date in the source offset, without timezone
conversion. The report explains that choice for offset-aware timestamps. Time
and offset are omitted by the default date-only output format; use an explicit
`output_format` to retain them. This is date normalization, not timezone inference.

## General options and compatibility

The original `trailing_spaces`, `names`, `dates`, and `numbers` lists are still
supported. New `rules` entries take precedence for the same column. The legacy
`day_first_output=True` parameter still controls **input** interpretation for the
legacy `dates` list; prefer a rule's `ambiguous_dates` for new configurations.

Other `clean_csv()` options include:

- `remove_duplicates=True`: remove exact duplicate normalized rows and keep the
  first. Sharing an ID alone never deletes a record.
- `unique_keys=[...]`: flag retained records with the same key and different
  contents. Supports composite keys such as SKU plus warehouse. Keys remain
  case-sensitive; conflicts are reported for review, not merged.
- `invalid_policy="mark"`: replace invalid values with `N/A`. Use `"keep"` to
  retain original invalid text and still report the failure.
- `missing_tokens=()`: additional missing tokens for all selected columns.
- `delimiter=","`, `encoding="utf-8-sig"`: explicit input dialect/encoding. UTF-8
  BOMs are accepted. Cleaned UTF-8 output is written without a BOM.
- `has_headers=True`, `output_headers=None`: use input headers and preserve their
  presence on output by default.
- `output_path=None`: by default, write `<input_stem>_cleaned.csv` beside the input.

Invalid column selectors and rule settings raise `ValueError`. File read and CSV
parse failures return `Report(status="failed")`, with no partial cleaned export.
Output write errors propagate to the caller. No automatic delimiter, header, type,
locale, currency-conversion, or timezone detection is performed beyond the
explicit numeric auto-locale option.

## Reports

`print_report()` shows success/failure, row counts, duplicates, changed columns,
missing and invalid cells, conflicting-key records, and generated paths.

`save_report(report, report_path=None)` writes a UTF-8 BOM CSV. Its columns are:

| Column | Meaning |
| --- | --- |
| `record` | Original parsed data record, starting at 1, before duplicate removal. |
| `row` | Physical line where that source record starts, accounting for headers, blank lines and quoted multiline fields. |
| `column` | Header name or zero-based label; blank for a whole-record/file issue. |
| `original_value` | Cell text before cleaning. |
| `cleaned_value` | Final text; blank for missing or whole-record/file issues. |
| `issue` | Normalization, missing/invalid value, ambiguous date, duplicate, key conflict, or file error. |
| `action` | Actions taken on the cell or record. |
| `reason` | Specific validation failure or explanation of a parsing decision. |

Entries for deleted duplicate records remain in the audit. A successful run with
no issues still writes report headers. File failures use the current record/start
line where available; `0` means a position could not be established.

The returned `Report` contains `b_rows`, `a_rows`, `duplicates_removed`,
`edited_columns`, `missing_values`, `invalid_values`, `conflicts`, `edits`,
`issues`, `input_path`, `output_path`, `status`, and `error`.

Literal spreadsheet formulas in free text are preserved as data, not evaluated by
this program. A spreadsheet application may interpret them when opening a CSV.

## Development

```powershell
.\.pvenv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.pvenv\Scripts\python.exe -m ruff check .
.\.pvenv\Scripts\python.exe -m ruff format --check .
.\.pvenv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Tests cover the four fixtures, exact numeric precision, locales, date ambiguity,
missing-token policies, physical source lines, validation, reports, duplicates,
conflicts, headerless files, and source-file protection. Test outputs use temporary
directories. GitHub Actions runs lint, formatting and tests on Windows and Linux
with Python 3.10 and 3.12. See `CONTRIBUTING.md` for contribution guidelines.

```text
src/clean_csv.py           General cleaner, helpers, rules, and reporting
src/sample_configs.py      Editable sample schemas and runner
data/test_samples/         Synthetic input fixtures (including one malformed file)
data/output/               Generated results; ignored by Git
data/private/              Local private inputs; ignored by Git
tests/                     Unit and fixture regression tests
requirements.txt           Runtime dependencies
requirements-dev.txt       Runtime dependencies plus development tools
```
