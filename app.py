import io
from pathlib import Path

import pandas as pd
import streamlit as st

from core import file_reader as fr
from core import schema_manager as sm
from core.validator import check_schema_match, suggest_schema, validate

# ---------------- Settings ----------------
ASSETS = Path(__file__).resolve().parent / "assets"
LOGO = ASSETS / "logo.png"
CONTACT = "meapac.is.finance@accor.com"
DESCRIPTION = ("Designed and developed by IS Finance, Bangkok, "
               "for data validation purposes.")
MAX_SHOW = 1000  # maximum rows shown on screen


def get_version() -> str:
    f = Path(__file__).resolve().parent / "VERSION.txt"
    return f.read_text(encoding="utf-8").strip() if f.exists() else "unknown"


st.set_page_config(
    page_title="Data Validation Tool",
    page_icon=str(LOGO) if LOGO.exists() else "✅",
    layout="wide",
)

col_logo, col_title = st.columns([1, 8])
if LOGO.exists():
    col_logo.image(str(LOGO), width=90)
col_title.title("Data Validation Tool")

page = st.sidebar.radio(
    "Menu", ["1. Create Schema", "2. Validate Data", "3. Manage Schemas"]
)

st.sidebar.divider()
if LOGO.exists():
    st.sidebar.image(str(LOGO), width=110)
st.sidebar.caption(DESCRIPTION)
st.sidebar.caption(f"Questions or feedback: {CONTACT}")
st.sidebar.caption(f"Version {get_version()}")


def to_excel_bytes(df):
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    return buffer.getvalue()


def get_schema_names():
    """List schemas, or stop with a friendly message if the folder is unreachable."""
    try:
        return sm.list_schemas()
    except OSError:
        st.error("The schema folder cannot be reached. Please check that "
                 "the SharePoint folder is synced.")
        st.stop()


COLUMN_CONFIG = {
    "name": st.column_config.TextColumn(required=True),
    "type": st.column_config.SelectboxColumn(options=sm.TYPES, required=True),
    "required": st.column_config.CheckboxColumn(),
    "unique": st.column_config.CheckboxColumn(),
    "allowed_values": st.column_config.TextColumn(
        help="Comma-separated, optional. Example: Manager, Analyst"),
    "match_mode": st.column_config.SelectboxColumn(
        "match", options=sm.MATCH_MODES,
        help="exact = whole value must match. contains = value only has to "
             "include it (Manager also accepts Senior Manager)"),
    "case_sensitive": st.column_config.CheckboxColumn(
        help="Untick to ignore capital letters"),
    "min_value": st.column_config.NumberColumn(help="Numbers only"),
    "max_value": st.column_config.NumberColumn(help="Numbers only"),
    "sign": st.column_config.SelectboxColumn(
        options=sm.SIGNS, help="positive = above 0, negative = below 0"),
    "date_format": st.column_config.SelectboxColumn(
        options=list(sm.DATE_FORMATS.keys()), help="Only used for date columns"),
}


# ---------------- Page 1: Create schema ----------------
if page.startswith("1"):
    st.header("Create Schema from a Sample File")
    f = st.file_uploader("Upload a csv or xlsx file", type=["csv", "xlsx"], key="c")
    if f:
        try:
            is_xl = fr.is_excel(f)
            sheets = fr.list_sheets(f) if is_xl else [None]
            chosen = (
                st.multiselect("Select sheet(s) - one schema per sheet",
                               sheets, default=sheets[:1])
                if is_xl else [None]
            )
            base = f.name.rsplit(".", 1)[0]

            for i, sh in enumerate(chosen):
                label = f"{base}_{sh}" if sh else base
                st.subheader(f"Sheet: {sh}" if sh else "File schema")
                df = fr.read_file(f, sh)
                st.caption("Preview (first 5 rows)")
                st.dataframe(df.head(5), use_container_width=True)

                cols = pd.DataFrame(sm.columns_to_rows(sm.infer_schema(df)))
                st.caption("Review and edit the rules, then save.")
                edited = st.data_editor(
                    cols, key=f"ed_{i}_{label}", use_container_width=True,
                    disabled=["name"], column_config=COLUMN_CONFIG)
                name = st.text_input("Schema name", sm.safe_name(label),
                                     key=f"nm_{i}_{label}")

                if st.button(f"Save schema '{name}'", key=f"sv_{i}_{label}"):
                    output = sm.rows_to_columns(edited.to_dict("records"))
                    problems = sm.validate_columns(output)
                    if problems:
                        for p in problems:
                            st.error(p)
                    else:
                        existed = name in get_schema_names()
                        if existed:
                            st.warning(f"Schema '{name}' already exists. "
                                       "It was replaced with a new version.")
                        saved = sm.save_schema(name, output)
                        st.success(f"Schema '{saved}' saved"
                                   + (" (new version)." if existed else "."))
        except Exception as e:
            st.error(f"Could not process file: {e}")

