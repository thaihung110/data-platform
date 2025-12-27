#!/bin/bash

# Port-forward script for OpenFGA Playground
# This allows accessing playground via localhost, which matches the CSP frame-ancestors policy

set -eu

echo "Port-forwarding OpenFGA Playground to localhost:3000"
echo "Access playground at: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop port-forwarding"

kubectl port-forward svc/openhouse-openfga 3000:3000 -n default

