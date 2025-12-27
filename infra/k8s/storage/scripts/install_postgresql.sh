#!/bin/bash

set -eu

APP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "${APP_DIR}" || exit 1

helm upgrade --install openhouse-postgresql helm/postgresql -f config/postgresql.yaml 
