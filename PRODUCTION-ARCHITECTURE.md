# Flight Search System - Production Architecture

## Overview

This document outlines the production deployment architecture for the Flight Search System, a microservices-based application featuring vector search, LLM-powered intent detection, and numerical filtering capabilities.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    PRODUCTION ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐     │
│  │   Internet  │───▶│    CDN/WAF   │───▶│  Load Balancer  │     │
│  └─────────────┘    └──────────────┘    └─────────────────┘     │
│                                                   │             │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                 KUBERNETES CLUSTER                         │ │
│  │                                                             │ │
│  │  ┌────────────────┐                                        │ │
│  │  │  INGRESS NGINX │                                        │ │
│  │  │   (SSL/TLS)    │                                        │ │
│  │  └────────┬───────┘                                        │ │
│  │           │                                                │ │
│  │  ┌────────▼──────────────────────────────────────────────┐ │ │
│  │  │                FRONTEND TIER                         │ │ │
│  │  │                                                      │ │ │
│  │  │  ┌─────────────────┐     ┌─────────────────┐         │ │ │
│  │  │  │  LLM Service    │────▶│  Console Front  │         │ │ │
│  │  │  │  (4-20 pods)    │     │  (2-5 pods)     │         │ │ │
│  │  │  │  - Intent Det.  │     │  - UI Interface │         │ │ │
│  │  │  │  - OpenAI API   │     │  - WebSocket    │         │ │ │
│  │  │  │  - Chat Logic   │     │  - Static Files │         │ │ │
│  │  │  └─────────────────┘     └─────────────────┘         │ │ │
│  │  └──────────────────┬───────────────────────────────────┘ │ │
│  │                     │                                     │ │
│  │  ┌──────────────────▼───────────────────────────────────┐ │ │
│  │  │                BACKEND TIER                         │ │ │
│  │  │                                                     │ │ │
│  │  │  ┌─────────────────┐     ┌─────────────────┐        │ │ │
│  │  │  │  RAG Service    │────▶│  Vector Search  │        │ │ │
│  │  │  │  (3-10 pods)    │     │  Orchestrator   │        │ │ │
│  │  │  │  - Flight Filter│     │                 │        │ │ │
│  │  │  │  - Numerical    │     │                 │        │ │ │
│  │  │  │  - Post Process │     │                 │        │ │ │
│  │  │  └─────────────────┘     └─────────────────┘        │ │ │
│  │  └──────────────────┬───────────────────────────────────┘ │ │
│  │                     │                                     │ │
│  │  ┌──────────────────▼───────────────────────────────────┐ │ │
│  │  │                  DATA TIER                          │ │ │
│  │  │                                                     │ │ │
│  │  │  ┌─────────────────┐     ┌─────────────────┐        │ │ │
│  │  │  │  Vector DB      │────▶│  Persistent     │        │ │ │
│  │  │  │  (ChromaDB)     │     │  Storage        │        │ │ │
│  │  │  │  (2-3 pods)     │     │  (SSD/NVMe)     │        │ │ │
│  │  │  │  - Embeddings   │     │  - 50GB+ PVC    │        │ │ │
│  │  │  │  - Vector Ops   │     │  - Backup       │        │ │ │
│  │  │  │  - HNSW Index   │     │  - Replication  │        │ │ │
│  │  │  └─────────────────┘     └─────────────────┘        │ │ │
│  │  └─────────────────────────────────────────────────────┘ │ │
│  │                                                           │ │
│  │  ┌─────────────────────────────────────────────────────┐ │ │
│  │  │              OBSERVABILITY STACK                   │ │ │
│  │  │                                                     │ │ │
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐│ │ │
│  │  │  │Prometheus│ │ Grafana  │ │ELK Stack │ │ Jaeger  ││ │ │
│  │  │  │(Metrics) │ │(Dashbrd) │ │ (Logs)   │ │(Tracing)││ │ │
│  │  │  └──────────┘ └──────────┘ └──────────┘ └─────────┘│ │ │
│  │  └─────────────────────────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Deployment Strategy

