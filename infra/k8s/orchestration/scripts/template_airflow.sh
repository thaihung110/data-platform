#!/bin/bash

set -eu

APP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "${APP_DIR}" || exit 1

helm template openhouse-airflow helm/airflow -f config/airflow.yaml > test_template/airflow_template.yaml

