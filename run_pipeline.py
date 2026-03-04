"""Standalone script to run the ETL pipeline and generate HTML report."""
import argparse
import logging
import os
import sys
from pathlib import Path

# Add workspace root to path
root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if root not in sys.path:
    sys.path.insert(0, root)

from src.extract import extract_data
from src.transform import transform_data
from src.results import export_results_to_html

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
_logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run ETL pipeline and generate HTML results report."
    )
    parser.add_argument(
        "--data-file",
        dest="data_file",
        default="order_data.csv",
        help="name of the CSV file under ./data/ to process",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default="results",
        help="directory where HTML report will be saved",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    try:
        # Extract
        _logger.info("=" * 60)
        _logger.info("Starting ETL Pipeline")
        _logger.info("=" * 60)
        df = extract_data(filename=args.data_file)

        # Transform
        _logger.info("\nPerforming transformations...")
        df_transformed = transform_data(df)

        # Recalculate aggregations for HTML export
        _logger.info("\nGenerating results report...")
        category_sales = (
            df_transformed.groupby("category")["total_amount"]
            .sum().reset_index()
            .rename(columns={"total_amount": "total_sales"})
            .sort_values("total_sales", ascending=False)
        )

        top_customer = (
            df_transformed.groupby("customer_name")["total_amount"]
            .sum().reset_index()
            .rename(columns={"total_amount": "total_spent"})
            .sort_values("total_spent", ascending=False)
        )

        most_sold_product = (
            df_transformed.groupby("product")["quantity"]
            .sum().reset_index()
            .rename(columns={"quantity": "total_quantity"})
            .sort_values("total_quantity", ascending=False)
        )

        # Export to HTML
        html_file = export_results_to_html(
            df_transformed,
            category_sales,
            top_customer,
            most_sold_product,
            output_dir=args.output_dir
        )

        _logger.info("=" * 60)
        _logger.info(f"✅ ETL Pipeline completed successfully!")
        _logger.info(f"📄 Report saved to: {html_file}")
        _logger.info("=" * 60)

        print(f"\n📊 Open this file in your browser: {html_file}")
        return html_file

    except Exception as err:
        _logger.exception("❌ ETL Pipeline failed")
        raise


if __name__ == "__main__":
    main()
