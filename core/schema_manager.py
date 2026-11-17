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
    return problems