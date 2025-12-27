#!/bin/bash

set -eu

APP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "${APP_DIR}" || exit 1

helm template openhouse-spark-operator helm/spark-operator -f config/spark.yaml > test_template/spark_operator_template.yaml