import pandas as pd
import re
import csv
import regex

from word2number import w2n
from pathlib import Path
from dateutil import parser
from titlecase import titlecase
from dataclasses import asdict, dataclass, field


ROOT_DIR = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT_DIR / "data" / "test_samples" / "01_messy_sales.csv"
MISSING_VALUE = "N/A"

@dataclass(frozen=True)
class MissingPosition:
    row:int 
    col:int | str

@dataclass(frozen=True)
class CleaningIssue:
    record: int
    row: int
    column: str | int | None
    original_value: str | None
    cleaned_value: str | None
    issue: str
    action: str


@dataclass(frozen=True)
class Report:
    b_rows: int = 0
    a_rows: int = 0
    edited_columns: list[str | int] = field(default_factory=list)
    missing_values: list[MissingPosition] = field(default_factory=list)
    edits: list[str] = field(default_factory=list)
    issues: list[CleaningIssue] = field(default_factory=list)
    input_path: Path | None = None
    output_path: Path | None = None

    @property
    def duplicates_removed(self) -> int:
        return self.b_rows - self.a_rows

    @property
    def invalid_values(self) -> int:
        return sum(issue.issue.startswith("Invalid ") for issue in self.issues)


def save_report(report: Report, report_path: Path | None = None) -> Path:
    if report_path is None:
        if report.input_path is None:
            raise ValueError("An input path or report path is required.")
        report_path = report.input_path.with_name(f"{report.input_path.stem}_report.csv")
    report_path = Path(report_path)
    for protected_path in (report.input_path, report.output_path):
        if protected_path is not None and report_path.resolve() == protected_path.resolve():
            raise ValueError("The report path must differ from the input and cleaned CSV paths.")

    columns = [
        "record", "row", "column", "original_value", "cleaned_value", "issue", "action"
    ]
    with report_path.open("w", newline="", encoding="utf-8-sig") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(asdict(issue) for issue in report.issues)
    return report_path


def print_report(report: Report, report_path: Path | None = None) -> None:
    print("CSV cleaning complete")
    print(f"Rows: {report.b_rows} -> {report.a_rows}")
    print(f"Duplicates removed: {report.duplicates_removed}")
    columns = ", ".join(str(column) for column in report.edited_columns) or "None"
    print(f"Edited columns: {columns}")
    print(f"Missing cells (selected columns): {len(report.missing_values)}")
    print(f"Invalid values: {report.invalid_values}")
    if report.output_path is not None:
        print(f"Cleaned CSV: {report.output_path}")
    if report_path is not None:
        print(f"Report CSV: {report_path}")


def normalize_name(name: str):
    name = name.lower()
    if "@" not in name:
        return titlecase(name)

    parts = []
    for part in name.split():
        if "@" in part:
            parts.append(part.lower())
        else:
            parts.append(titlecase(part))

    return " ".join(parts)


def has_currency(
    val: str,
):
    currency_symbols = r"\p{Sc}"
    currency_codes = r"\b(INR|USD|EUR|GBP|JPY|AUD|CAD|CHF|CNY|SGD|HKD|NZD|KRW|TWD|THB|VND|MYR|PHP|IDR|BDT|LKR|NPR|PKR|AED|SAR|EGP|NGN|ZAR|KES|GHS|ETB|TRY|ILS|PLN|CZK|HUF|RON|BGN|SEK|NOK|DKK|ISK|AUD|NZD)\b"
    currency_names   = r"\b(rupees?|dollars?|euros?|pounds?|yens?|francs?|pesos?|reais?|liras?|shekels?|zlotys?|forints?|crowns?|dirhams?|riyals?|bahts?|won|ringgits?|naira|cedis?|rand|shillings?)\b"

    currency_re = regex.compile(
        rf"(?:{currency_codes}|{currency_symbols}|{currency_names})",
        regex.IGNORECASE
    )

    match = None
    match_ob = currency_re.search(val)
    if match_ob is not None:
        match = match_ob.group(0)

    return bool(match), match

def normalize_numeric_values(
    val:str,  
    separator:str="_",
) -> str:

    if not isinstance(val, str):
        raise ValueError(
            "Input must be string."
        )

    result = None
    
    def _normalize_numbers(val:str):
        c_pattern = r"[+-]?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?"
        if not re.fullmatch(c_pattern, val):
            raise ValueError(f"Invalid numeric format: {val!r}")

        val = val.replace(",", "")
        if not val:
            return MISSING_VALUE

        conv = 0
        result = 0

        try:
            conv = int(val)
            result = conv

        except ValueError:        
                conv = float(val)
                result = conv

        return result

    try:
        x = w2n.word_to_num(val)
        result = x
    except ValueError:
        val = val.strip()

        currency_bool, sym = has_currency(val)
        if currency_bool and sym is not None:
            val = val.replace(sym, "", 1).strip()
            
        pattern = re.findall(
            r"[a-zA-Z]+", val
        )
        if pattern:
            raise ValueError(f"Invalid numeric value. Contains alphabets {pattern}")
            
        result = _normalize_numbers(val)

    if separator:
        if isinstance(result, int):
            result = f"{result:{separator}}"
        elif isinstance(result, float):
            result = f"{result:{separator}.2f}"

    return str(result)

        


