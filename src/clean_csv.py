"""Configurable CSV normalization with a record-by-record audit report."""

from __future__ import annotations

import csv
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Literal, TypeAlias

import pandas as pd
import regex
from dateutil import parser
from titlecase import titlecase
from word2number import w2n

ROOT_DIR = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT_DIR / "data" / "test_samples" / "01_messy_sales.csv"
MISSING_VALUE = "N/A"
Column: TypeAlias = str | int
Kind: TypeAlias = Literal["text", "name", "email", "date", "number", "integer", "boolean", "category"]


@dataclass(frozen=True)
class ColumnRule:
    """A declared column type; identifiers should normally use text."""

    kind: Kind = "text"
    trim: bool = True
    required: bool = False
    missing_tokens: tuple[str, ...] = ()
    decimal_mark: Literal[".", ",", "auto"] = "."
    decimal_places: int | None = None
    minimum: str | int | Decimal | None = None
    maximum: str | int | Decimal | None = None
    allow_words: bool = True
    input_format: str | None = None
    output_format: str = "%d/%m/%Y"
    ambiguous_dates: Literal["day_first", "month_first", "reject"] = "reject"
    choices: Mapping[str, str] | None = None


@dataclass(frozen=True)
class MissingPosition:
    row: int
    col: Column


@dataclass(frozen=True)
class CleaningIssue:
    record: int
    row: int
    column: Column | None
    original_value: str | None
    cleaned_value: str | None
    issue: str
    action: str
    reason: str = ""


@dataclass(frozen=True)
class Report:
    b_rows: int = 0
    a_rows: int = 0
    edited_columns: list[Column] = field(default_factory=list)
    missing_values: list[MissingPosition] = field(default_factory=list)
    edits: list[str] = field(default_factory=list)
    issues: list[CleaningIssue] = field(default_factory=list)
    input_path: Path | None = None
    output_path: Path | None = None
    status: Literal["success", "failed"] = "success"
    error: str | None = None

    @property
    def duplicates_removed(self) -> int:
        return sum(item.issue == "Duplicate row" for item in self.issues)

    @property
    def invalid_values(self) -> int:
        return sum(item.issue.startswith("Invalid ") for item in self.issues)

    @property
    def conflicts(self) -> int:
        return sum(item.issue == "Conflicting key" for item in self.issues)


def save_report(report: Report, report_path: Path | None = None) -> Path:
    if report_path is None:
        if report.input_path is None:
            raise ValueError("An input path or report path is required.")
        report_path = report.input_path.with_name(f"{report.input_path.stem}_report.csv")
    report_path = Path(report_path)
    for protected in (report.input_path, report.output_path):
        if protected is not None and report_path.resolve() == protected.resolve():
            raise ValueError("The report path must differ from the input and cleaned CSV paths.")
    with report_path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(CleaningIssue.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(issue) for issue in report.issues)
    return report_path


def print_report(report: Report, report_path: Path | None = None) -> None:
    if report.status == "failed":
        print(f"CSV cleaning failed: {report.error}")
    else:
        print("CSV cleaning complete")
        print(f"Rows: {report.b_rows} -> {report.a_rows}")
        print(f"Duplicates removed: {report.duplicates_removed}")
        print(f"Edited columns: {', '.join(map(str, report.edited_columns)) or 'None'}")
        print(f"Missing cells (selected columns): {len(report.missing_values)}")
        print(f"Invalid values: {report.invalid_values}")
        print(f"Records with conflicting keys: {report.conflicts}")
    if report.output_path is not None:
        print(f"Cleaned CSV: {report.output_path}")
    if report_path is not None:
        print(f"Report CSV: {report_path}")


def normalize_name(name: str) -> str:
    """Normalize human names, including nonbreaking and zero-width spaces."""
    name = "".join(char for char in name if unicodedata.category(char) != "Cf")
    name = " ".join(name.split()).lower()
    if "@" not in name:
        return titlecase(name)
    return " ".join(token if "@" in token else titlecase(token) for token in name.split())


