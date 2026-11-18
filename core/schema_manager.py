import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"
SCHEMA_DIR.mkdir(exist_ok=True)

TYPES = ["string", "integer", "float", "date", "boolean"]
BOOL_VALUES = {"true", "false", "yes", "no", "y", "n", "1", "0"}


def safe_name(name: str) -> str:
    """Keep only letters, numbers, _ and - so the file name is safe."""
    cleaned = re.sub(r"[^A-Za-z0-9_\-]", "_", name.strip())
    if not cleaned:
        raise ValueError("Schema name is empty.")
    return cleaned


def _infer_type(series: pd.Series) -> str:
    vals = series[series.str.strip() != ""].str.strip()
    if vals.empty:
        return "string"
    if vals.str.lower().isin(BOOL_VALUES).all() and not vals.isin(["0", "1"]).all():
        return "boolean"
    if pd.to_numeric(vals, errors="coerce").notna().all():
        if vals.str.fullmatch(r"[+-]?\d+").all():
            return "integer"
        return "float"
    parsed = pd.to_datetime(vals, errors="coerce", format="mixed")
    if parsed.notna().all():
        return "date"
    return "string"


def infer_schema(df: pd.DataFrame) -> list[dict]:
    columns = []
    for c in df.columns:
        s = df[c]
        has_blank = (s.str.strip() == "").any()
        columns.append({
            "name": c,
            "type": _infer_type(s),
            "required": not has_blank,
            "unique": False,
        })
    return columns


def save_schema(name: str, columns: list[dict], overwrite=True) -> str:
    name = safe_name(name)
    path = SCHEMA_DIR / f"{name}.json"
    version = 1
    created_at = datetime.now().isoformat(timespec="seconds")
    if path.exists():
        if not overwrite:
            raise FileExistsError(f"Schema '{name}' already exists.")
        old = json.loads(path.read_text(encoding="utf-8"))
        version = old.get("version", 1) + 1
        created_at = old.get("created_at", created_at)
    data = {
        "name": name,
        "version": version,
        "created_at": created_at,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "columns": columns,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return name


def list_schemas() -> list[str]:
    return sorted(p.stem for p in SCHEMA_DIR.glob("*.json"))


def load_schema(name: str) -> dict:
    path = SCHEMA_DIR / f"{safe_name(name)}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def delete_schema(name: str):
    (SCHEMA_DIR / f"{safe_name(name)}.json").unlink(missing_ok=True)

def validate_columns(columns: list[dict]) -> list[str]:
    """Return a list of problems. An empty list means the schema is OK."""
    problems = []
    names = [str(c.get("name", "")).strip() for c in columns]

    if not columns:
        problems.append("The schema must have at least one column.")
    if any(n == "" for n in names):
        problems.append("Column names cannot be empty.")

    seen = set()
    for n in names:
        if n and n in seen:
            problems.append(f"Duplicate column name: {n}")
        seen.add(n)

    for c in columns:
        if c.get("type") not in TYPES:
            problems.append(f"Invalid type for column '{c.get('name')}'.")

    for c in columns:
        lo, hi = c.get("min_value"), c.get("max_value")
        if lo is not None and hi is not None and lo > hi:
            problems.append(f"Column '{c.get('name')}': min is greater than max.")
        if c.get("sign") == "positive" and hi is not None and hi <= 0:
            problems.append(f"Column '{c.get('name')}': max must be above 0 for positive only.")
        if c.get("sign") == "negative" and lo is not None and lo >= 0:
            problems.append(f"Column '{c.get('name')}': min must be below 0 for negative only.")
    return problems

import math

MATCH_MODES = ["exact", "contains"]
SIGNS = ["any", "positive", "negative", "non-negative"]
DATE_FORMATS = {
    "Auto (any format)": None,
    "YYYY-MM-DD": "%Y-%m-%d",
    "DD/MM/YYYY": "%d/%m/%Y",
    "MM/DD/YYYY": "%m/%d/%Y",
    "DD-MM-YYYY": "%d-%m-%Y",
    "YYYY/MM/DD": "%Y/%m/%d",
    "DD-Mon-YYYY": "%d-%b-%Y",
}


def columns_to_rows(columns: list[dict]) -> list[dict]:
    """Schema columns -> rows for the editor table (with defaults)."""
    rows = []
    for c in columns:
        rows.append({
            "name": c["name"],
            "type": c.get("type", "string"),
            "required": bool(c.get("required", False)),
            "unique": bool(c.get("unique", False)),
            "allowed_values": ", ".join(c.get("allowed_values", [])),
            "match_mode": c.get("match_mode", "exact"),
            "case_sensitive": bool(c.get("case_sensitive", True)),
            "min_value": c.get("min_value"),
            "max_value": c.get("max_value"),
            "sign": c.get("sign", "any"),
            "date_format": c.get("date_format", "Auto (any format)"),
        })
    return rows


def _number(value):
    """Return int/float, or None if the cell is empty."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    value = float(value)
    return int(value) if value.is_integer() else value


def rows_to_columns(rows: list[dict]) -> list[dict]:
    """Editor table rows -> clean schema columns."""
    columns = []
    for r in rows:
        name = str(r.get("name") or "").strip()
        if not name and not r.get("type"):
            continue  # skip empty rows
        typ = r.get("type") or "string"
        rule = {
            "name": name,
            "type": typ,
            "required": bool(r.get("required")),
            "unique": bool(r.get("unique")),
        }
        raw = str(r.get("allowed_values") or "")
        values = [v.strip() for v in raw.split(",") if v.strip()]
        if values:
            rule["allowed_values"] = values
            rule["match_mode"] = r.get("match_mode") or "exact"
            rule["case_sensitive"] = bool(r.get("case_sensitive"))
        if typ in ("integer", "float"):
            for key in ("min_value", "max_value"):
                number = _number(r.get(key))
                if number is not None:
                    rule[key] = number
            if r.get("sign") and r["sign"] != "any":
                rule["sign"] = r["sign"]
        if typ == "date" and r.get("date_format") not in (None, "Auto (any format)"):
            rule["date_format"] = r["date_format"]
        columns.append(rule)
    return columns