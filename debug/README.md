# Debug Tools

Folder này chứa các công cụ và manifest files để debug các services trong data platform.

## Files

### `kafka-test-client.yaml`

Pod để test Kafka connectivity và consume/produce messages.

**Quick start:**

```bash
# Deploy test pod
kubectl apply -f debug/kafka-test-client.yaml

# Exec vào pod
kubectl exec -it kafka-test-client -- bash

# Xem hướng dẫn chi tiết
cat docs/kafka-testing.md
```

## Cleanup

```bash
# Xóa tất cả debug resources
kubectl delete -f debug/
```
