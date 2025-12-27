#!/bin/bash

set -eu

APP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "${APP_DIR}" || exit 1

helm template openhouse-lakekeeper helm/lakekeeper -f config/lakekeeper.yaml > test_template/lakekeeper_template.yaml