_CURRENCY_CODES = (
    "INR USD EUR GBP JPY AUD CAD CHF CNY SGD HKD NZD KRW TWD THB VND MYR PHP "
    "IDR BDT LKR NPR PKR AED SAR EGP NGN ZAR KES GHS ETB TRY ILS PLN CZK HUF "
    "RON BGN SEK NOK DKK ISK"
).split()
_CURRENCY_NAMES = (
    r"rupees?|dollars?|euros?|pounds?|yens?|francs?|pesos?|reais|real|liras?|"
    r"shekels?|zlotys?|forints?|crowns?|dirhams?|riyals?|bahts?|won|ringgits?|"
    r"naira|cedis?|rand|shillings?"
)
_CURRENCY = regex.compile(
    rf"(?:\p{{Sc}}|(?<![A-Za-z])(?:{'|'.join(_CURRENCY_CODES)}|{_CURRENCY_NAMES})(?![A-Za-z]))",
    regex.IGNORECASE,
)
_NUMBER_WORDS = set(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty "
    "sixty seventy eighty ninety hundred thousand million billion and point".split()
)


def has_currency(val: str) -> tuple[bool, str | None]:
    match = _CURRENCY.search(val)
    return match is not None, match.group() if match else None


def _parse_number(value: str, decimal_mark: str = ".", allow_words: bool = True) -> Decimal:
    text = value.strip()
    if len(text) > 2000:
        raise ValueError("Number exceeds the supported 2000-character limit.")
    accounting = text.startswith("(") and text.endswith(")")
    if accounting:
        text = text[1:-1].strip()
    sign = ""
    if text[:1] in ("+", "-"):
        sign, text = text[0], text[1:].strip()
    prefix = _CURRENCY.match(text)
    if prefix:
        text = text[prefix.end() :].strip()
    suffix = next((match for match in _CURRENCY.finditer(text) if match.end() == len(text)), None)
    if suffix:
        text = text[: suffix.start()].strip()
    if not sign and text[:1] in ("+", "-"):
        sign, text = text[0], text[1:].strip()
    if accounting and sign:
        raise ValueError("Accounting parentheses cannot be combined with an explicit sign.")
    if text.lower().startswith(("minus ", "negative ")):
        if sign or accounting:
            raise ValueError("Multiple number signs.")
        sign, text = "-", text.split(maxsplit=1)[1]

    words = re.split(r"[\s-]+", text.lower())
    if allow_words and words and all(word in _NUMBER_WORDS for word in words):
        number = Decimal(str(w2n.word_to_num(text)))
    else:
        parts = re.fullmatch(r"(.+?)(?:[eE]([+-]?[0-9]+))?", text)
        if parts is None:
            raise ValueError(f"Invalid numeric format: {value!r}")
        mantissa, exponent = parts.groups()
        if exponent and abs(int(exponent)) > 1000:
            raise ValueError("Exponent must be between -1000 and 1000.")
        mantissa = mantissa.replace("\u00a0", " ").replace("\u202f", " ")
        mark = decimal_mark
        if mark == "auto":
            if "." in mantissa and "," in mantissa:
                mark = "." if mantissa.rfind(".") > mantissa.rfind(",") else ","
            elif "," in mantissa:
                grouped = re.fullmatch(r"[0-9]{1,3}(?:,[0-9]{3})+", mantissa)
                mark = "." if grouped else ","
            else:
                mark = "."
        if mark not in (".", ","):
            raise ValueError("decimal_mark must be '.', ',' or 'auto'.")
        group = "," if mark == "." else "."
        grouping = rf"(?:[0-9]+|[0-9]{{1,3}}(?:{re.escape(group)}[0-9]{{3}})+|[0-9]{{1,3}}(?: [0-9]{{3}})+)"
        pattern = rf"(?:{grouping}(?:{re.escape(mark)}[0-9]*)?|{re.escape(mark)}[0-9]+)"
        if re.fullmatch(pattern, mantissa) is None:
            raise ValueError(f"Invalid numeric format or grouping: {value!r}")
        canonical = mantissa.replace(group, "").replace(" ", "").replace(mark, ".")
        try:
            number = Decimal(canonical + (f"e{exponent}" if exponent else ""))
        except InvalidOperation as exc:
            raise ValueError(f"Invalid number: {value!r}") from exc
    if not number.is_finite():
        raise ValueError("Number must be finite.")
    return number.copy_negate() if accounting or sign == "-" else number


