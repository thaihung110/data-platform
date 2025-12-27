#!/bin/bash

set -eu

APP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "${APP_DIR}" || exit 1

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🗑️  Uninstalling Source API...${NC}"
echo ""

# Delete the deployment, service, and configmap
echo -e "${YELLOW}📝 Deleting Kubernetes resources...${NC}"
kubectl delete -f application/source-api.yaml --ignore-not-found=true

echo ""
echo -e "${YELLOW}⏳ Waiting for resources to be deleted...${NC}"
sleep 5

echo ""
echo -e "${YELLOW}🔍 Checking if resources are deleted...${NC}"
kubectl get deployment fastapi-csv-uploader -n default 2>/dev/null && echo -e "${YELLOW}⚠️  Deployment still exists${NC}" || echo -e "${GREEN}✅ Deployment deleted${NC}"
kubectl get configmap source-api-config -n default 2>/dev/null && echo -e "${YELLOW}⚠️  ConfigMap still exists${NC}" || echo -e "${GREEN}✅ ConfigMap deleted${NC}"
kubectl get svc fastapi-csv-uploader -n default 2>/dev/null && echo -e "${YELLOW}⚠️  Service still exists${NC}" || echo -e "${GREEN}✅ Service deleted${NC}"

echo ""
echo -e "${YELLOW}💾 PersistentVolumeClaim status:${NC}"
if kubectl get pvc csv-chunks-pvc -n default 2>/dev/null; then
    echo ""
    read -p "Do you want to delete the PersistentVolumeClaim (csv-chunks-pvc)? This will delete all stored CSV chunks. (y/N): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Deleting PVC...${NC}"
        kubectl delete pvc csv-chunks-pvc -n default
        echo -e "${GREEN}✅ PVC deleted${NC}"
    else
        echo -e "${YELLOW}⚠️  PVC retained (can be reused on next installation)${NC}"
    fi
else
    echo -e "${GREEN}✅ PVC already deleted or doesn't exist${NC}"
fi

echo ""
echo -e "${GREEN}✅ Source API uninstalled successfully!${NC}"
