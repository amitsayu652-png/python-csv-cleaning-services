# Contributing

Use Python 3.10 or newer and install `requirements-dev.txt` in a virtual
environment. Keep real customer data in the ignored `data/private/` directory;
commit only synthetic fixtures under `data/test_samples/`.

Declare column types with `ColumnRule` rather than inferring them from values.
Preserve identifiers, source files, unknown category values in the audit, and
decimal precision. Add a regression test when changing parsing or reporting.
Tests must write to temporary directories instead of changing sample inputs.

Before proposing a change, run from the repository root:

```powershell
.\.pvenv\Scripts\python.exe -m ruff check .
.\.pvenv\Scripts\python.exe -m ruff format --check .
.\.pvenv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Describe the changed behavior, any intentionally unsupported cases, and the
checks you ran. Do not commit virtual environments or generated CSV/report files.