def _format_number(number: Decimal, separator: str, places: int | None) -> str:
    if separator not in ("", ",", "_"):
        raise ValueError("digit_separator must be ',', '_' or ''.")
    if places is not None:
        with localcontext() as context:
            context.prec = max(28, len(number.as_tuple().digits) + abs(number.adjusted()) + places + 2)
            number = number.quantize(Decimal(1).scaleb(-places))
    return format(number, ",f").replace(",", separator) if separator else format(number, "f")


def normalize_numeric_values(
    val: str,
    separator: str = "_",
    *,
    decimal_mark: str = ".",
    decimal_places: int | None = None,
    allow_words: bool = True,
) -> str:
    if not isinstance(val, str):
        raise ValueError("Input must be a string.")
    if decimal_places is not None and not 0 <= decimal_places <= 100:
        raise ValueError("decimal_places must be between 0 and 100.")
    return _format_number(_parse_number(val, decimal_mark, allow_words), separator, decimal_places)


def _parse_date(value: str, input_format: str | None, ambiguity: str) -> tuple[datetime, bool]:
    text = value.strip()
    if input_format:
        # strptime requires every specified component and does not invent today's day.
        if (
            not all(token in input_format for token in ("%Y",))
            or not any(token in input_format for token in ("%d", "%j"))
            or not any(token in input_format for token in ("%m", "%b", "%B", "%j"))
        ):
            raise ValueError("Date input format must specify a complete day, month and year.")
        return datetime.strptime(text, input_format), False
    iso = re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:[Tt ][0-9]{2}:[0-9]{2}.*)?", text)
    if iso:
        return datetime.fromisoformat(text.replace("Z", "+00:00")), False
    numeric = re.fullmatch(r"([0-9]{1,4})([/.-])([0-9]{1,2})\2([0-9]{1,4})", text)
    if numeric:
        first, _, middle, last = numeric.groups()
        if len(first) == 4:
            return datetime(int(first), int(middle), int(last)), False
        if len(last) != 4 or len(first) > 2:
            raise ValueError("Date requires a four-digit year and a complete day and month.")
        a, b = int(first), int(middle)
        ambiguous = 1 <= a <= 12 and 1 <= b <= 12 and a != b
        if ambiguous and ambiguity == "reject":
            raise ValueError("Ambiguous day/month order; select day_first or month_first.")
        if a > 12:
            day, month = a, b
        elif b > 12:
            month, day = a, b
        else:
            day, month = (a, b) if ambiguity != "month_first" else (b, a)
        return datetime(int(last), month, day), ambiguous
    month_word = r"[A-Za-z]+"
    named = rf"(?:[0-9]{{1,2}}(?:st|nd|rd|th)?[\s./-]+{month_word}[\s,./-]+[0-9]{{4}}|{month_word}[\s./-]+[0-9]{{1,2}}(?:st|nd|rd|th)?[\s,./-]+[0-9]{{4}})"
    if re.fullmatch(named, text, re.IGNORECASE):
        return parser.parse(text, default=datetime(2000, 1, 1), fuzzy=False), False
    raise ValueError("Unsupported or incomplete date; provide a complete date or input_format.")


def normalize_dates(
    val: str,
    output_format: str = "%d/%m/%Y",
    separator: str = "/",
    input_format: str | None = None,
    day_first_output: bool = True,
) -> str:
    try:
        date, _ = _parse_date(val, input_format, "day_first" if day_first_output else "month_first")
        return date.strftime(output_format).replace("/", separator)
    except (ValueError, OverflowError):
        return MISSING_VALUE


