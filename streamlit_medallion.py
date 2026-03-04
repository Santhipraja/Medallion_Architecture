"""Streamlit Medallion ETL Pipeline — Universal Auto-Detect Edition.

Upload ANY file type (CSV, Excel, JSON, TSV, Parquet).
No manual column mapping needed — the pipeline auto-detects
numeric, categorical, and date columns automatically.

Bronze  → Raw ingestion (any file type → standardised CSV)
Silver  → Auto-clean: parse dates, coerce numerics, drop empty cols,
          derive _total_value (qty × price or first numeric col)
Gold    → Auto-aggregate: all numeric cols × all categorical cols
"""
import os
import sys
import logging
import shutil
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

# ── bootstrap ─────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.WARNING)
root = os.path.abspath(os.path.dirname(__file__))
if root not in sys.path:
    sys.path.insert(0, root)

project_root = Path(root)
data_dir = project_root / "data"
data_dir.mkdir(exist_ok=True)

BRONZE_DIR = data_dir / "bronze"
SILVER_DIR = data_dir / "silver"
GOLD_DIR   = data_dir / "gold"

# ── supported file types ──────────────────────────────────────────────────────
SUPPORTED_TYPES = ["csv", "xlsx", "xls", "json", "tsv"]

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Medallion ETL", page_icon="🏛️", layout="wide")