### 1. **Infrastructure Requirements**

#### Kubernetes Cluster Specifications
- **Node Types**: 3 node types for optimal resource allocation
  - **Frontend Nodes**: 4-8 cores, 16-32GB RAM (for LLM service)
  - **Backend Nodes**: 4-8 cores, 8-16GB RAM (for RAG processing)
  - **Data Nodes**: 8-16 cores, 32-64GB RAM, NVMe SSD (for vector operations)

#### Storage Requirements
- **Vector Database**: 50GB+ SSD/NVMe storage with backup
- **Application Logs**: 10GB+ for centralized logging
- **Metrics Storage**: 5GB+ for Prometheus time series

### 2. **Scaling Strategy**

#### Horizontal Pod Autoscaling (HPA)
```yaml
LLM Service:     4-20 pods  (CPU: 60%, Memory: 75%)
RAG Service:     3-10 pods  (CPU: 70%, Memory: 80%)
Vector DB:       2-3 pods   (Manual scaling)
Console:         2-5 pods   (CPU: 70%, Memory: 70%)
```

#### Vertical Scaling
- **Memory**: Scale based on dataset size and concurrent users
- **CPU**: Scale based on vector operations and LLM inference load
- **Storage**: Scale based on flight data volume and embedding storage

### 3. **Traffic Management**

#### Load Balancing
- **External**: NGINX Ingress Controller with SSL termination
- **Internal**: Kubernetes Service mesh for inter-service communication
- **Rate Limiting**: 100 requests/minute per IP to prevent abuse

#### Caching Strategy
- **Vector Results**: Cache frequent searches at RAG service level
- **Intent Classifications**: Cache common query patterns
- **Static Content**: CDN for frontend assets

### 4. **Data Management**

#### Vector Database Scaling
```bash
# For large datasets (1M+ flights)
- Partitioning: Shard by geographic region or airline
- Replication: 2-3 replicas for high availability
- Backup: Daily snapshots to object storage
- Indexing: Optimize HNSW parameters for dataset size
```

#### Data Pipeline
```
Flight Data Sources → ETL Pipeline → Vector Embedding → ChromaDB
                                        ↓
                               Batch Processing (nightly)
                                        ↓
                               Index Optimization
```

### 5. **Monitoring & Observability**

#### Metrics Dashboard
- **Business Metrics**: Search success rate, intent accuracy, response time
- **System Metrics**: CPU, memory, disk I/O, network latency
- **Application Metrics**: Vector search performance, LLM inference time

#### Alerting Rules
```yaml
Critical Alerts:
- Vector DB down (>2 minutes)
- Error rate >5% (>5 minutes)
- Response time >3s (95th percentile)

Warning Alerts:
- High memory usage >85%
- High CPU usage >80%
- Disk space <20%
```

## Deployment Process

### 1. **Pre-Deployment**

```bash
# Set up cluster and prerequisites
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml

# Install monitoring stack
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install monitoring prometheus-community/kube-prometheus-stack
```

### 2. **Application Deployment**

```bash
# Clone and deploy
git clone <repository>
cd flight-search-system

# Configure secrets
kubectl create secret generic flight-search-secrets \
  --from-literal=OPENAI_API_KEY=your-api-key \
  -n flight-search

# Deploy application
chmod +x k8s/deploy.sh
./k8s/deploy.sh v1.0.0
```

### 3. **Data Loading**

```bash
# Load initial dataset
kubectl apply -f k8s/data-loader-job.yaml

# Verify data loading
kubectl logs job/data-loader -n flight-search
```

### 4. **Production Verification**

```bash
# Health checks
kubectl get pods -n flight-search
kubectl get services -n flight-search

# Performance testing
kubectl apply -f k8s/load-test-job.yaml
```

## Security Considerations

### 1. **Network Security**
- **Network Policies**: Restrict inter-pod communication
- **TLS Encryption**: All external and internal communication
- **API Rate Limiting**: Prevent DDoS and abuse