def _normalize(value: str, rule: ColumnRule, separator: str) -> tuple[str, str, str]:
    """Return normalized text, issue label and explanation."""
    reason = ""
    issue = "Normalized value"
    if rule.kind == "name":
        result = normalize_name(value)
    elif rule.kind == "email":
        result = value.strip().lower()
        if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", result) is None:
            raise ValueError("Expected an email address with a local part, @ and a dotted domain.")
    elif rule.kind in ("number", "integer"):
        number = _parse_number(value, rule.decimal_mark, rule.allow_words)
        if rule.kind == "integer" and number != number.to_integral_value():
            raise ValueError("Expected a whole number.")
        if rule.minimum is not None and number < Decimal(str(rule.minimum)):
            raise ValueError(f"Number must be at least {rule.minimum}.")
        if rule.maximum is not None and number > Decimal(str(rule.maximum)):
            raise ValueError(f"Number must be at most {rule.maximum}.")
        places = 0 if rule.kind == "integer" else rule.decimal_places
        result = _format_number(number, separator, places)
    elif rule.kind == "date":
        date, ambiguous = _parse_date(value, rule.input_format, rule.ambiguous_dates)
        result = date.strftime(rule.output_format)
        if ambiguous:
            issue, reason = "Ambiguous date", f"Interpreted using {rule.ambiguous_dates}."
        if date.tzinfo is not None:
            reason = (reason + " Kept the source calendar date; no timezone conversion was applied.").strip()
    elif rule.kind == "boolean":
        options = {word: "true" for word in ("true", "yes", "y", "1")}
        options.update({word: "false" for word in ("false", "no", "n", "0")})
        if value.casefold() not in options:
            raise ValueError("Expected true/false, yes/no, y/n or 1/0.")
        result = options[value.casefold()]
    elif rule.kind == "category":
        options = {key.casefold(): label for key, label in (rule.choices or {}).items()}
        if value.casefold() not in options:
            raise ValueError(f"Unknown category: {value!r}.")
        result = options[value.casefold()]
    else:
        result = value
    return result, issue, reason


class _ReadError(ValueError):
    def __init__(self, message: str, record: int = 0, row: int = 0):
        super().__init__(message)
        self.record, self.row = record, row


def _read_csv(path: Path, has_headers: bool, delimiter: str, encoding: str):
    rows, positions = [], []
    columns = None
    record, start = 0, 1
    try:
        with path.open(newline="", encoding=encoding) as stream:
            reader = csv.reader(stream, delimiter=delimiter, strict=True)
            while True:
                start = reader.line_num + 1
                try:
                    values = next(reader)
                except StopIteration:
                    break
                if not values:  # Blank physical lines are not data records.
                    continue
                if columns is None:
                    if has_headers:
                        if any(not value.strip() for value in values) or len(set(values)) != len(values):
                            raise _ReadError("Headers must be nonempty and unique.", 0, start)
                        columns = values
                        continue
                    columns = list(range(len(values)))
                record += 1
                if len(values) != len(columns):
                    raise _ReadError(f"Expected {len(columns)} fields; found {len(values)}.", record, start)
                rows.append(values)
                positions.append(start)
    except (csv.Error, UnicodeError, OSError) as exc:
        raise _ReadError(f"Cannot read {path.name}: {exc}", record + 1, start) from exc
    if columns is None:
        raise _ReadError("The CSV is empty; no header or data records were found.")
    return pd.DataFrame(rows, columns=columns, dtype="string"), positions


def _column(selector: Column, columns: Sequence[Column]) -> Column:
    if isinstance(selector, bool):
        raise ValueError("A column selector must be a header or a zero-based position.")
    if isinstance(selector, int):
        if not 0 <= selector < len(columns):
            raise ValueError(f"Column position {selector} is out of range for {len(columns)} columns.")
        return columns[selector]
    if selector not in columns:
        raise ValueError(f"Unknown column: {selector!r}. Available columns: {list(columns)}")
    return selector


