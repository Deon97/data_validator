import pandas as pd

from core.validator import check_schema_match, suggest_schema, validate


# ---------- Helpers ----------
def run(rule, values):
    """Validate one column named 'c'. Return the errors table."""
    df = pd.DataFrame({"c": values})
    schema = {"columns": [{"name": "c", **rule}]}
    return validate(df, schema)[1]


def messages(errs):
    return list(errs["Error"])


# ---------- 1. Basic and structure ----------
def test_basic_errors():
    schema = {"columns": [
        {"name": "id", "type": "integer", "required": True, "unique": True},
        {"name": "status", "type": "string", "allowed_values": ["a", "b"]}]}
    df = pd.DataFrame({"id": ["1", "x", "1", ""], "status": ["a", "c", "b", "a"]})
    _, errs, invalid = validate(df, schema)
    assert len(invalid) == 4
    assert "Not a valid integer" in set(errs["Error"])


def test_all_valid_returns_no_errors():
    schema = {"columns": [{"name": "id", "type": "integer", "required": True}]}
    df = pd.DataFrame({"id": ["1", "2", "3"]})
    structure, errs, invalid = validate(df, schema)
    assert structure == []
    assert errs.empty and invalid.empty


def test_missing_and_extra_columns():
    schema = {"columns": [{"name": "id"}, {"name": "email"}]}
    df = pd.DataFrame({"id": ["1"], "other": ["x"]})
    structure, _, _ = validate(df, schema)
    assert any("Missing columns: email" in m for m in structure)
    assert any("Unexpected columns" in m and "other" in m for m in structure)


def test_excel_row_numbers():
    errs = run({"type": "integer"}, ["1", "bad"])
    assert errs.iloc[0]["Row"] == 3  # header is row 1, so 2nd data row is row 3


def test_invalid_rows_have_row_and_details():
    df = pd.DataFrame({"c": ["1", "x"]})
    schema = {"columns": [{"name": "c", "type": "integer"}]}
    _, _, invalid = validate(df, schema)
    assert list(invalid.columns[:2]) == ["Row", "Error Details"]
    assert invalid.iloc[0]["Row"] == 3


# ---------- 2. Required and unique ----------
def test_required_blank_and_spaces():
    errs = run({"required": True}, ["a", "", "   "])
    assert len(errs) == 2
    assert set(messages(errs)) == {"Required value is missing"}


def test_not_required_blank_is_ok():
    assert run({"type": "integer", "required": False}, ["", "5"]).empty


def test_unique_duplicates_flagged_both_rows():
    errs = run({"unique": True}, ["a", "b", "a"])
    assert len(errs) == 2
    assert set(messages(errs)) == {"Duplicate value"}


def test_unique_ignores_blanks():
    assert run({"unique": True}, ["", ""]).empty


# ---------- 3. Types ----------
def test_integer_type():
    errs = run({"type": "integer"}, ["10", "-5", "+7", "3.5", "abc"])
    assert list(errs["Value"]) == ["3.5", "abc"]


def test_float_type():
    errs = run({"type": "float"}, ["1.5", "2", "abc"])
    assert list(errs["Value"]) == ["abc"]


def test_boolean_type():
    errs = run({"type": "boolean"}, ["true", "No", "Y", "maybe"])
    assert list(errs["Value"]) == ["maybe"]


def test_leading_zero_kept_as_text():
    assert run({"type": "string"}, ["007"]).empty


# ---------- 4. Allowed values ----------
def test_allowed_exact_is_case_sensitive_by_default():
    errs = run({"allowed_values": ["Manager"]}, ["Manager", "manager"])
    assert list(errs["Value"]) == ["manager"]


def test_allowed_exact_case_insensitive():
    rule = {"allowed_values": ["Manager"], "case_sensitive": False}
    assert run(rule, ["manager", "MANAGER"]).empty


def test_allowed_contains_case_insensitive():
    rule = {"allowed_values": ["Manager"], "match_mode": "contains",
            "case_sensitive": False}
    errs = run(rule, ["Senior manager", "Analyst"])
    assert list(errs["Value"]) == ["Analyst"]


def test_allowed_contains_case_sensitive():
    rule = {"allowed_values": ["Manager"], "match_mode": "contains",
            "case_sensitive": True}
    errs = run(rule, ["Senior Manager", "senior manager"])
    assert list(errs["Value"]) == ["senior manager"]


def test_allowed_exact_rejects_partial():
    errs = run({"allowed_values": ["Manager"]}, ["Senior Manager"])
    assert len(errs) == 1


