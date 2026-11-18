import re

import pandas as pd

from .schema_manager import BOOL_VALUES, DATE_FORMATS

MATCH_THRESHOLD = 0.5  # at least 50% of schema columns must be found


def _check_date(s: pd.Series, label: str) -> pd.Series:
    # Excel dates are read as "2025-01-05 00:00:00": remove the time part
    s = s.str.replace(r"\s00:00:00$", "", regex=True)
    fmt = DATE_FORMATS.get(label)
    if fmt is None:
        return pd.to_datetime(s, errors="coerce", format="mixed").notna()
    return pd.to_datetime(s, errors="coerce", format=fmt).notna()


def _check_type(series: pd.Series, rule: dict) -> pd.Series:
    """True where the value has the right type."""
    typ = rule.get("type", "string")
    s = series.str.strip()
    if typ == "integer":
        return s.str.fullmatch(r"[+-]?\d+")
    if typ == "float":
        return pd.to_numeric(s, errors="coerce").notna()
    if typ == "date":
        return _check_date(s, rule.get("date_format", "Auto (any format)"))
    if typ == "boolean":
        return s.str.lower().isin(BOOL_VALUES)
    return pd.Series(True, index=s.index)


def _check_allowed(s: pd.Series, rule: dict) -> pd.Series:
    """True where the value matches the allowed list."""
    allowed = [str(a).strip() for a in rule["allowed_values"]]
    values = s.str.strip()
    if not rule.get("case_sensitive", True):
        values = values.str.lower()
        allowed = [a.lower() for a in allowed]
    if rule.get("match_mode", "exact") == "contains":
        pattern = "|".join(re.escape(a) for a in allowed)
        return values.str.contains(pattern, regex=True)
    return values.isin(allowed)


def check_schema_match(df: pd.DataFrame, schema: dict) -> dict:
    """Compare file columns with schema columns."""
    expected = [r["name"] for r in schema["columns"]]
    found = [c for c in expected if c in df.columns]
    missing = [c for c in expected if c not in df.columns]
    extra = [c for c in df.columns if c not in expected]
    ratio = len(found) / len(expected) if expected else 0
    return {"ratio": ratio, "found": found, "missing": missing,
            "extra": extra, "is_wrong_schema": ratio < MATCH_THRESHOLD}


def suggest_schema(df: pd.DataFrame, schemas: dict):
    """schemas = {name: schema_dict}. Return (best_name, ratio) or (None, 0)."""
    best_name, best_ratio = None, 0
    for name, schema in schemas.items():
        ratio = check_schema_match(df, schema)["ratio"]
        if ratio > best_ratio:
            best_name, best_ratio = name, ratio
    return (best_name, best_ratio) if best_ratio > 0 else (None, 0)


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
        filled = ~blank
        typ = rule.get("type", "string")

        # Required
        if rule.get("required"):
            add(blank, col, "Required value is missing")

        # Type (and date format)
        type_ok = _check_type(s, rule)
        if typ != "string":
            if typ == "date" and rule.get("date_format", "Auto (any format)") != "Auto (any format)":
                msg = f"Invalid date. Expected format {rule['date_format']}"
            else:
                msg = f"Not a valid {typ}"
            add(filled & ~type_ok, col, msg)

        # Numbers: sign, min, max (only for values with a valid type)
        if typ in ("integer", "float"):
            nums = pd.to_numeric(s.str.strip(), errors="coerce")
            good = filled & type_ok
            sign = rule.get("sign", "any")
            if sign == "positive":
                add(good & (nums <= 0), col, "Must be a positive number (above 0)")
            elif sign == "negative":
                add(good & (nums >= 0), col, "Must be a negative number (below 0)")
            elif sign == "non-negative":
                add(good & (nums < 0), col, "Must not be negative (0 or above)")
            if rule.get("min_value") is not None:
                add(good & (nums < rule["min_value"]), col,
                    f"Below minimum {rule['min_value']}")
            if rule.get("max_value") is not None:
                add(good & (nums > rule["max_value"]), col,
                    f"Above maximum {rule['max_value']}")

        # Unique
        if rule.get("unique"):
            add(s.duplicated(keep=False) & filled, col, "Duplicate value")

        # Allowed values
        if rule.get("allowed_values"):
            mode = rule.get("match_mode", "exact")
            label = "contain one of" if mode == "contains" else "be one of"
            add(filled & ~_check_allowed(s, rule), col,
                f"Must {label}: {', '.join(rule['allowed_values'])}")

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