def normalize_dates(
    val:str,
    output_format:str="%d/%m/%Y",
    separator:str="/",
    input_format:str | None=None,
    day_first_output:bool=True,
) -> str:
    if val is None:
        raise ValueError(
            "Input is none."
        )
    val = val.strip()
    if input_format is not None:
        date = pd.to_datetime(val, format=input_format, errors="coerce")
    else:
        year_first = re.match(r"^\d{4}(?:\D|$)", val) is not None
        try:
            date = parser.parse(
                val,
                dayfirst=day_first_output and not year_first,
                yearfirst=year_first,
            )
        except (ValueError, OverflowError):
            val = re.sub(r"[^\d]+", "/", val)
            if len(val.split("/")[0]) == 4:
                fmt = "%Y/%m/%d"
            else:
                fmt = "%d/%m/%Y" if day_first_output else "%m/%d/%Y"
            date = pd.to_datetime(val, format=fmt, errors="coerce")

    if pd.isna(date):
        return MISSING_VALUE
    
    date = date.strftime(output_format)
    date = re.sub(r"[^\d]+", separator, date)

    return date


def clean_csv(
    csv_path:Path,
    has_headers:bool=True,
    trailing_spaces:list[str | int] | None=None,
    names:list[str | int ] | None=None,
    dates:list[str | int] | None=None,
    numbers:list[str | int] | None=None,
    digit_separator:str=",",
    remove_duplicates:bool=True,
    date_input_format:str | None=None,
    day_first_output:bool=True,
    output_path:Path | None=None,
) -> Report:
    """Clean selected columns and return an audit report without printing it."""
    csv_path = Path(csv_path)
    output_path = (
        Path(output_path) if output_path is not None
        else csv_path.with_name(f"{csv_path.stem}_cleaned.csv")
    )
    if output_path.resolve() == csv_path.resolve():
        raise ValueError("The cleaned CSV path must differ from the input path.")

    if has_headers:
        df = pd.read_csv(csv_path, dtype="string")
        start_row = 2
    else:
        df = pd.read_csv(csv_path, dtype="string", header=None)
        start_row = 1

    before_rows = len(df)
    column_positions: dict[str | int, int] = {
        column: position for position, column in enumerate(df.columns)
    }
    source_records = {idx: number for number, idx in enumerate(df.index, start=1)}
    missing_values: list[MissingPosition] = []
    missing_positions: set[MissingPosition] = set()
    issues_by_cell: dict[tuple[int, str | int], CleaningIssue] = {}
    edited_columns: set[str | int] = set()
    edit_counts: dict[str, int] = {}

    def as_text(value) -> str | None:
        return None if pd.isna(value) else str(value)

    def record_issue(row, column, original, cleaned, issue, action):
        key = (row, column)
        previous = issues_by_cell.get(key)
        actions = previous.action.split("; ") if previous else []
        if action not in actions:
            actions.append(action)
        issues_by_cell[key] = CleaningIssue(
            record=row - start_row + 1,
            row=row,
            column=column,
            original_value=previous.original_value if previous else as_text(original),
            cleaned_value=as_text(cleaned),
            issue=previous.issue if previous and issue == "Normalized value" else issue,
            action="; ".join(actions),
        )

    def apply_change(idx, row, column, original, result, action, issue="Normalized value"):
        if as_text(original) == as_text(result):
            return
        df.loc[idx, column] = result
        edited_columns.add(column)
        edit_counts[action] = edit_counts.get(action, 0) + 1
        record_issue(row, column, original, result, issue, action)

    def is_missing(value) -> bool:
        return bool(pd.isna(value)) or (isinstance(value, str) and not value.strip())

    def record_missing(idx, row: int, column: str | int, value):
        position = MissingPosition(row=row, col=column)
        if position not in missing_positions:
            missing_values.append(position)
            missing_positions.add(position)
            action = "Left missing" if pd.isna(value) else "Marked blank cell as missing"
            record_issue(row, column, value, None, "Missing value", action)
        if not pd.isna(value):
            df.loc[idx, column] = pd.NA
            edited_columns.add(column)
            action = "Marked blank cell as missing"
            edit_counts[action] = edit_counts.get(action, 0) + 1

    def clean_whitespaces(column: str | int):
        if isinstance(column, str):
            column_name = column
        elif isinstance(column, int):
            column_name = df.columns[column]
        else:
            raise ValueError(
                "Column must be specified as a string or integer representing the index."
            )

        col_df = df[column_name]
        for row, (idx, val) in enumerate(col_df.items(), start=start_row):
            if is_missing(val):
                record_missing(idx, row, column_name, val)
                continue
            if not isinstance(val, str):
                raise ValueError("Invalid input. Input must of dtype=str.")
            
            result = val.strip()
            apply_change(idx, row, column_name, val, result, "Trimmed whitespace")

    def clean_names(
        column: str | int
    ):
        if isinstance(column, str):
            column_name = column
        elif isinstance(column, int):
            column_name = df.columns[column]
        else:
            raise ValueError(
                "Column must be specified as a string or integer representing the index."
            )

        col_df = df[column_name]
        for row, (idx, name) in enumerate(col_df.items(), start=start_row):
            if is_missing(name):
                record_missing(idx, row, column_name, name)
                continue
            if not isinstance(name, str):
                raise ValueError("Invalid input. Input must of dtype=str.")
            
            result = normalize_name(name)
            apply_change(idx, row, column_name, name, result, "Normalized name")

    def clean_dates(
        column: str | int
    ):
        if isinstance(column, str):
            column_name = column
        elif isinstance(column, int):
            column_name = df.columns[column]
        else:
            raise ValueError(
                "Column must be specified as a string or integer representing the index."
            )

        col_df = df[column_name]
        for row, (idx, date) in enumerate(col_df.items(), start=start_row):
            if is_missing(date):
                record_missing(idx, row, column_name, date)
                continue
            if not isinstance(date, str):
                raise ValueError("Invalid input. Input must of dtype=str.")
            
            result = normalize_dates(
                date, input_format=date_input_format, day_first_output=day_first_output
            )
            invalid = result == MISSING_VALUE
            apply_change(
                idx, row, column_name, date, result,
                "Marked invalid date as N/A" if invalid else "Normalized date",
                "Invalid date" if invalid else "Normalized value",
            )

    def clean_numeric_values(
        column: str | int
    ):
        if isinstance(column, str):
            column_name = column
        elif isinstance(column, int):
            column_name = df.columns[column]
        else:
            raise ValueError(
                "Column must be specified as a string or integer representing the index."
            )

        col_df = df[column_name]
        for row, (idx, val) in enumerate(col_df.items(), start=start_row):
            if is_missing(val):
                record_missing(idx, row, column_name, val)
                continue
            if not isinstance(val, str):
                raise ValueError("Invalid input. Input must of dtype=str.")

            try:
                result = normalize_numeric_values(val, separator=digit_separator)
            except (ValueError, OverflowError) as err:
                record_issue(row=row, column=column_name, original=val, issue=err, cleaned=None, action="Replaced with N/A")
                result = MISSING_VALUE
            invalid = result == MISSING_VALUE

            apply_change(
                idx, row, column_name, val, result,
                "Marked invalid number as N/A" if invalid else "Normalized number",
                "Invalid number" if invalid else "Normalized value",
            )

    if trailing_spaces is not None:
        for col in trailing_spaces:
            clean_whitespaces(col)

    if names is not None:
        for col in names:
            clean_names(col)

    if dates is not None:
        for col in dates:
            clean_dates(col)
    if numbers is not None:
        for col in numbers:
            clean_numeric_values(col)

    duplicate_issues = []
    if remove_duplicates:
        duplicates = df.duplicated()
        for idx in df.index[duplicates]:
            record = source_records[idx]
            duplicate_issues.append(CleaningIssue(
                record=record,
                row=record + start_row - 1,
                column=None,
                original_value=None,
                cleaned_value=None,
                issue="Duplicate row",
                action="Removed duplicate row; kept the first occurrence",
            ))
        df = df.loc[~duplicates].copy()

    df.to_csv(output_path, index=False)

    issues = sorted(
        [*issues_by_cell.values(), *duplicate_issues],
        key=lambda issue: (
            issue.record,
            column_positions.get(issue.column, len(column_positions))
            if issue.column is not None else len(column_positions),
        ),
    )

    edits = [f"{action}: {count} cell(s)" for action, count in edit_counts.items()]
    if duplicate_issues:
        edits.append(f"Removed {len(duplicate_issues)} duplicate row(s)")

    return Report(
        b_rows=before_rows,
        a_rows=len(df),
        edited_columns=[column for column in df.columns if column in edited_columns],
        missing_values=sorted(
            missing_values, key=lambda position: (position.row, column_positions[position.col])
        ),
        edits=edits,
        issues=issues,
        input_path=csv_path,
        output_path=output_path,
    )


def clean() -> Report:
    report = clean_csv(
        csv_path=CSV_PATH,
        has_headers=True,
        trailing_spaces=[
            x for x in range(11)
        ],
        names=[2, 3, 4, 8, 9, 10],
        dates=[1],
        numbers=[5, 6, 7],
        remove_duplicates=True,
        day_first_output=True,
    )
    report_path = save_report(report)
    print_report(report, report_path)
    return report


def test():
    df = pd.read_csv(CSV_PATH, dtype=str)
    print(df)


def main():
    clean()
    
if __name__ == "__main__":
    main()
