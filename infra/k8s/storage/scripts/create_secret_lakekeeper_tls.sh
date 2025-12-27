#!/bin/bash

set -eu

APP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "${APP_DIR}" || exit 1

function create_tls {
  domain=$1
  key=$2
  cert=$3
  openssl req -x509 -nodes -days 10000 \
  -newkey rsa:2048 \
  -subj "/CN=${domain}/0=${domain}" \
  -keyout "$key" \
  -out "$cert"
}


function main {
  domain="openhouse.lakekeeper.test"
  key="tls/lakekeeper_tls.key"
  cert="tls/lakekeeper_tls.cert"

  create_tls $domain $key $cert
  kubectl create secret tls lakekeeper-catalog-tls \
  --cert="$cert" \
  --key="$key" \
  -n default
}

main
