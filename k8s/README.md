# Kubernetes deployment

## Prerequisites

- `kubectl` configured for your cluster (AWS EKS, GKE, AKS, or another CNCF-compliant cluster).
- A Secret `pantheon-secrets` with key `anthropic-api-key`.

## Apply

```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
```

## Cloud notes

- **AWS EKS**: use an Application Load Balancer or NLB via annotations on the Service; ensure security groups allow 80/443 to the load balancer.
- **GKE**: LoadBalancer type provisions a Google Cloud external passthrough NLB by default.
- **Azure AKS**: use `type: LoadBalancer` or an Ingress controller (NGINX / App Gateway).

Readiness uses `GET /ready` on port **8002** — align container `PORT` with your image CMD.
