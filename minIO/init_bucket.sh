#!/bin/sh

set -eu

MINIO_ALIAS="${MINIO_ALIAS:-local}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://localhost:9000}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-minio}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-minio-secret}"
MINIO_AIRFLOW_USER="${MINIO_AIRFLOW_USER:-fraudguard}"
MINIO_AIRFLOW_PASSWORD="${MINIO_AIRFLOW_PASSWORD:-fraudguard-secret}"

VALID_PATH="s3a://fraud-transactions"
QUARANTINE_PATH="s3a://fraud-transactions-quarantine"
CHECKPOINT_PATH="s3a://fraud-transactions-checkpoint"
LABEL_VALID_PATH="s3a://fraud-transaction-labels"
LABEL_QUARANTINE_PATH="s3a://fraud-transaction-labels-quarantine"
LABEL_CHECKPOINT_PATH="s3a://fraud-transaction-labels-checkpoint"

mc alias set \
    "$MINIO_ALIAS" \
    "$MINIO_ENDPOINT" \
    "$MINIO_ROOT_USER" \
    "$MINIO_ROOT_PASSWORD"

mc admin user add \
    "$MINIO_ALIAS" \
    "$MINIO_AIRFLOW_USER" \
    "$MINIO_AIRFLOW_PASSWORD"

mc admin policy attach \
    "$MINIO_ALIAS" \
    readwrite \
    --user "$MINIO_AIRFLOW_USER"

for s3a_path in \
    "$VALID_PATH" \
    "$QUARANTINE_PATH" \
    "$CHECKPOINT_PATH" \
    "$LABEL_VALID_PATH" \
    "$LABEL_QUARANTINE_PATH" \
    "$LABEL_CHECKPOINT_PATH"
do
    bucket_name="${s3a_path#s3a://}"
    mc mb --ignore-existing "$MINIO_ALIAS/$bucket_name"
done
