"""Entry point for running the medallion-style ETL steps from the command line."""
import argparse
import logging
from src.medallion import bronze_ingest, silver_transform, gold_aggregate
from src.extract import get_spark_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
_logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run medallion ETL pipeline: bronze -> silver -> gold."
    )
    parser.add_argument(
        "--step",
        choices=["bronze", "silver", "gold", "all"],
        default="all",
        help="Which stage to execute (default: all).",
    )
    parser.add_argument(
        "--input-csv",
        default="data/order_data.csv",
        help="Source CSV file for bronze stage.",
    )
    parser.add_argument(
        "--bronze-dir",
        default="data/bronze",
        help="Directory for bronze parquet files.",
    )
    parser.add_argument(
        "--silver-dir",
        default="data/silver",
        help="Directory for silver parquet files.",
    )
    parser.add_argument(
        "--gold-dir",
        default="data/gold",
        help="Directory for gold output summaries.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    spark = get_spark_session()
    try:
        if args.step in ("bronze", "all"):
            _logger.info("Running bronze ingestion...")
            bronze_ingest(spark, input_csv=args.input_csv, output_dir=args.bronze_dir)

        if args.step in ("silver", "all"):
            _logger.info("Running silver transformation...")
            silver_transform(spark, bronze_dir=args.bronze_dir, silver_dir=args.silver_dir)

        if args.step in ("gold", "all"):
            _logger.info("Running gold aggregation...")
            gold_aggregate(spark, silver_dir=args.silver_dir, gold_dir=args.gold_dir)

        _logger.info("Medallion pipeline finished successfully.")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
