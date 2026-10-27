"""Shared pytest fixtures.

Spark resolution order: an active session (running inside a Databricks notebook), then
Databricks Connect (local IDE + `databricks auth login`), then plain local PySpark.
"""

import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "pipeline"))  # -> `utilities.pdu_rules`
sys.path.insert(0, os.path.join(ROOT, "src", "app"))       # -> `components`

THRESHOLDS_CSV = os.path.join(ROOT, "src", "sql", "pdu_thresholds_seed.csv")


@pytest.fixture(scope="session")
def spark():
    from pyspark.sql import SparkSession

    active = SparkSession.getActiveSession()
    if active is not None:
        return active
    try:
        from databricks.connect import DatabricksSession

        return DatabricksSession.builder.serverless(True).getOrCreate()
    except ImportError:
        return (
            SparkSession.builder.master("local[2]")
            .config("spark.sql.session.timeZone", "UTC")
            .config("spark.sql.shuffle.partitions", "2")
            .getOrCreate()
        )


@pytest.fixture(scope="session")
def thresholds_csv():
    return THRESHOLDS_CSV
