#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/.env"
    set +a
elif [[ -f "${PROJECT_ROOT}/.env.dbt" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/.env.dbt"
    set +a
fi

exec uv run dbt "$@"\
    --project-dir "${PROJECT_ROOT}/dbt" \
    --profiles-dir "${PROJECT_ROOT}/dbt"