def test_allowed_values_with_special_characters():
    rule = {"allowed_values": ["C++", "R (lang)"], "match_mode": "contains"}
    assert run(rule, ["Learn C++ now", "R (lang) user"]).empty


def test_allowed_blank_not_checked():
    assert run({"allowed_values": ["a"]}, [""]).empty


# ---------- 5. Number rules ----------
def test_min_and_max():
    errs = run({"type": "integer", "min_value": 18, "max_value": 65},
               ["30", "10", "70"])
    assert set(messages(errs)) == {"Below minimum 18", "Above maximum 65"}


def test_boundaries_are_allowed():
    assert run({"type": "integer", "min_value": 18, "max_value": 65},
               ["18", "65"]).empty


def test_sign_positive():
    errs = run({"type": "integer", "sign": "positive"}, ["5", "0", "-3"])
    assert list(errs["Value"]) == ["0", "-3"]


def test_sign_negative():
    errs = run({"type": "integer", "sign": "negative"}, ["-5", "0", "3"])
    assert list(errs["Value"]) == ["0", "3"]


def test_sign_non_negative():
    errs = run({"type": "integer", "sign": "non-negative"}, ["0", "4", "-1"])
    assert list(errs["Value"]) == ["-1"]


def test_float_range():
    errs = run({"type": "float", "min_value": 0.5, "max_value": 1.5},
               ["1.0", "0.1", "2.0"])
    assert list(errs["Value"]) == ["0.1", "2.0"]


def test_number_rules_skip_invalid_type_values():
    errs = run({"type": "integer", "min_value": 10}, ["abc"])
    assert messages(errs) == ["Not a valid integer"]  # no extra "Below minimum"


# ---------- 6. Dates ----------
def test_date_specific_format():
    errs = run({"type": "date", "date_format": "DD/MM/YYYY"},
               ["31/12/2025", "2025-12-31"])
    assert len(errs) == 1
    assert "Expected format DD/MM/YYYY" in errs.iloc[0]["Error"]


def test_date_invalid_day():
    errs = run({"type": "date", "date_format": "DD/MM/YYYY"}, ["32/01/2025"])
    assert len(errs) == 1


def test_date_auto_accepts_common_formats():
    assert run({"type": "date"}, ["2025-01-05", "05/01/2025"]).empty


def test_date_auto_rejects_text():
    errs = run({"type": "date"}, ["not a date"])
    assert messages(errs) == ["Not a valid date"]


def test_excel_datetime_with_midnight_time_is_ok():
    rule = {"type": "date", "date_format": "YYYY-MM-DD"}
    assert run(rule, ["2025-01-05 00:00:00"]).empty


# ---------- 7. Combined rules ----------
def test_multiple_errors_in_one_row_are_joined():
    schema = {"columns": [
        {"name": "id", "type": "integer", "required": True},
        {"name": "age", "type": "integer", "min_value": 18}]}
    df = pd.DataFrame({"id": [""], "age": ["10"]})
    _, errs, invalid = validate(df, schema)
    assert len(errs) == 2
    assert len(invalid) == 1
    assert "id:" in invalid.iloc[0]["Error Details"]
    assert "age:" in invalid.iloc[0]["Error Details"]


# ---------- 8. Wrong schema detection ----------
SCHEMA = {"columns": [{"name": "id"}, {"name": "email"}, {"name": "age"}]}


def test_wrong_schema_detected():
    df = pd.DataFrame({"title": ["a"], "director": ["b"]})
    result = check_schema_match(df, SCHEMA)
    assert result["is_wrong_schema"] is True
    assert result["ratio"] == 0


def test_correct_schema_not_flagged():
    df = pd.DataFrame({"id": ["1"], "email": ["a"], "age": ["3"]})
    assert check_schema_match(df, SCHEMA)["is_wrong_schema"] is False


def test_partial_match_is_ok_at_threshold():
    df = pd.DataFrame({"id": ["1"], "email": ["a"]})  # 2 of 3 found
    result = check_schema_match(df, SCHEMA)
    assert result["is_wrong_schema"] is False
    assert result["missing"] == ["age"]


def test_suggest_best_schema():
    df = pd.DataFrame({"title": ["a"], "director": ["b"]})
    schemas = {
        "customer": SCHEMA,
        "movies": {"columns": [{"name": "title"}, {"name": "director"}]},
    }
    assert suggest_schema(df, schemas) == ("movies", 1.0)


def test_suggest_schema_none_when_no_match():
    df = pd.DataFrame({"zzz": ["a"]})
    assert suggest_schema(df, {"customer": SCHEMA}) == (None, 0)