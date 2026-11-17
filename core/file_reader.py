import pandas as pd

MAX_MB = 200


def _check_size(file):
    size = getattr(file, "size", 0)
    if size > MAX_MB * 1024 * 1024:
        raise ValueError(f"File is larger than {MAX_MB} MB.")


def is_excel(file) -> bool:
    return file.name.lower().endswith((".xlsx", ".xls"))


def list_sheets(file) -> list[str]:
    _check_size(file)
    file.seek(0)
    return pd.ExcelFile(file).sheet_names


def read_file(file, sheet_name=None) -> pd.DataFrame:
    """Read everything as text so we control type validation."""
    _check_size(file)
    file.seek(0)
    name = file.name.lower()
    if name.endswith(".csv"):
        try:
            df = pd.read_csv(file, dtype=str, keep_default_na=False)
        except UnicodeDecodeError:
            file.seek(0)
            df = pd.read_csv(file, dtype=str, keep_default_na=False,
                             encoding="latin-1")
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(file, sheet_name=sheet_name or 0,
                           dtype=str, keep_default_na=False)
    else:
        raise ValueError("Only .csv and .xlsx files are supported.")
    df.columns = [str(c).strip() for c in df.columns]
    return df