st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background: #ffffff; }
    [data-testid="stSidebar"]          { background: #f3f4f6; border-right: 1px solid #e5e7eb; }
    .medal-card {
        border-radius: 12px; padding: 18px 20px;
        text-align: center; font-size: 1.05rem;
        font-weight: 600; margin-bottom: 8px;
    }
    .bronze-card { background: linear-gradient(135deg,#92400e,#d97706); color:#fff; }
    .silver-card { background: linear-gradient(135deg,#4b5563,#9ca3af); color:#fff; }
    .gold-card   { background: linear-gradient(135deg,#b45309,#fbbf24); color:#fff; }
    .metric-box  {
        background:#f9fafb; border:1px solid #e5e7eb;
        border-radius:10px; padding:16px; text-align:center;
    }
    .metric-value { font-size:2rem; font-weight:700; color:#4f46e5; }
    .metric-label { font-size:0.85rem; color:#6b7280; margin-top:4px; }
    .tag {
        display:inline-block; background:#ede9fe; color:#5b21b6;
        border-radius:6px; padding:2px 8px; font-size:0.8rem;
        margin:2px; font-weight:500;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# File reading — supports CSV, Excel, JSON, TSV, Parquet
# ─────────────────────────────────────────────────────────────────────────────

def read_any_file(path: Path, sheet_name=0) -> pd.DataFrame:
    """Read any supported file type into a DataFrame."""
    ext = path.suffix.lower()
    if ext in (".xlsx", ".xls"):
        try:
            return pd.read_excel(path, sheet_name=sheet_name)
        except ImportError:
            st.error(
                "❌ Reading Excel files requires **openpyxl**. "
                "Run this in your terminal then restart the app:\n\n"
                "```\npip install openpyxl\n```"
            )
            st.stop()
    if ext == ".json":
        return pd.read_json(path)
    if ext in (".tsv", ".tab"):
        try:
            return pd.read_csv(path, sep="\t")
        except Exception:
            return pd.read_csv(path, sep="\t", on_bad_lines="skip", engine="python")
    if ext == ".parquet":
        return pd.read_parquet(path)
    # Default: CSV with bad-line fallback
    try:
        return pd.read_csv(path)
    except Exception:
        df = pd.read_csv(path, on_bad_lines="skip", engine="python")
        st.warning("⚠️ Some malformed rows were skipped.")
        return df


def get_sheet_names(path: Path):
    if path.suffix.lower() in (".xlsx", ".xls"):
        try:
            return pd.ExcelFile(path).sheet_names
        except ImportError:
            st.error(
                "❌ Reading Excel files requires **openpyxl**. "
                "Run this in your terminal then restart the app:\n\n"
                "```\npip install openpyxl\n```"
            )
            st.stop()
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline stages
# ─────────────────────────────────────────────────────────────────────────────

def run_bronze(input_path: Path, sheet_name=0) -> pd.DataFrame:
    """Stage 1 — Ingest any file, standardise as CSV in bronze dir."""
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)
    df = read_any_file(input_path, sheet_name=sheet_name)
    df.to_csv(BRONZE_DIR / "data.csv", index=False)
    return df


def run_silver(df_bronze: pd.DataFrame) -> pd.DataFrame:
    """Stage 2 — Auto-clean & enrich.

    - Drop fully-empty columns
    - Auto-parse date-like columns
    - Coerce object columns that look numeric
    - Derive _total_value:  qty × price  OR  first numeric column
    """
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    df = df_bronze.copy()

    # Drop fully empty columns
    df = df.dropna(axis=1, how="all")

    # Auto-parse date columns
    for col in df.columns:
        if df[col].dtype == object:
            try:
                parsed = pd.to_datetime(df[col], errors="coerce", infer_datetime_format=True)
                if parsed.notna().sum() / max(len(df), 1) > 0.6:   # >60% parse success
                    df[col] = parsed
            except Exception:
                pass

    # Coerce object columns that are actually numeric
    for col in df.select_dtypes(include="object").columns:
        coerced = pd.to_numeric(df[col].str.replace(",", "", regex=False), errors="coerce")
        if coerced.notna().sum() / max(len(df), 1) > 0.8:
            df[col] = coerced

    # Derive _total_value
    num_cols = df.select_dtypes(include="number").columns.tolist()
    qty_candidates   = [c for c in num_cols if any(k in c.lower() for k in ["qty","quantity","units","count","amount_qty"])]
    price_candidates = [c for c in num_cols if any(k in c.lower() for k in ["price","rate","cost","amount","revenue","sales","value","total"])]

    if qty_candidates and price_candidates:
        df["_total_value"] = df[qty_candidates[0]] * df[price_candidates[0]]
    elif price_candidates:
        df["_total_value"] = df[price_candidates[0]]
    elif num_cols:
        df["_total_value"] = df[num_cols[0]]
    else:
        df["_total_value"] = 0

    # Year / month from first date column
    date_cols = df.select_dtypes(include=["datetime64"]).columns.tolist()
    if date_cols:
        df["_year"]  = df[date_cols[0]].dt.year
        df["_month"] = df[date_cols[0]].dt.month

    df.to_csv(SILVER_DIR / "data.csv", index=False)
    return df


def run_gold(df_silver: pd.DataFrame) -> dict:
    """Stage 3 — Auto-aggregate _total_value by every categorical column."""
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    results = {}

    cat_cols = df_silver.select_dtypes(include=["object", "category"]).columns.tolist()
    # Exclude very high-cardinality cols (IDs etc.)
    cat_cols = [c for c in cat_cols if df_silver[c].nunique() <= 100]

    for col in cat_cols:
        agg = (
            df_silver.groupby(col)["_total_value"]
            .sum()
            .reset_index()
            .rename(columns={"_total_value": "total_value"})
            .sort_values("total_value", ascending=False)
        )
        agg.to_csv(GOLD_DIR / f"{col}_summary.csv", index=False)
        results[col] = agg

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────────────────────
for k, v in {
    "completed":    {"bronze": False, "silver": False, "gold": False},
    "bronze_df":    None,
    "silver_df":    None,
    "gold_results": None,
}.items():
    st.session_state.setdefault(k, v)

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📂 Upload File")
    st.caption(f"Supported: **{', '.join(f'.{t}' for t in SUPPORTED_TYPES)}**")

    uploaded = st.file_uploader(
        "Drop any data file here",
        type=SUPPORTED_TYPES,
    )

    if uploaded:
        ext       = Path(uploaded.name).suffix.lower()
        input_path = data_dir / f"uploaded{ext}"
        input_path.write_bytes(uploaded.getbuffer())
        st.success(f"✅ **{uploaded.name}** ready")
    else:
        input_path = data_dir / "order_data.csv"
        st.info("Using default: **order_data.csv**")

    if not input_path.exists():
        st.error("❌ File not found. Please upload a file.")
        st.stop()

    # Sheet selector for Excel
    sheet_name = 0
    sheets = get_sheet_names(input_path)
    if sheets and len(sheets) > 1:
        sheet_name = st.selectbox("📋 Sheet", sheets)

    st.divider()
    st.markdown("## ▶️ Run Pipeline")
    run_all    = st.button("🚀 Execute All Stages",  use_container_width=True, type="primary")
    btn_bronze = st.button("🔵 Bronze — Ingest",     use_container_width=True)
    btn_silver = st.button("🟢 Silver — Auto-Clean", use_container_width=True)
    btn_gold   = st.button("🟡 Gold — Auto-Aggregate", use_container_width=True)

    st.divider()
    if st.button("🗑️ Reset All", use_container_width=True):
        for d in [BRONZE_DIR, SILVER_DIR, GOLD_DIR]:
            shutil.rmtree(d, ignore_errors=True)
        for key in ["bronze_df","silver_df","gold_results","completed"]:
            st.session_state.pop(key, None)
        st.success("All layers cleared.")
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Title & stage badges
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("# 🏛️ Medallion Architecture ETL Pipeline")
st.markdown("> Upload **any data file** — the pipeline auto-detects columns and runs Bronze → Silver → Gold automatically.")
st.divider()

c1, c2, c3 = st.columns(3)
for col_ui, css, label, key in [
    (c1, "bronze-card", "🔵 Bronze — Ingested",   "bronze"),
    (c2, "silver-card", "🟢 Silver — Cleaned",    "silver"),
    (c3, "gold-card",   "🟡 Gold — Aggregated",   "gold"),
]:
    tick = "✅" if st.session_state.completed[key] else "⏳"
    col_ui.markdown(f'<div class="medal-card {css}">{tick} {label}</div>', unsafe_allow_html=True)

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# File preview
# ─────────────────────────────────────────────────────────────────────────────
try:
    _preview = read_any_file(input_path, sheet_name=sheet_name)
    num_cols_p  = _preview.select_dtypes(include="number").columns.tolist()
    cat_cols_p  = _preview.select_dtypes(include="object").columns.tolist()
except Exception as e:
    st.error(f"Cannot read file: {e}")
    st.stop()

with st.expander(f"📄 File Preview — {input_path.name} ({len(_preview):,} rows × {len(_preview.columns)} cols)", expanded=True):
    st.dataframe(_preview.head(10), use_container_width=True)
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**🔢 Numeric columns detected:**")
        st.markdown(" ".join(f'<span class="tag">{c}</span>' for c in num_cols_p) or "_None_", unsafe_allow_html=True)
    with col_b:
        st.markdown("**🔤 Categorical columns detected:**")
        st.markdown(" ".join(f'<span class="tag">{c}</span>' for c in cat_cols_p) or "_None_", unsafe_allow_html=True)

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Pipeline execution
# ─────────────────────────────────────────────────────────────────────────────

# Bronze
if run_all or btn_bronze:
    with st.spinner("🔵 Bronze — Ingesting file…"):
        try:
            df = run_bronze(input_path, sheet_name=sheet_name)
            st.session_state.bronze_df = df
            st.session_state.completed["bronze"] = True
            st.success(f"✅ Bronze complete — **{len(df):,} rows · {len(df.columns)} columns**")
        except Exception as exc:
            st.error(f"❌ Bronze failed: {exc}")

# Silver
if run_all or btn_silver:
    src = st.session_state.bronze_df
    if src is None:
        st.warning("⚠️ Run Bronze first.")
    else:
        with st.spinner("🟢 Silver — Auto-cleaning & enriching…"):
            try:
                df = run_silver(src)
                st.session_state.silver_df = df
                st.session_state.completed["silver"] = True
                date_info = f" · `_year`/`_month` extracted" if "_year" in df.columns else ""
                st.success(f"✅ Silver complete — `_total_value` derived{date_info}")
            except Exception as exc:
                st.error(f"❌ Silver failed: {exc}")

# Gold
if run_all or btn_gold:
    src = st.session_state.silver_df
    if src is None:
        st.warning("⚠️ Run Silver first.")
    else:
        with st.spinner("🟡 Gold — Auto-aggregating…"):
            try:
                results = run_gold(src)
                st.session_state.gold_results = results
                st.session_state.completed["gold"] = True
                st.success(f"✅ Gold complete — **{len(results)} aggregation(s)**: {', '.join(f'`{k}`' for k in results)}")
            except Exception as exc:
                st.error(f"❌ Gold failed: {exc}")

# ─────────────────────────────────────────────────────────────────────────────
# Summary metrics
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.silver_df is not None:
    df_s = st.session_state.silver_df
    total_val = df_s["_total_value"].sum() if "_total_value" in df_s.columns else 0
    st.markdown("### 📊 Summary Metrics")
    m1, m2, m3, m4 = st.columns(4)
    for col_ui, val, label in [
        (m1, f"{len(df_s):,}",      "Total Rows"),
        (m2, f"{len(df_s.columns)}","Columns"),
        (m3, f"${total_val:,.2f}",  "Total Value"),
        (m4, f"{df_s.select_dtypes(include='number').shape[1]}", "Numeric Cols"),
    ]:
        col_ui.markdown(
            f'<div class="metric-box"><div class="metric-value">{val}</div>'
            f'<div class="metric-label">{label}</div></div>',
            unsafe_allow_html=True
        )
    st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Layer viewer tabs
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("### 🔍 Inspect Each Layer")
tab_b, tab_s, tab_g = st.tabs(["🔵 Bronze", "🟢 Silver", "🟡 Gold"])

with tab_b:
    df_b = st.session_state.bronze_df
    if df_b is not None:
        st.caption(f"{len(df_b):,} rows · {len(df_b.columns)} columns — raw, unmodified data")
        st.dataframe(df_b.head(50), use_container_width=True)
    else:
        st.info("▶️ Click **Bronze — Ingest** or **Execute All** in the sidebar.")

with tab_s:
    df_s = st.session_state.silver_df
    if df_s is not None:
        extras = [c for c in ["_total_value","_year","_month"] if c in df_s.columns]
        st.caption(f"{len(df_s):,} rows · {len(df_s.columns)} columns · added: {', '.join(f'`{c}`' for c in extras)}")
        st.dataframe(df_s.head(50), use_container_width=True)
    else:
        st.info("▶️ Run the Silver stage to see enriched data.")

with tab_g:
    results = st.session_state.gold_results
    if results:
        gcols = list(results.keys())
        if gcols:
            sub_tabs = st.tabs([f"📦 By {c}" for c in gcols])
            for sub_tab, gcol in zip(sub_tabs, gcols):
                with sub_tab:
                    df_agg = results[gcol]
                    col_l, col_r = st.columns([1, 1])
                    with col_l:
                        st.dataframe(df_agg, use_container_width=True)
                        st.download_button(
                            f"⬇️ Download {gcol}_summary.csv",
                            data=df_agg.to_csv(index=False).encode(),
                            file_name=f"gold_{gcol}_summary.csv",
                            mime="text/csv",
                        )
                    with col_r:
                        if not df_agg.empty and len(df_agg) <= 30:
                            st.bar_chart(df_agg.set_index(gcol)["total_value"])
                        elif not df_agg.empty:
                            st.bar_chart(df_agg.head(20).set_index(gcol)["total_value"])
                            st.caption("Showing top 20")
    else:
        st.info("▶️ Run the Gold stage to see aggregated insights.")

# ─────────────────────────────────────────────────────────────────────────────
st.divider()
st.caption(f"🏛️ Medallion ETL · Universal Auto-Detect Edition · {datetime.now().strftime('%Y-%m-%d %H:%M')}")
