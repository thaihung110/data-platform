#!/bin/bash

set -eu

APP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "${APP_DIR}" || exit 1

helm template openhouse-openfga helm/openfga -f config/openfga.yaml > test_template/openfga_template.yaml