def _validate_rule(rule: ColumnRule) -> None:
    if rule.kind not in ("text", "name", "email", "date", "number", "integer", "boolean", "category"):
        raise ValueError(f"Unknown cleaning kind: {rule.kind!r}")
    if rule.decimal_mark not in (".", ",", "auto"):
        raise ValueError("decimal_mark must be '.', ',' or 'auto'.")
    if rule.decimal_places is not None and (
        type(rule.decimal_places) is not int or not 0 <= rule.decimal_places <= 100
    ):
        raise ValueError("decimal_places must be an integer between 0 and 100.")
    if rule.ambiguous_dates not in ("day_first", "month_first", "reject"):
        raise ValueError("Unknown ambiguous_dates policy.")
    if rule.kind == "category" and not rule.choices:
        raise ValueError("A category rule requires choices.")
    for bound in (rule.minimum, rule.maximum):
        if bound is not None:
            try:
                number = Decimal(str(bound))
            except InvalidOperation as exc:
                raise ValueError(f"Invalid numeric bound: {bound!r}.") from exc
            if not number.is_finite():
                raise ValueError("Numeric bounds must be finite.")
    if rule.minimum is not None and rule.maximum is not None:
        if Decimal(str(rule.minimum)) > Decimal(str(rule.maximum)):
            raise ValueError("minimum cannot exceed maximum.")


