# CSV cleaning and reports

Clean selected CSV columns, save the cleaned data, and review a report of what
changed. You choose each column's cleaning rule; the program does not automatically
decide whether a column contains names, dates, numbers, or identifiers.

The reusable API is `clean_csv()` in `src/clean_csv.py`. The script runs it through
`main()` and `clean()`. Paths and options are supplied through Python function
calls. The script does not read command-line options such as `--input_path`.

## Setup

Use Python 3.10 or newer. Run these commands from the project root in Windows
PowerShell.

For a fresh environment:

```powershell
py -3 -m venv .pvenv
```

Install the dependencies using that environment's Python:

```powershell
.\.pvenv\Scripts\python.exe -m pip install pandas python-dateutil titlecase word2number regex
```

`requirements.txt` is currently empty, so installing from it alone will not install
these dependencies. Activating the environment is optional when using the full
interpreter path shown above.

## Run the included sample

```powershell
.\.pvenv\Scripts\python.exe -B src\clean_csv.py
```

The script runs `main()`, which calls `clean()`. That function selects the input
and cleaning rules, calls `clean_csv()`, saves the detailed report, and prints the
summary.

The bundled configuration uses `data/test_samples/01_messy_sales.csv`. Its
default outputs are saved beside the input:

- `01_messy_sales_cleaned.csv`: cleaned data.
- `01_messy_sales_report.csv`: changes, missing cells, invalid values, and removed
  duplicate rows.

To change the bundled run, edit `CSV_PATH` and the options passed inside `clean()`.
For another program or a future UI, call `clean_csv()` directly as shown below.

The current `clean()` configuration trims all 11 sales columns, applies name
capitalization to `customer`, `region`, `item`, `payment_method`, `status`, and
`notes`, parses `sale_date`, and cleans `units`, `unit_price`, and `discount_pct`.
That capitalization also changes acronyms and free text, such as `UPI` to `Upi`.
Choose the `names` columns carefully; the direct-call example below limits it to
customers and regions so product names, payment labels, statuses, and notes are
only trimmed. There is no payment-label mapping or `smart_title()` rule built in.

## Use the function directly

Run this code from the project root, for example in a Python session or a script
that can import the `src` directory:

```python
from pathlib import Path
from src.clean_csv import clean_csv, print_report, save_report

report = clean_csv(
    csv_path=Path("data/test_samples/01_messy_sales.csv"),
    has_headers=True,
    trailing_spaces=list(range(11)),
    names=["customer", "region"],
    dates=["sale_date"],
    numbers=["units", "unit_price", "discount_pct"],
    digit_separator=",",
    remove_duplicates=True,
    date_input_format=None,
    day_first_output=True,
)

report_path = save_report(report)
print_report(report, report_path)
```

`clean_csv()` saves the cleaned CSV and returns a `Report`. It does not print the
summary or save the report CSV itself:

- Call `save_report(report)` to write the detailed report and receive its path.
- Call `print_report(report, report_path)` to print the summary and both output
  paths. The report path is optional when no detailed report has been saved.
- Use the returned `Report` directly when another application needs the results.

## Column selection and options

Each cleaning option accepts a list of header names, zero-based column positions,
or a mixture of the two. For example, `names=["customer", 3]` selects the
named column and the fourth column.

| Option | Default | Behavior |
| --- | --- | --- |
| `csv_path` | Required | Path to the input CSV. |
| `has_headers` | `True` | Uses the first record as column names. Set to `False` when the file has no header. |
| `trailing_spaces` | `None` | Trims leading and trailing whitespace in the listed columns. |
| `names` | `None` | Lowercases text before applying name capitalization; tokens containing `@` remain lowercase. |
| `dates` | `None` | Parses dates in the listed columns and writes `DD/MM/YYYY` text. |
| `numbers` | `None` | Parses and formats values in the listed numeric columns. |
| `digit_separator` | `","` | Output grouping for numbers. Use `","`, `"_"`, or `""` for no grouping. |
| `remove_duplicates` | `True` | Removes exact duplicate rows after cleaning and keeps the first occurrence. |
| `date_input_format` | `None` | Uses automatic date parsing. Supply a format for a known, consistent input layout. |
| `day_first_output` | `True` | Prefers day-first interpretation of ambiguous input dates when no input format is supplied. |
| `output_path` | `None` | Saves beside the input as `<input_stem>_cleaned.csv`; supply a path to change this. |

