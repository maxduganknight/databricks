# Databricks notebook source
# MAGIC %md
# MAGIC # Revenue Forecasting - Model Training & Out-of-Time Validation
# MAGIC
# MAGIC - **5 years of data** (2021-2025), ~260 weekly observations
# MAGIC - **4 quarters of out-of-time validation** (Q1-Q4 2025)
# MAGIC - **Target**: `total_revenue` for the upcoming quarter (13-week sum)
# MAGIC - **Models**: XGBoost, LightGBM, Random Forest, Ridge Regression
# MAGIC - **Evaluation**: RMSE on each OOT quarter, compared in MLflow
# MAGIC - **Best model** registered and deployed

# COMMAND ----------

CATALOG = "demand_forecast_demo_catalog"
SCHEMA = "revenue_forecasting"
EXPERIMENT_NAME = "/Shared/revenue_forecasting_ml/model_comparison"

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

# COMMAND ----------

import pandas as pd
import numpy as np
import mlflow
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

mlflow.set_experiment(EXPERIMENT_NAME)

# Load features
features_pd = spark.table("sales_features").toPandas()
features_pd["week_start"] = pd.to_datetime(features_pd["week_start"])
features_pd = features_pd.sort_values("week_start").reset_index(drop=True)

print(f"Total rows: {len(features_pd)}")
print(f"Date range: {features_pd['week_start'].min()} to {features_pd['week_start'].max()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Create Target Variable
# MAGIC
# MAGIC Target: total revenue for the **next 13 weeks** (1 quarter ahead)

# COMMAND ----------

# Forward-looking 13-week revenue sum (what we're predicting)
features_pd["target_next_quarter_revenue"] = (
    features_pd["total_revenue"]
    .shift(-1)
    .rolling(window=13, min_periods=13)
    .sum()
    .shift(-12)
)

# Drop rows where target is NaN (last 13 weeks have no full forward quarter)
model_data = features_pd.dropna(subset=["target_next_quarter_revenue"]).copy()

print(f"Rows with valid target: {len(model_data)}")
print(f"Date range for modeling: {model_data['week_start'].min()} to {model_data['week_start'].max()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Define Out-of-Time Validation Splits
# MAGIC
# MAGIC 4 OOT quarters in 2025: each trained on all prior data

# COMMAND ----------

oot_splits = [
    {
        "name": "2024-Q1",
        "train_end": "2023-12-31",
        "test_start": "2024-01-01",
        "test_end": "2024-03-31",
    },
    {
        "name": "2024-Q2",
        "train_end": "2024-03-31",
        "test_start": "2024-04-01",
        "test_end": "2024-06-30",
    },
    {
        "name": "2024-Q3",
        "train_end": "2024-06-30",
        "test_start": "2024-07-01",
        "test_end": "2024-09-30",
    },
    {
        "name": "2024-Q4",
        "train_end": "2024-09-30",
        "test_start": "2024-10-01",
        "test_end": "2024-12-31",
    },
]

for split in oot_splits:
    train = model_data[model_data["week_start"] <= split["train_end"]]
    test = model_data[
        (model_data["week_start"] >= split["test_start"]) &
        (model_data["week_start"] <= split["test_end"])
    ]
    print(f"{split['name']}: train={len(train)} rows, test={len(test)} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Feature Selection

# COMMAND ----------

# Exclude non-feature columns
exclude_cols = [
    "week_start", "total_revenue", "total_units", "transaction_count",
    "target_next_quarter_revenue",
    # Drop the raw weekly category revenue (we keep the rolling versions)
    "weekly_revenue_tables", "weekly_revenue_beds", "weekly_revenue_chairs",
    "weekly_revenue_patio_furniture", "weekly_revenue_sofas", "weekly_revenue_desks",
    "weekly_units_tables", "weekly_units_beds", "weekly_units_chairs",
    "weekly_units_patio_furniture", "weekly_units_sofas", "weekly_units_desks",
    "weekly_revenue_toronto", "weekly_revenue_vancouver", "weekly_revenue_montreal",
    "weekly_revenue_calgary", "weekly_revenue_edmonton",
]

feature_columns = [c for c in model_data.columns if c not in exclude_cols]
target_col = "target_next_quarter_revenue"

print(f"Feature columns ({len(feature_columns)}):")
for f in sorted(feature_columns):
    print(f"  {f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Model Definitions

# COMMAND ----------

from xgboost import XGBRegressor
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge

try:
    from lightgbm import LGBMRegressor
    HAS_LGBM = True
except ImportError:
    HAS_LGBM = False
    print("LightGBM not available, using GradientBoosting as substitute")

model_configs = {
    "xgboost": {
        "model_class": XGBRegressor,
        "params": {
            "n_estimators": 500,
            "max_depth": 6,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "random_state": 42,
        },
    },
    "lightgbm": {
        "model_class": LGBMRegressor if HAS_LGBM else GradientBoostingRegressor,
        "params": {
            "n_estimators": 500,
            "max_depth": 6,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "random_state": 42,
            **({"colsample_bytree": 0.8, "reg_alpha": 0.1, "reg_lambda": 1.0, "verbosity": -1} if HAS_LGBM else {}),
        },
    },
    "random_forest": {
        "model_class": RandomForestRegressor,
        "params": {
            "n_estimators": 300,
            "max_depth": 10,
            "min_samples_split": 5,
            "min_samples_leaf": 3,
            "random_state": 42,
            "n_jobs": -1,
        },
    },
    "ridge_regression": {
        "model_class": Ridge,
        "params": {
            "alpha": 100.0,
        },
    },
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Train All Models with Out-of-Time Validation

# COMMAND ----------

from sklearn.inspection import permutation_importance

results = []
best_rmse = float("inf")
best_model_name = None
best_model_obj = None
best_model_features = None

for model_name, config in model_configs.items():
    print(f"\n{'='*60}")
    print(f"Training: {model_name}")
    print(f"{'='*60}")

    with mlflow.start_run(run_name=f"revenue_forecast_{model_name}") as parent_run:
        mlflow.log_param("model_type", model_name)
        mlflow.log_param("target", target_col)
        mlflow.log_param("num_features", len(feature_columns))
        mlflow.log_param("oot_quarters", 4)
        mlflow.log_params(config["params"])

        all_oot_preds = []
        all_oot_actuals = []
        quarter_metrics = {}

        for split in oot_splits:
            with mlflow.start_run(run_name=f"{model_name}_{split['name']}", nested=True):
                # Split data
                train = model_data[model_data["week_start"] <= split["train_end"]]
                test = model_data[
                    (model_data["week_start"] >= split["test_start"]) &
                    (model_data["week_start"] <= split["test_end"])
                ]

                X_train = train[feature_columns].values
                y_train = train[target_col].values
                X_test = test[feature_columns].values
                y_test = test[target_col].values

                # Train
                model = config["model_class"](**config["params"])
                model.fit(X_train, y_train)

                # Predict
                y_pred = model.predict(X_test)

                # Metrics
                rmse = np.sqrt(mean_squared_error(y_test, y_pred))
                mae = mean_absolute_error(y_test, y_pred)
                r2 = r2_score(y_test, y_pred) if len(y_test) > 1 else 0.0
                mape = np.mean(np.abs((y_test - y_pred) / y_test)) * 100

                mlflow.log_metric("rmse", rmse)
                mlflow.log_metric("mae", mae)
                mlflow.log_metric("r2", r2)
                mlflow.log_metric("mape", mape)
                mlflow.log_metric("train_size", len(train))
                mlflow.log_metric("test_size", len(test))

                quarter_metrics[split["name"]] = {"rmse": rmse, "mae": mae, "r2": r2, "mape": mape}
                all_oot_preds.extend(y_pred.tolist())
                all_oot_actuals.extend(y_test.tolist())

                print(f"  {split['name']}: RMSE=${rmse:,.0f}, MAE=${mae:,.0f}, MAPE={mape:.1f}%, R2={r2:.3f}")

        # Overall OOT metrics
        overall_rmse = np.sqrt(mean_squared_error(all_oot_actuals, all_oot_preds))
        overall_mae = mean_absolute_error(all_oot_actuals, all_oot_preds)
        overall_r2 = r2_score(all_oot_actuals, all_oot_preds)
        overall_mape = np.mean(np.abs(
            (np.array(all_oot_actuals) - np.array(all_oot_preds)) / np.array(all_oot_actuals)
        )) * 100

        mlflow.log_metric("overall_oot_rmse", overall_rmse)
        mlflow.log_metric("overall_oot_mae", overall_mae)
        mlflow.log_metric("overall_oot_r2", overall_r2)
        mlflow.log_metric("overall_oot_mape", overall_mape)

        # Train final model on ALL data for deployment
        X_all = model_data[feature_columns].values
        y_all = model_data[target_col].values
        final_model = config["model_class"](**config["params"])
        final_model.fit(X_all, y_all)

        # Compute permutation-based feature importance on last OOT split
        last_test = model_data[
            (model_data["week_start"] >= oot_splits[-1]["test_start"]) &
            (model_data["week_start"] <= oot_splits[-1]["test_end"])
        ]
        X_last_test = last_test[feature_columns].values
        y_last_test = last_test[target_col].values

        perm_imp = permutation_importance(
            model, X_last_test, y_last_test,
            n_repeats=10, random_state=42, scoring="neg_root_mean_squared_error"
        )

        importance_df = pd.DataFrame({
            "feature": feature_columns,
            "importance_mean": perm_imp.importances_mean,
            "importance_std": perm_imp.importances_std,
        }).sort_values("importance_mean", ascending=False)

        # Log top features
        for _, row in importance_df.head(15).iterrows():
            mlflow.log_metric(f"perm_imp_{row['feature']}", row["importance_mean"])

        # Log the final model (with input_example so MLflow infers signature for UC)
        mlflow.sklearn.log_model(
            final_model,
            artifact_path="model",
            input_example=pd.DataFrame([X_all[0]], columns=feature_columns),
        )

        # Log feature importance as artifact
        import tempfile, os
        tmp_path = os.path.join(tempfile.gettempdir(), "feature_importance.csv")
        importance_df.to_csv(tmp_path, index=False)
        mlflow.log_artifact(tmp_path)

        print(f"\n  Overall OOT: RMSE=${overall_rmse:,.0f}, MAE=${overall_mae:,.0f}, "
              f"MAPE={overall_mape:.1f}%, R2={overall_r2:.3f}")

        results.append({
            "model": model_name,
            "overall_rmse": overall_rmse,
            "overall_mae": overall_mae,
            "overall_r2": overall_r2,
            "overall_mape": overall_mape,
            "run_id": parent_run.info.run_id,
        })

        # Track best
        if overall_rmse < best_rmse:
            best_rmse = overall_rmse
            best_model_name = model_name
            best_model_obj = final_model
            best_model_features = feature_columns.copy()
            best_run_id = parent_run.info.run_id
            best_importance_df = importance_df.copy()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Model Comparison

# COMMAND ----------

results_df = pd.DataFrame(results).sort_values("overall_rmse")
print("\n" + "="*80)
print("MODEL COMPARISON (sorted by RMSE)")
print("="*80)
print(results_df.to_string(index=False))
print(f"\nBest model: {best_model_name} (RMSE=${best_rmse:,.0f})")

# Save comparison table
df_comparison = spark.createDataFrame(results_df)
df_comparison.write.mode("overwrite").saveAsTable("model_comparison")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Register Best Model

# COMMAND ----------

MODEL_NAME = f"{CATALOG}.{SCHEMA}.revenue_forecast_model"

# Register the best model
model_uri = f"runs:/{best_run_id}/model"
registered = mlflow.register_model(model_uri, MODEL_NAME)

print(f"Registered model: {MODEL_NAME}")
print(f"  Version: {registered.version}")
print(f"  Best model type: {best_model_name}")
print(f"  Overall OOT RMSE: ${best_rmse:,.0f}")

# Set alias for serving
from mlflow import MlflowClient
client = MlflowClient()
client.set_registered_model_alias(MODEL_NAME, "production", registered.version)
print(f"  Alias 'production' set to version {registered.version}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Save Feature Importance for App

# COMMAND ----------

# Save permutation importance to a table for the dashboard app
importance_data = best_importance_df.copy()
importance_data["model_name"] = best_model_name
importance_data["model_version"] = int(registered.version)

df_importance = spark.createDataFrame(importance_data)
df_importance.write.mode("overwrite").saveAsTable("feature_importance")

print(f"Saved feature importance: {len(importance_data)} features")
print("\nTop 15 features:")
print(importance_data.head(15)[["feature", "importance_mean"]].to_string(index=False))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Save OOT Predictions for App (Actual vs Predicted)

# COMMAND ----------

# Re-run the best model on all OOT splits to save predictions
oot_records = []

for split in oot_splits:
    train = model_data[model_data["week_start"] <= split["train_end"]]
    test = model_data[
        (model_data["week_start"] >= split["test_start"]) &
        (model_data["week_start"] <= split["test_end"])
    ]

    X_train = train[feature_columns].values
    y_train = train[target_col].values
    X_test = test[feature_columns].values
    y_test = test[target_col].values

    model = model_configs[best_model_name]["model_class"](**model_configs[best_model_name]["params"])
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    for i, (_, row) in enumerate(test.iterrows()):
        oot_records.append({
            "week_start": row["week_start"],
            "oot_quarter": split["name"],
            "actual_next_quarter_revenue": y_test[i],
            "predicted_next_quarter_revenue": y_pred[i],
            "residual": y_test[i] - y_pred[i],
            "pct_error": abs(y_test[i] - y_pred[i]) / y_test[i] * 100,
        })

oot_df = pd.DataFrame(oot_records)
df_oot = spark.createDataFrame(oot_df)
df_oot = df_oot.withColumn("week_start", df_oot["week_start"].cast("date"))
df_oot.write.mode("overwrite").saveAsTable("oot_validation_results")

print(f"Saved OOT validation results: {len(oot_records)} rows")
print(f"\nOOT summary by quarter:")
print(oot_df.groupby("oot_quarter").agg(
    avg_pct_error=("pct_error", "mean"),
    median_pct_error=("pct_error", "median"),
).to_string())
