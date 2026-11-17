import pandas as pd

from .schema_manager import BOOL_VALUES


def _check_type(series: pd.Series, typ: str) -> pd.Series:
    """True where the value has the right type."""
    s = series.str.strip()
    if typ == "integer":
        return s.str.fullmatch(r"[+-]?\d+")
    if typ == "float":
        return pd.to_numeric(s, errors="coerce").notna()
    if typ == "date":
        return pd.to_datetime(s, errors="coerce", format="mixed").notna()
    if typ == "boolean":
        return s.str.lower().isin(BOOL_VALUES)
    return pd.Series(True, index=s.index)


def validate(df: pd.DataFrame, schema: dict):
    """Return (structure_messages, errors_table, invalid_rows_table)."""
    rules = schema["columns"]
    expected = [r["name"] for r in rules]

    # Part A: structure check
    structure = []
    missing = [c for c in expected if c not in df.columns]
    extra = [c for c in df.columns if c not in expected]
    if missing:
        structure.append(f"Missing columns: {', '.join(missing)}")
    if extra:
        structure.append(f"Unexpected columns (ignored): {', '.join(extra)}")

    # Part B: cell checks
    errors = []

    def add(mask, col, reason):
        for idx in df.index[mask]:
            errors.append({"Row": idx + 2, "Column": col,
                           "Value": df.at[idx, col], "Error": reason})

    for rule in rules:
        col = rule["name"]
        if col not in df.columns:
            continue
        s = df[col]
        blank = s.str.strip() == ""

        if rule.get("required"):
            add(blank, col, "Required value is missing")

        filled = ~blank
        typ = rule.get("type", "string")
        if typ != "string":
            add(filled & ~_check_type(s, typ), col, f"Not a valid {typ}")

        if rule.get("unique"):
            add(s.duplicated(keep=False) & filled, col, "Duplicate value")

        allowed = rule.get("allowed_values")
        if allowed:
            add(filled & ~s.str.strip().isin(allowed), col,
                f"Not in allowed values: {allowed}")

    # Part C: build the result tables
    errors_df = pd.DataFrame(errors, columns=["Row", "Column", "Value", "Error"])
    bad_idx = sorted(r - 2 for r in errors_df["Row"].unique())
    invalid = df.loc[bad_idx].copy()
    if not invalid.empty:
        reasons = {}
        for row, group in errors_df.groupby("Row"):
            reasons[row] = "; ".join(group["Column"] + ": " + group["Error"])
        invalid.insert(0, "Error Details", [reasons[i + 2] for i in invalid.index])
        invalid.insert(0, "Row", [i + 2 for i in invalid.index])
    return structure, errors_df, invalid