### 2. **Secrets Management**
- **Kubernetes Secrets**: Store OpenAI API keys and sensitive config
- **RBAC**: Role-based access control for service accounts
- **Pod Security Standards**: Enforce security contexts

### 3. **Data Protection**
- **Encryption at Rest**: Encrypt persistent volumes
- **Encryption in Transit**: TLS for all communication
- **Data Retention**: Implement data lifecycle policies

## Performance Optimization

### 1. **Vector Search Optimization**
```python
# Optimize ChromaDB settings for production
collection_config = {
    "hnsw:space": "cosine",
    "hnsw:M": 32,                    # Higher for better recall
    "hnsw:ef_construction": 400,     # Higher for better index quality
    "hnsw:ef": 200,                  # Higher for better search quality
    "hnsw:max_elements": 10000000    # Scale for dataset size
}
```

### 2. **LLM Service Optimization**
- **Batch Processing**: Batch multiple intent detection requests
- **Model Caching**: Cache embeddings for common queries
- **Connection Pooling**: Optimize HTTP connections to OpenAI

### 3. **Resource Optimization**
- **CPU Requests/Limits**: Right-size based on actual usage
- **Memory Management**: Optimize Python memory usage
- **Disk I/O**: Use SSD storage for vector operations

## Disaster Recovery

### 1. **Backup Strategy**
```bash
# Daily vector database backup
kubectl create cronjob vector-db-backup \
  --image=backup-tool \
  --schedule="0 2 * * *" \
  --restart=OnFailure

# Configuration backup
kubectl get all -n flight-search -o yaml > backup/deployment-backup.yaml
```

### 2. **High Availability**
- **Multi-Zone Deployment**: Spread pods across availability zones
- **Database Replication**: Multiple vector database replicas
- **Failover Procedures**: Automated failover for critical services

### 3. **Recovery Procedures**
```bash
# Restore from backup
kubectl apply -f backup/deployment-backup.yaml

# Restore vector database
kubectl exec vector-db-0 -- restore-from-backup /backup/latest.tar.gz
```

## Cost Optimization

### 1. **Resource Efficiency**
- **Right-Sizing**: Monitor and adjust resource requests/limits
- **Spot Instances**: Use spot instances for development/testing
- **Auto-Scaling**: Scale down during low traffic periods

### 2. **OpenAI API Optimization**
- **Caching**: Cache intent detection results
- **Rate Limiting**: Prevent unnecessary API calls
- **Model Selection**: Use appropriate model for each use case

### 3. **Storage Optimization**
- **Data Compression**: Compress vector embeddings
- **Retention Policies**: Implement data lifecycle management
- **Storage Classes**: Use appropriate storage classes for different data types

## Maintenance & Updates

### 1. **Rolling Updates**
```bash
# Zero-downtime deployment
kubectl set image deployment/llm-service \
  llm-service=registry/flight-llm-service:v1.1.0 \
  -n flight-search

# Monitor rollout
kubectl rollout status deployment/llm-service -n flight-search
```

### 2. **Health Monitoring**
- **Continuous Health Checks**: Monitor service health
- **Performance Monitoring**: Track key performance metrics
- **Automated Alerting**: Alert on performance degradation

### 3. **Capacity Planning**
- **Usage Analytics**: Monitor growth trends
- **Performance Testing**: Regular load testing
- **Resource Planning**: Plan for traffic growth

## Getting Started

1. **Prerequisites**: Kubernetes cluster, Docker registry, monitoring stack
2. **Configuration**: Update secrets and configuration maps
3. **Deployment**: Run the deployment script
4. **Verification**: Verify all services are healthy
5. **Data Loading**: Load initial flight dataset
6. **Testing**: Run performance and functional tests
7. **Monitoring**: Set up dashboards and alerts

This architecture provides a robust, scalable foundation for the Flight Search System that can handle production workloads while maintaining high availability and performance.