`None` or an empty list skips a cleaning rule. Column position `0` is valid.
Columns without a selected cleaning rule keep their parsed values. Pandas still
recognizes default missing-value tokens such as `NA`, `NULL`, and `N/A` throughout
the input, including unselected columns. Removing duplicate rows applies to the
whole dataset when enabled. Keep identifiers, phone numbers, and postal codes out
of `numbers` if their leading zeros and original formatting must be preserved.

### Headerless CSVs

Use `has_headers=False` and column positions. This example assumes a file whose
first three columns contain a name, a date, and an amount:

```python
report = clean_csv(
    csv_path=Path("data/no_headers.csv"),
    has_headers=False,
    trailing_spaces=[0, 1, 2],
    names=[0],
    dates=[1],
    numbers=[2],
)
```

Pandas assigns numeric column labels starting at `0`. The current export writes
those labels as a header row in the cleaned output, including for headerless
input. The input setting does not disable output headers.

### Dates

`date_input_format` describes the **input**, including its literal separators:

- `%d/%m/%Y` matches `03/04/2026` as 3 April 2026.
- `%m/%d/%Y` matches `03/04/2026` as March 4, 2026.
- `%Y-%m-%d` matches `2026-04-03`.

For mixed input layouts, leave `date_input_format=None`. Automatic parsing accepts
common numeric and month-name dates, prefers day-first input by default, and
preserves year-first interpretation for values such as `2026-04-03`. Parsing that
fails produces `N/A` and an invalid-date report entry.

Despite its name, **`day_first_output` controls input interpretation**, not the
output layout. Set it to `False` to prefer month-first ambiguous input. An explicit
`date_input_format` takes precedence. The cleaner's date output is `DD/MM/YYYY`.
Automatic parsing can fill missing components of incomplete dates; use an explicit
input format when complete dates must match a known layout.

### Numbers and names

Numeric cleaning uses a decimal point and treats commas as grouping separators.
With the default `digit_separator=","`, `1234` becomes `1,234` and `1234.5` becomes
`1,234.50`. Float output uses two decimal places when grouping is enabled. An empty
separator disables that formatting step. Negative signs are preserved.

Values are read as strings, and numeric results are saved as formatted strings.
This preserves integer/decimal presentation rather than creating Python numeric
types in the output CSV. Formatting can change the original decimal precision.

The numeric helper first tries `word2number`, so `two` becomes `2` and `ten`
becomes `10`. If that fails, it trims whitespace, removes the first recognized
currency symbol, code, or name, rejects remaining letters, and validates the
whole remaining numeric string before removing commas. This accepts an optional
leading `+` or `-`, digits, optional three-digit comma grouping, and an optional
decimal part with digits on both sides of the decimal point.

| Input | Result with `digit_separator=","` |
| --- | --- |
| `1,499.00` | `1,499.00` |
| `INR 1299` | `1,299` |
| `₹12,999.00` | `12,999.00` |
| `-2` | `-2` |
| `two` | `2` |
| `2O99` (letter O) | Invalid number; saved as `N/A`. |
| `1,2,99` | Invalid number; saved as `N/A`. |
| `12/50` or `12..50` | Invalid number; saved as `N/A`. |

Currency detection uses the `regex` package for Unicode currency symbols and a
fixed list of currency codes and names. It removes currency text, but does not
convert between currencies or record currency units. Codes and names require word
boundaries: `INR 1299` is supported, while `INR1299` is not. Scientific notation,
decimal-comma amounts, Indian-style comma grouping, accounting parentheses, `.5`,
and `5.` are not supported by the numeric-format validator. The initial
`word2number` attempt is permissive and can ignore additional non-number words.

Name cleaning lowercases the input, then uses `titlecase`. Tokens containing `@`
remain lowercase, which helps normalize email-like text, but the function does
not validate email addresses. Acronyms such as `UPI` are not preserved reliably.
Use this rule for names, trim free-text notes without changing their case, and
handle category labels with a separate mapping if consistent labels are needed.

### Sales sample coverage and remaining rules

With the current `clean()` configuration, the included sales sample produces:

- 34 input records and 32 cleaned records, after removing two exact duplicates.
- 15 missing cells in selected columns.
- Seven invalid values: three dates and four numbers.

The invalid numbers are `free` (INV-2016), `12..50` (INV-2017), `2O99`
(INV-2018), and `1,2,99` (INV-2028). The invalid dates are `2026-02-30`,
`2026-13-10`, and `not-a-date`. Each is replaced with `N/A` and included in the
report; worded quantities and discounts now convert successfully.

