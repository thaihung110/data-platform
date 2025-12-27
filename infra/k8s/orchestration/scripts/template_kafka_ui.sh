#!/bin/bash

set -eu

APP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "${APP_DIR}" || exit 1

helm template openhouse-kafka-ui helm/kafka-ui -f config/kafka-ui.yaml > test_template/kafka-ui_template.yaml