def clean_csv(
    csv_path: Path,
    has_headers: bool = True,
    trailing_spaces: list[Column] | None = None,
    names: list[Column] | None = None,
    dates: list[Column] | None = None,
    numbers: list[Column] | None = None,
    digit_separator: str = ",",
    remove_duplicates: bool = True,
    date_input_format: str | None = None,
    day_first_output: bool = True,
    output_path: Path | None = None,
    *,
    rules: Mapping[Column, ColumnRule] | None = None,
    trim_all: bool = False,
    missing_tokens: Sequence[str] = (),
    invalid_policy: Literal["mark", "keep"] = "mark",
    unique_keys: Sequence[Column] | None = None,
    delimiter: str = ",",
    encoding: str = "utf-8-sig",
    output_headers: bool | None = None,
) -> Report:
    """Save a cleaned CSV and return an audit. Parse failures return a failed Report.

    Rules are explicit, with no automatic type inference. Legacy column lists
    remain supported; entries in rules take precedence over those lists.
    """
    csv_path = Path(csv_path)
    output_path = (
        Path(output_path) if output_path is not None else csv_path.with_name(f"{csv_path.stem}_cleaned.csv")
    )
    if output_path.resolve() == csv_path.resolve():
        raise ValueError("The cleaned CSV path must differ from the input path.")
    if invalid_policy not in ("mark", "keep"):
        raise ValueError("invalid_policy must be 'mark' or 'keep'.")
    if digit_separator not in ("", ",", "_"):
        raise ValueError("digit_separator must be ',', '_' or ''.")
    if len(delimiter) != 1 or delimiter in ("\r", "\n", '"'):
        raise ValueError("delimiter must be one character other than a quote or newline.")
    try:
        frame, positions = _read_csv(csv_path, has_headers, delimiter, encoding)
    except _ReadError as exc:
        issue = CleaningIssue(
            exc.record, exc.row, None, None, None, "File error", "No cleaned CSV written", str(exc)
        )
        return Report(input_path=csv_path, status="failed", error=str(exc), issues=[issue])

    columns: list[Column] = list(frame.columns)
    selected: dict[Column, ColumnRule] = {col: ColumnRule() for col in columns} if trim_all else {}
    for selector in trailing_spaces or []:
        selected[_column(selector, columns)] = ColumnRule()
    legacy: tuple[tuple[list[Column] | None, Kind], ...] = (
        (names, "name"),
        (dates, "date"),
        (numbers, "number"),
    )
    for selectors, kind in legacy:
        for selector in selectors or []:
            selected[_column(selector, columns)] = ColumnRule(
                kind=kind,
                input_format=date_input_format,
                ambiguous_dates="day_first" if day_first_output else "month_first",
            )
    for selector, rule in (rules or {}).items():
        selected[_column(selector, columns)] = rule
    for rule in selected.values():
        _validate_rule(rule)
    keys = list(dict.fromkeys(_column(key, columns) for key in unique_keys or []))

    issues: list[CleaningIssue] = []
    missing: list[MissingPosition] = []
    edited: set[Column] = set()
    actions: Counter[str] = Counter()
    invalid_key_rows: set[int] = set()
    for col in columns:
        if col not in selected:
            continue
        rule = selected[col]
        tokens = {token.casefold() for token in (*missing_tokens, *rule.missing_tokens)}
        # The reader creates a RangeIndex; enumerate gives the checker an int.
        for idx, original in enumerate(frame[col]):
            row, record = positions[idx], idx + 1
            value = original.strip() if rule.trim else original
            cell_actions = []
            if value != original:
                cell_actions.append("Trimmed whitespace")
            reason = ""
            if not value.strip() or value.casefold() in tokens:
                missing.append(MissingPosition(row, col))
                result = None
                issue = "Invalid required value" if rule.required else "Missing value"
                reason = (
                    "A value is required." if rule.required else "Empty cell or configured missing token."
                )
                cell_actions.append(
                    "Marked blank cell as missing" if original.strip() == "" and original else "Left missing"
                )
            else:
                try:
                    result, issue, reason = _normalize(value, rule, digit_separator)
                    if result != value:
                        labels = {"name": "name", "date": "date", "number": "number", "integer": "number"}
                        cell_actions.append(f"Normalized {labels.get(rule.kind, rule.kind)}")
                except (ValueError, InvalidOperation, OverflowError) as exc:
                    result = MISSING_VALUE if invalid_policy == "mark" else original
                    issue = f"Invalid {'number' if rule.kind == 'integer' else rule.kind}"
                    reason = str(exc)
                    if col in keys:
                        invalid_key_rows.add(idx)
                    cell_actions.append(
                        "Marked invalid value as N/A"
                        if invalid_policy == "mark"
                        else "Kept original invalid value"
                    )
            if result != original:
                frame.at[idx, col] = pd.NA if result is None else result
                edited.add(col)
            if cell_actions or issue != "Normalized value" or reason:
                if not cell_actions:
                    cell_actions.append("Kept value; flagged for review")
                issues.append(
                    CleaningIssue(record, row, col, original, result, issue, "; ".join(cell_actions), reason)
                )
                actions.update(cell_actions)

    before = len(frame)
    if remove_duplicates:
        duplicates = frame.duplicated()
        for idx in frame.index[duplicates]:
            issues.append(
                CleaningIssue(
                    idx + 1,
                    positions[idx],
                    None,
                    None,
                    None,
                    "Duplicate row",
                    "Removed duplicate row; kept the first occurrence",
                )
            )
        frame = frame.loc[~duplicates].copy()
    if keys and not frame.empty:
        keyed = frame.loc[
            frame[keys].notna().all(axis=1)
            & frame[keys].apply(lambda col: col.str.strip().ne("")).all(axis=1)
            & ~frame.index.isin(invalid_key_rows)
        ]
        for _, group in keyed.groupby(keys, sort=False, dropna=False):
            if len(group.drop_duplicates()) < 2:
                continue
            for idx in group.index:
                key_text = ", ".join(f"{key}={frame.at[idx, key]}" for key in keys)
                issues.append(
                    CleaningIssue(
                        idx + 1,
                        positions[idx],
                        None,
                        key_text,
                        key_text,
                        "Conflicting key",
                        "Kept record for review",
                        "Different records share the configured key.",
                    )
                )
    frame.to_csv(
        output_path,
        index=False,
        header=has_headers if output_headers is None else output_headers,
        sep=delimiter,
        encoding="utf-8" if encoding == "utf-8-sig" else encoding,
    )
    order: dict[Column, int] = {col: index for index, col in enumerate(columns)}
    issues.sort(
        key=lambda item: (
            item.record,
            order.get(item.column, len(columns)) if item.column is not None else len(columns),
        )
    )
    return Report(
        b_rows=before,
        a_rows=len(frame),
        edited_columns=[col for col in columns if col in edited],
        missing_values=sorted(missing, key=lambda item: (item.row, order[item.col])),
        edits=[f"{action}: {count} cell(s)" for action, count in actions.items()],
        issues=issues,
        input_path=csv_path,
        output_path=output_path,
    )


def clean() -> Report:
    """Run the sales preset. Change this call to select a different sample."""
    if __package__:
        from .sample_configs import run_sample
    else:
        from sample_configs import run_sample
    return run_sample("sales")


def main() -> None:
    report = clean()
    if report.status == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
