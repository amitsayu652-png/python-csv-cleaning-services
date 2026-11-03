"""Explicit, editable schemas for the synthetic CSV fixtures."""

from dataclasses import dataclass
from pathlib import Path

if __package__:
    from .clean_csv import ColumnRule, Report, clean_csv, print_report, save_report
else:
    from clean_csv import ColumnRule, Report, clean_csv, print_report, save_report

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "test_samples"
OUTPUTS = ROOT / "data" / "output"


@dataclass(frozen=True)
class SampleConfig:
    filename: str
    rules: dict[str | int, ColumnRule]
    unique_keys: tuple[str, ...] = ()


SAMPLE_CONFIGS = {
    "sales": SampleConfig(
        "01_messy_sales.csv",
        {
            "invoice_id": ColumnRule(required=True),
            "customer": ColumnRule("name"),
            "region": ColumnRule(
                "category",
                choices={
                    value.lower(): value
                    for value in ("West", "East", "North", "South", "Central", "Northeast")
                },
            ),
            "sale_date": ColumnRule("date", ambiguous_dates="day_first"),
            "units": ColumnRule("integer"),  # Negative units may describe a return.
            "unit_price": ColumnRule("number"),  # Credits remain negative.
            "discount_pct": ColumnRule("number", minimum=0, maximum=100),
            "payment_method": ColumnRule("category", choices={"upi": "UPI", "card": "Card", "cash": "Cash"}),
            "status": ColumnRule(
                "category", choices={value: value for value in ("paid", "pending", "refunded", "cancelled")}
            ),
        },
        ("invoice_id",),
    ),
    "customers": SampleConfig(
        "02_adversarial_customers.csv",
        {
            "customer_id": ColumnRule(required=True),
            "full_name": ColumnRule("name", missing_tokens=("NULL", "NA")),
            "email": ColumnRule("email"),
            "signup_date": ColumnRule("date", ambiguous_dates="day_first"),
            "account_balance": ColumnRule("number", decimal_mark="auto", missing_tokens=("NaN", "NULL")),
            "is_active": ColumnRule("boolean", missing_tokens=("NULL",)),
        },
        ("customer_id",),
    ),
    "inventory": SampleConfig(
        "03_messy_inventory.csv",
        {
            "sku": ColumnRule(required=True),
            "warehouse": ColumnRule(
                "category", choices={value.lower(): value for value in ("WH-A", "WH-B", "WH-C")}
            ),
            "stock_on_hand": ColumnRule("integer", minimum=0),
            "reorder_level": ColumnRule("integer", minimum=0),
            "cost_inr": ColumnRule("number", minimum=0, decimal_mark="auto"),
            "last_counted": ColumnRule("date", ambiguous_dates="day_first"),
            "discontinued": ColumnRule("boolean"),
        },
        ("sku", "warehouse"),
    ),
    "malformed": SampleConfig("04_malformed_unclosed_quote.csv", {}),
}


def run_sample(name: str = "sales", output_dir: Path | None = None) -> Report:
    """Write generated files to data/output, leaving sample inputs untouched."""
    if name not in SAMPLE_CONFIGS:
        raise ValueError(f"Unknown sample {name!r}. Choose from {list(SAMPLE_CONFIGS)}.")
    config = SAMPLE_CONFIGS[name]
    source = SAMPLES / config.filename
    folder = Path(output_dir) if output_dir is not None else OUTPUTS
    folder.mkdir(parents=True, exist_ok=True)
    report_path = folder / f"{source.stem}_report.csv"
    cleaned_path = folder / f"{source.stem}_cleaned.csv"
    if report_path.resolve() == source.resolve():
        raise ValueError("The report cannot overwrite the source CSV.")
    report = clean_csv(
        source,
        rules=config.rules,
        trim_all=True,
        unique_keys=config.unique_keys,
        output_path=cleaned_path,
    )
    # A parse failure must not overwrite an older cleaned result. Its report
    # states failure and has no output_path, even if an old file exists there.
    save_report(report, report_path)
    print_report(report, report_path)
    return report