# ---------------- Page 2: Validate ----------------
elif page.startswith("2"):
    st.header("Validate a Data File")
    names = get_schema_names()
    if not names:
        st.info("No schemas yet. Please create one first.")
    else:
        schema_name = st.selectbox("Choose schema", names)
        f = st.file_uploader("Upload data file", type=["csv", "xlsx"], key="v")
        if f:
            try:
                sheet = None
                if fr.is_excel(f):
                    sheet = st.selectbox("Sheet", fr.list_sheets(f))

                if st.button("Run validation", type="primary"):
                    st.session_state.pop("result", None)  # clear old result
                    df = fr.read_file(f, sheet)

                    # Empty-file check
                    if df.empty:
                        st.error("❌ The file has no data rows. Please upload "
                                 "a file that contains data.")
                        st.stop()

                    schema = sm.load_schema(schema_name)
                    match = check_schema_match(df, schema)

                    if match["is_wrong_schema"]:
                        st.error(
                            f"❌ Wrong schema selected. Only {len(match['found'])} "
                            f"of {len(schema['columns'])} schema columns were "
                            "found in this file. Please choose the correct schema."
                        )
                        all_schemas = {n: sm.load_schema(n) for n in names}
                        best, ratio = suggest_schema(df, all_schemas)
                        if best and best != schema_name and ratio >= 0.5:
                            st.info(f"💡 Suggested schema: **{best}** "
                                    f"({ratio:.0%} of columns match).")
                        else:
                            st.info("💡 No saved schema matches this file. Go to "
                                    "**Create Schema** to create one.")
                        with st.expander("Column comparison"):
                            st.write("**Missing from file:**",
                                     ", ".join(match["missing"]) or "-")
                            st.write("**Unexpected in file:**",
                                     ", ".join(match["extra"]) or "-")
                    else:
                        structure, errs, invalid = validate(df, schema)
                        st.session_state["result"] = (len(df), structure, errs, invalid)
            except Exception as e:
                st.error(f"Could not process file: {e}")

        if "result" in st.session_state:
            total, structure, errs, invalid = st.session_state["result"]
            has_missing = any(m.startswith("Missing columns") for m in structure)
            for message in structure:
                if message.startswith("Missing columns"):
                    st.error(message)
                else:
                    st.warning(message)

            c1, c2, c3 = st.columns(3)
            c1.metric("Total rows", f"{total:,}")
            c2.metric("Invalid rows", f"{len(invalid):,}")
            c3.metric("Valid rows", f"{total - len(invalid):,}")

            if has_missing:
                st.error("Validation incomplete: required columns are missing.")
            elif errs.empty:
                st.success("🎉 All rows passed validation.")

            if not errs.empty:
                st.subheader("Errors by column")
                st.bar_chart(errs["Column"].value_counts())

                st.subheader("Invalid rows")
                st.dataframe(invalid.head(MAX_SHOW), use_container_width=True)
                if len(invalid) > MAX_SHOW:
                    st.info(f"Showing the first {MAX_SHOW:,} of {len(invalid):,} "
                            "invalid rows. Download the file to see all of them.")

                with st.expander("Cell-level error list"):
                    st.dataframe(errs.head(MAX_SHOW), use_container_width=True)

                d1, d2 = st.columns(2)
                d1.download_button(
                    "⬇ Download CSV",
                    invalid.to_csv(index=False).encode("utf-8-sig"),
                    "invalid_rows.csv", "text/csv")
                if len(invalid) < 1_000_000:
                    d2.download_button(
                        "⬇ Download Excel", to_excel_bytes(invalid),
                        "invalid_rows.xlsx")
                else:
                    d2.warning("Too many rows for Excel. Please use CSV.")

# ---------------- Page 3: Manage ----------------
else:
    st.header("Saved Schemas")
    names = get_schema_names()
    if not names:
        st.info("No schemas saved yet.")

    for n in names:
        s = sm.load_schema(n)
        title = (f"{n}  (v{s['version']}, updated "
                 f"{s.get('updated_at', s['created_at'])}"
                 f"{' by ' + s['updated_by'] if s.get('updated_by') else ''})")
        with st.expander(title):
            rows = sm.columns_to_rows(s["columns"])

            st.caption("Edit the table below. Use the empty last row to add a "
                       "column. Select a row and press Delete to remove it. "
                       "Scroll right to see all rule columns.")
            edited = st.data_editor(
                pd.DataFrame(rows),
                key=f"edit_{n}",
                num_rows="dynamic",
                use_container_width=True,
                column_config=COLUMN_CONFIG,
            )

            col_save, col_del = st.columns([1, 1])

            if col_save.button("💾 Save changes", key=f"save_{n}"):
                new_cols = sm.rows_to_columns(edited.to_dict("records"))
                problems = sm.validate_columns(new_cols)
                if problems:
                    for p in problems:
                        st.error(p)
                else:
                    try:
                        sm.save_schema(n, new_cols, expected_version=s["version"])
                        st.success("Schema updated. Version increased.")
                        st.rerun()
                    except sm.SchemaConflictError as e:
                        st.error(str(e))

            confirm = col_del.checkbox("Yes, delete this schema", key=f"cf_{n}")
            if col_del.button("🗑 Delete schema", key=f"del_{n}", disabled=not confirm):
                sm.delete_schema(n)
                st.rerun()