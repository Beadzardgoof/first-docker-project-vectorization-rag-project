#!/bin/bash

# Production Deployment Script for Flight Search System
set -e

echo "🚀 Deploying Flight Search System to Kubernetes..."

# Configuration
NAMESPACE="flight-search"
REGISTRY="your-registry.com"  # Update with your container registry
VERSION=${1:-latest}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    if ! command -v kubectl &> /dev/null; then
        error "kubectl is not installed"
        exit 1
    fi
    
    if ! command -v docker &> /dev/null; then
        error "docker is not installed"
        exit 1
    fi
    
    # Check if cluster is accessible
    if ! kubectl cluster-info &> /dev/null; then
        error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    success "Prerequisites check passed"
}

# Build and push images
build_and_push() {
    log "Building and pushing Docker images..."
    
    services=("vector-db" "rag-service" "llm-service" "console-frontend")
    
    for service in "${services[@]}"; do
        log "Building ${service}..."
        docker build -t "${REGISTRY}/flight-${service}:${VERSION}" "./services/${service}/"
        
        log "Pushing ${service}..."
        docker push "${REGISTRY}/flight-${service}:${VERSION}"
        
        success "Built and pushed ${service}"
    done
}

# Update image tags in manifests
update_manifests() {
    log "Updating image tags in manifests..."
    
    # Update image tags to use the specified version
    find k8s/ -name "*.yaml" -exec sed -i "s|image: flight-\([^:]*\):.*|image: ${REGISTRY}/flight-\1:${VERSION}|g" {} \;
    
    success "Updated manifests with version ${VERSION}"
}

# Deploy to Kubernetes
deploy_k8s() {
    log "Deploying to Kubernetes..."
    
    # Create namespace
    kubectl apply -f k8s/namespace.yaml
    
    # Apply ConfigMaps and Secrets
    kubectl apply -f k8s/configmap.yaml
    
    # Deploy data layer first
    log "Deploying Vector DB..."
    kubectl apply -f k8s/vector-db-deployment.yaml
    
    # Wait for Vector DB to be ready
    log "Waiting for Vector DB to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/vector-db -n ${NAMESPACE}
    
    # Deploy backend services
    log "Deploying RAG Service..."
    kubectl apply -f k8s/rag-service-deployment.yaml
    
    log "Waiting for RAG Service to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/rag-service -n ${NAMESPACE}
    
    # Deploy frontend services
    log "Deploying LLM Service..."
    kubectl apply -f k8s/llm-service-deployment.yaml
    
    log "Waiting for LLM Service to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/llm-service -n ${NAMESPACE}
    
    # Apply monitoring (optional)
    if kubectl get crd prometheusrules.monitoring.coreos.com &> /dev/null; then
        log "Deploying monitoring..."
        kubectl apply -f k8s/monitoring.yaml
    else
        warn "Prometheus operator not found, skipping monitoring setup"
    fi
    
    success "Kubernetes deployment completed"
}

# Verify deployment
verify_deployment() {
    log "Verifying deployment..."
    
    # Check pod status
    echo ""
    log "Pod Status:"
    kubectl get pods -n ${NAMESPACE}
    
    echo ""
    log "Service Status:"
    kubectl get services -n ${NAMESPACE}
    
    # Check if all pods are running
    if kubectl get pods -n ${NAMESPACE} | grep -v "Running\|Completed" | grep -q "flight"; then
        warn "Some pods are not in Running state"
        kubectl get pods -n ${NAMESPACE} | grep -v "Running\|Completed"
    else
        success "All pods are running successfully"
    fi
    
    # Get ingress information
    echo ""
    log "Ingress Status:"
    kubectl get ingress -n ${NAMESPACE}
    
    echo ""
    success "Deployment verification completed"
}

# Load test data
load_test_data() {
    log "Loading test flight data..."
    
    # Get a vector-db pod name
    VECTOR_POD=$(kubectl get pods -n ${NAMESPACE} -l app=vector-db -o jsonpath='{.items[0].metadata.name}')
    
    if [ ! -z "$VECTOR_POD" ]; then
        # Copy and run data loading script
        kubectl cp ./data/flights_dataset.json ${NAMESPACE}/${VECTOR_POD}:/tmp/
        kubectl exec -n ${NAMESPACE} ${VECTOR_POD} -- python -c "
import json
import requests

# Load flight data from file
with open('/tmp/flights_dataset.json', 'r') as f:
    flights = json.load(f)

# Post each flight to the vector DB
for i, flight in enumerate(flights[:1000]):  # Load first 1000 flights
    try:
        response = requests.post('http://localhost:8000/flights/add', json=flight)
        if i % 100 == 0:
            print(f'Loaded {i} flights...')
    except Exception as e:
        print(f'Error loading flight {i}: {e}')

print('Test data loading completed!')
"
        success "Test data loaded successfully"
    else
        warn "Could not find vector-db pod for data loading"
    fi
}

# Performance test
performance_test() {
    log "Running basic performance test..."
    
    # Get LLM service URL
    INGRESS_URL=$(kubectl get ingress llm-service-ingress -n ${NAMESPACE} -o jsonpath='{.spec.rules[0].host}')
    
    if [ ! -z "$INGRESS_URL" ]; then
        log "Testing endpoint: https://${INGRESS_URL}/health"
        
        # Simple health check
        if curl -s "https://${INGRESS_URL}/health" | grep -q "healthy"; then
            success "Health check passed"
        else
            warn "Health check failed"
        fi
        
        # Basic load test with curl
        log "Running basic load test..."
        for i in {1..10}; do
            response_time=$(curl -s -w "%{time_total}" -o /dev/null "https://${INGRESS_URL}/health")
            echo "Request $i: ${response_time}s"
        done
        
        success "Basic performance test completed"
    else
        warn "Could not determine ingress URL for testing"
    fi
}

# Main execution
main() {
    echo "Flight Search System - Production Deployment"
    echo "==========================================="
    
    check_prerequisites
    
    # Ask for confirmation
    read -p "Deploy version ${VERSION} to ${NAMESPACE} namespace? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Deployment cancelled"
        exit 0
    fi
    
    build_and_push
    update_manifests
    deploy_k8s
    verify_deployment
    
    # Optional steps
    read -p "Load test data? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        load_test_data
    fi
    
    read -p "Run performance test? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        performance_test
    fi
    
    echo ""
    success "🎉 Deployment completed successfully!"
    echo ""
    log "Next steps:"
    echo "  1. Configure DNS to point to your ingress"
    echo "  2. Set up monitoring dashboards"
    echo "  3. Configure backup for vector database"
    echo "  4. Set up CI/CD pipeline"
    echo ""
    log "Useful commands:"
    echo "  kubectl get pods -n ${NAMESPACE}"
    echo "  kubectl logs -f deployment/llm-service -n ${NAMESPACE}"
    echo "  kubectl port-forward service/llm-service 8080:8000 -n ${NAMESPACE}"
}

# Run main function
main "$@"