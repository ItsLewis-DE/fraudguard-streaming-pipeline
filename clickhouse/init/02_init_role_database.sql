CREATE DATABASE IF NOT EXISTS fraudguard_staging;
CREATE DATABASE IF NOT EXISTS fraudguard_intermediate;
CREATE DATABASE IF NOT EXISTS fraudguard_mart;
CREATE DATABASE IF NOT EXISTS fraudguard_monitoring;

CREATE ROLE IF NOT EXISTS fraudguard_loader_role;
CREATE ROLE IF NOT EXISTS fraudguard_transformer_role;
CREATE ROLE IF NOT EXISTS fraudguard_superset_role;

-- Airflow chỉ nạp dữ liệu thô và đọc/ghi trạng thái ingestion.
GRANT INSERT ON fraudguard.transactions
TO fraudguard_loader_role;

GRANT INSERT ON fraudguard.transaction_labels
TO fraudguard_loader_role;

GRANT SELECT, INSERT ON fraudguard.ingestion_batches
TO fraudguard_loader_role;

GRANT SELECT ON system.tables
TO fraudguard_loader_role;

-- dbt đọc dữ liệu thô và quản lý các lớp dữ liệu phân tích.
GRANT SELECT ON fraudguard.*
TO fraudguard_transformer_role;

GRANT ALL ON fraudguard_staging.*
TO fraudguard_transformer_role;

GRANT ALL ON fraudguard_intermediate.*
TO fraudguard_transformer_role;

GRANT ALL ON fraudguard_mart.*
TO fraudguard_transformer_role;

GRANT ALL ON fraudguard_monitoring.*
TO fraudguard_transformer_role;

GRANT CREATE TEMPORARY TABLE ON *.*
TO fraudguard_transformer_role;

-- Superset chỉ được đọc các bảng phục vụ báo cáo và monitoring.
GRANT SELECT ON fraudguard_mart.*
TO fraudguard_superset_role;

GRANT SELECT ON fraudguard_monitoring.*
TO fraudguard_superset_role;

ALTER ROLE fraudguard_superset_role
SETTINGS
    readonly = 1,
    max_execution_time = 30,
    max_threads = 4,
    max_memory_usage = 2000000000,
    max_rows_to_read = 100000000,
    max_bytes_to_read = 5000000000;
