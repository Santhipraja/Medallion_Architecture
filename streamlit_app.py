import os
import pandas as pd

# streamlit is an optional dependency so that helper functions can be imported
# in environments where it isn't installed (e.g. during unit tests).  We
# delay the import and fall back to None when unavailable.
try:
    import streamlit as st
except ImportError:  # pragma: no cover - streamlit may not be installed here
    st = None


# Helper functions for testing and reuse

def load_data(uploaded_file=None, default_path="data/order_data.csv"):
    """Load data from an uploaded file or from the default CSV path.

    The original file has occasionally been malformed (extra commas or stray
    characters) which causes ``pandas`` to raise a ``CParserError``.  We
    attempt to read normally first; if that fails we fall back to a more
    tolerant mode that skips bad lines and reports how many were dropped.

    Parameters
    ----------
    uploaded_file : UploadedFile or None
        Streamlit uploaded file object.
    default_path : str
        Relative path to the default CSV file.

    Returns
    -------
    
    pandas.DataFrame
        The loaded data.
    """
    path = uploaded_file if uploaded_file is not None else default_path

    try:
        # pandas 1.3+ supports on_bad_lines
        return pd.read_csv(path)
    except Exception as exc:  # catch parsing errors
        # try again skipping malformed lines; this will drop problematic rows
        try:
            df = pd.read_csv(path, on_bad_lines="skip")
            dropped = " (some rows skipped due to parse errors)"
            # attach info so caller can warn user
            df.attrs["warning"] = str(exc)
            df.attrs["dropped_rows"] = True
            return df
        except TypeError:
            # older pandas fallback
            df = pd.read_csv(path, error_bad_lines=False, warn_bad_lines=True)
            df.attrs["warning"] = str(exc)
            df.attrs["dropped_rows"] = True
            return df


def compute_metrics(df: pd.DataFrame) -> dict:
    """Compute summary statistics and aggregations for the passed dataframe.

    The function adds a ``total_amount`` column and returns several
    pre‑aggregated series that the Streamlit app can visualize.
    """
    df = df.copy()
    # ensure correct types
    if "quantity" in df.columns and "price" in df.columns:
        df["total_amount"] = df["quantity"] * df["price"]
    if "order_date" in df.columns:
        df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")

    total_orders = len(df)
    total_revenue = df["total_amount"].sum() if "total_amount" in df.columns else 0
    unique_categories = df["category"].nunique() if "category" in df.columns else 0
    unique_customers = df["customer_name"].nunique() if "customer_name" in df.columns else 0

    cat_sales = (
        df.groupby("category")["total_amount"]
        .sum()
        .sort_values(ascending=False)
        if "category" in df.columns and "total_amount" in df.columns
        else pd.Series(dtype=float)
    )

    top_customers = (
        df.groupby("customer_name")["total_amount"]
        .sum()
        .sort_values(ascending=False)
        if "customer_name" in df.columns and "total_amount" in df.columns
        else pd.Series(dtype=float)
    )

    most_sold = (
        df.groupby("product")["quantity"]
        .sum()
        .sort_values(ascending=False)
        if "product" in df.columns and "quantity" in df.columns
        else pd.Series(dtype=int)
    )

    return {
        "df": df,
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "unique_categories": unique_categories,
        "unique_customers": unique_customers,
        "cat_sales": cat_sales,
        "top_customers": top_customers,
        "most_sold": most_sold,
    }


# Streamlit UI
if st is not None:
    st.set_page_config(page_title="Sales Analysis", layout="wide")

    st.title("📊 Ecommerce Sales Analysis")

    st.sidebar.header("Configuration")

    uploaded_file = st.sidebar.file_uploader("Upload a CSV file", type="csv")

    try:
        data = load_data(uploaded_file)
    except Exception as err:
        st.sidebar.error(f"Failed to load data: {err}")
        st.stop()

    if data is None or data.empty:
        st.warning("No data available. Please upload a CSV or place one in data/order_data.csv.")
        st.stop()

# notify user if load had to skip bad lines
if getattr(data, "dropped_rows", False):
    st.warning("Some rows were skipped during import due to parse errors.")
    st.caption(f"Original error: {data.attrs.get('warning')}")
    # summary metrics
    st.header("Summary Statistics")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Orders", metrics["total_orders"])
    col2.metric("Total Revenue", f"${metrics['total_revenue']:, .2f}")
    col3.metric("Unique Categories", metrics["unique_categories"])
    col4.metric("Unique Customers", metrics["unique_customers"])

    # visualizations
    st.header("Sales by Category")
    if not metrics["cat_sales"].empty:
        st.bar_chart(metrics["cat_sales"])
    else:
        st.info("No category sales data available.")

    st.header("Top Customers")
    if not metrics["top_customers"].empty:
        st.bar_chart(metrics["top_customers"].head(10))
    else:
        st.info("No customer spending data available.")

    st.header("Most Sold Products")
    if not metrics["most_sold"].empty:
        st.bar_chart(metrics["most_sold"].head(10))
    else:
        st.info("No product quantity data available.")

    # optional download of processed data
    st.sidebar.header("Download")
    csv = df.to_csv(index=False)
    st.sidebar.download_button("Download processed data as CSV", data=csv, file_name="processed_orders.csv")
else:
    # when streamlit isn't installed, provide a friendly message if executed
    if __name__ == "__main__":
        print("Streamlit is not installed; run `pip install streamlit` to use the UI.")
