#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "${PROJECT_ROOT}/.env.dbt" ]]; then
    set -a 
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/.env.dbt" #Dùng để bơm cấu hình để chạy dbt run
    set +a
fi

exec uv run dbt \
    --project-dir "${PROJECT_ROOT}/dbt" \
    --profiles-dir "${PROJECT_ROOT}/dbt" \
    "$@"