The cleaner normalizes formats but does not enforce sales business rules:

- Discounts `110` and `-5` remain valid numbers; no 0–100 range is enforced.
- Fractional units such as `1.5` are accepted; no integer-only rule is enforced.
- Unknown payment methods and statuses such as `barter` and `maybe` are not flagged.
- Negative quantities and prices are preserved, allowing returns and credits.
- Conflicting records sharing an invoice ID are retained unless every cleaned
  column matches. There is no invoice-ID reconciliation or case normalization.
- `03/04/2026` is interpreted as 3 April under the default day-first setting;
  the intended date cannot be inferred from that value alone.

Other inputs are in `data/test_samples/02_adversarial_customers.csv` and
`data/test_samples/03_messy_inventory.csv`. Select rules for their own headers;
the positional configuration in `clean()` is specific to the sales schema.
`04_malformed_unclosed_quote.csv` tests a file-level parsing failure: pandas
raises `ParserError` before cleaning starts, and no cleaning report is returned.

## How cleaning and reporting work

1. Read the CSV as strings and remember original record positions.
2. Process selected columns in this order: whitespace, names, dates, then numbers.
3. Record actual changes, retaining the value before the first action and the
   final cleaned value. Multiple actions on one cell are combined in one entry.
4. Record missing cells once across overlapping cleaners. Existing missing cells
   stay missing; whitespace-only cells in selected columns are marked as missing.
5. Mark invalid dates and unparseable numbers as `N/A`, record the issue, and
   continue processing. Missing cells and invalid values are counted separately.
6. Optionally remove exact duplicate cleaned rows. Every cleaned column must
   match; a shared identifier alone does not make two rows duplicates.
7. Save the cleaned CSV without a pandas index column and return the `Report`.

The original input is preserved. Custom output directories must already exist.
The input, cleaned output, and report must use different paths. Re-running with
the same output paths replaces the previous outputs.

To choose custom paths:

```python
report = clean_csv(
    csv_path=Path("data/test_samples/01_messy_sales.csv"),
    dates=["sale_date"],
    output_path=Path("data/test_samples/custom_cleaned.csv"),
)
report_path = save_report(report, Path("data/test_samples/custom_report.csv"))
print_report(report, report_path)
```

## Read the results

### Terminal summary

`print_report()` shows record counts before and after cleaning, duplicates removed,
edited columns, missing cells in selected columns, invalid values, and output
paths. Unselected missing cells are not included in the missing-cell count.

### Detailed report CSV

The report uses UTF-8 with a byte-order mark for spreadsheet compatibility. It
has these columns:

| Column | Meaning |
| --- | --- |
| `record` | Original data record, starting at 1, before duplicate removal. |
| `row` | Original record position plus one if the input has a header. |
| `column` | Header name, or zero-based column label for headerless input. Blank for a removed duplicate row. |
| `original_value` | Value before the first cleaning action on that cell. |
| `cleaned_value` | Final cleaned value. Blank for missing cells or a whole-row duplicate entry. |
| `issue` | Normalized value, missing value, invalid date, invalid number, or duplicate row. |
| `action` | Action taken; multiple actions on the same cell are combined. |

`record` is the reliable reference to a parsed data record. `row` is a
header-adjusted record position, **not a guaranteed physical file line number**:
skipped blank lines and quoted multiline records can change that relationship.

Entries for records removed as duplicates remain in the report so their original
positions can be reviewed. A run with no issues still saves the report headers.

### Returned `Report` object

| Attribute | Meaning |
| --- | --- |
| `b_rows`, `a_rows` | Number of data records before and after cleaning. |
| `duplicates_removed` | Difference between the before and after counts. |
| `edited_columns` | Columns whose values actually changed. |
| `missing_values` | Unique `MissingPosition(row, col)` entries for selected columns. |
| `invalid_values` | Number of invalid-date and invalid-number entries. |
| `edits` | Human-readable action counts. |
| `issues` | Detailed `CleaningIssue` entries used for the report CSV. |
| `input_path`, `output_path` | Input and cleaned-output paths. |

## Tests

The report tests are in `tests/test_clean_csv_report.py`. They currently import and
call the former function name `clean_csv2`. Those references need to be changed to
`clean_csv` before the suite can run against the current API.

After that test update, run from the project root:

```powershell
.\.pvenv\Scripts\python.exe -B -m unittest discover -s tests -v
```

The checks cover report counts, original values, missing cells, headerless input,
invalid numbers, duplicate removal, empty reports, and output-path protection.
