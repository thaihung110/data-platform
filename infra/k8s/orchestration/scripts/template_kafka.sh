#!/bin/bash

set -eu

APP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "${APP_DIR}" || exit 1

helm template openhouse-kafka helm/kafka -f config/kafka.yaml > test_template/kafka_template.yaml

