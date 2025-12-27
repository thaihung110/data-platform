#!/bin/bash

set -eu

APP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "${APP_DIR}" || exit 1

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🚀 Installing Source API...${NC}"
echo ""

# Apply the manifest
echo -e "${YELLOW}📝 Applying Kubernetes manifests...${NC}"
kubectl apply -f application/source-api.yaml

echo ""
echo -e "${YELLOW}⏳ Waiting for deployment to be ready...${NC}"
kubectl wait --for=condition=available --timeout=300s deployment/fastapi-csv-uploader -n default || {
    echo -e "${RED}⚠️  Deployment is taking longer than expected${NC}"
    echo -e "${YELLOW}Checking current status...${NC}"
}

echo ""
echo -e "${YELLOW}📊 Deployment status:${NC}"
kubectl get deployment fastapi-csv-uploader -n default

echo ""
echo -e "${YELLOW}📦 Pods:${NC}"
kubectl get pods -n default -l app=fastapi-csv-uploader

echo ""
echo -e "${YELLOW}💾 PersistentVolumeClaim:${NC}"
kubectl get pvc csv-chunks-pvc -n default

echo ""
echo -e "${YELLOW}🌐 Service:${NC}"
kubectl get svc fastapi-csv-uploader -n default

echo ""
echo -e "${GREEN}✅ Source API installation complete!${NC}"
echo ""
echo -e "${YELLOW}📝 Useful commands:${NC}"
echo ""
echo "  View logs:"
echo "    kubectl logs -f deployment/fastapi-csv-uploader -n default"
echo ""
echo "  Check pod status:"
echo "    kubectl get pods -n default -l app=fastapi-csv-uploader"
echo ""
echo "  Describe deployment:"
echo "    kubectl describe deployment fastapi-csv-uploader -n default"
echo ""
echo "  Test health endpoint:"
echo "    kubectl exec -it deployment/fastapi-csv-uploader -n default -- curl http://localhost:8000/api/v1/health"
echo ""
echo "  Port-forward for local access:"
echo "    kubectl port-forward -n default svc/fastapi-csv-uploader 8000:8000"
echo ""
