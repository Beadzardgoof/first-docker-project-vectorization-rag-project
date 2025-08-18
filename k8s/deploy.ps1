# Production Deployment Script for Flight Search System - PowerShell Version
param(
    [string]$Version = "latest",
    [string]$Registry = "your-registry.com",
    [string]$Namespace = "flight-search"
)

# Set error handling
$ErrorActionPreference = "Stop"

Write-Host "🚀 Deploying Flight Search System to Kubernetes..." -ForegroundColor Blue

# Function definitions
function Write-Log {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

# Check prerequisites
function Test-Prerequisites {
    Write-Log "Checking prerequisites..."
    
    # Check kubectl
    try {
        kubectl version --client | Out-Null
    }
    catch {
        Write-Error "kubectl is not installed or not in PATH"
        exit 1
    }
    
    # Check docker
    try {
        docker version | Out-Null
    }
    catch {
        Write-Error "docker is not installed or not running"
        exit 1
    }
    
    # Check cluster connectivity
    try {
        kubectl cluster-info | Out-Null
    }
    catch {
        Write-Error "Cannot connect to Kubernetes cluster"
        exit 1
    }
    
    Write-Success "Prerequisites check passed"
}

# Build and push images
function Build-AndPushImages {
    Write-Log "Building and pushing Docker images..."
    
    $services = @("vector-db", "rag-service", "llm-service", "console-frontend")
    
    foreach ($service in $services) {
        Write-Log "Building $service..."
        
        $imageName = "$Registry/flight-$service`:$Version"
        docker build -t $imageName ".\services\$service\"
        
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to build $service"
            exit 1
        }
        
        Write-Log "Pushing $service..."
        docker push $imageName
        
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to push $service"
            exit 1
        }
        
        Write-Success "Built and pushed $service"
    }
}

# Update image tags in manifests
function Update-Manifests {
    Write-Log "Updating image tags in manifests..."
    
    # Get all YAML files in k8s directory
    $yamlFiles = Get-ChildItem -Path "k8s\" -Filter "*.yaml"
    
    foreach ($file in $yamlFiles) {
        $content = Get-Content $file.FullName -Raw
        
        # Replace image tags using regex
        $content = $content -replace 'image: flight-([^:]*):.*', "image: $Registry/flight-`$1:$Version"
        
        Set-Content -Path $file.FullName -Value $content
    }
    
    Write-Success "Updated manifests with version $Version"
}

# Deploy to Kubernetes
function Deploy-ToKubernetes {
    Write-Log "Deploying to Kubernetes..."
    
    # Create namespace
    kubectl apply -f k8s\namespace.yaml
    if ($LASTEXITCODE -ne 0) { throw "Failed to create namespace" }
    
    # Apply ConfigMaps and Secrets
    kubectl apply -f k8s\configmap.yaml
    if ($LASTEXITCODE -ne 0) { throw "Failed to apply configmap" }
    
    # Deploy data layer first
    Write-Log "Deploying Vector DB..."
    kubectl apply -f k8s\vector-db-deployment.yaml
    if ($LASTEXITCODE -ne 0) { throw "Failed to deploy Vector DB" }
    
    # Wait for Vector DB to be ready
    Write-Log "Waiting for Vector DB to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/vector-db -n $Namespace
    if ($LASTEXITCODE -ne 0) { throw "Vector DB failed to become ready" }
    
    # Deploy backend services
    Write-Log "Deploying RAG Service..."
    kubectl apply -f k8s\rag-service-deployment.yaml
    if ($LASTEXITCODE -ne 0) { throw "Failed to deploy RAG Service" }
    
    Write-Log "Waiting for RAG Service to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/rag-service -n $Namespace
    if ($LASTEXITCODE -ne 0) { throw "RAG Service failed to become ready" }
    
    # Deploy frontend services
    Write-Log "Deploying LLM Service..."
    kubectl apply -f k8s\llm-service-deployment.yaml
    if ($LASTEXITCODE -ne 0) { throw "Failed to deploy LLM Service" }
    
    Write-Log "Waiting for LLM Service to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/llm-service -n $Namespace
    if ($LASTEXITCODE -ne 0) { throw "LLM Service failed to become ready" }
    
    # Deploy console frontend
    Write-Log "Deploying Console Frontend..."
    kubectl apply -f k8s\console-frontend-deployment.yaml
    if ($LASTEXITCODE -ne 0) { throw "Failed to deploy Console Frontend" }
    
    Write-Log "Waiting for Console Frontend to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/console-frontend -n $Namespace
    if ($LASTEXITCODE -ne 0) { throw "Console Frontend failed to become ready" }
    
    # Apply monitoring (optional)
    $crdCheck = kubectl get crd prometheusrules.monitoring.coreos.com 2>$null
    if ($crdCheck) {
        Write-Log "Deploying monitoring..."
        kubectl apply -f k8s\monitoring.yaml
    }
    else {
        Write-Warning "Prometheus operator not found, skipping monitoring setup"
    }
    
    Write-Success "Kubernetes deployment completed"
}

# Verify deployment
function Test-Deployment {
    Write-Log "Verifying deployment..."
    
    Write-Host ""
    Write-Log "Pod Status:"
    kubectl get pods -n $Namespace
    
    Write-Host ""
    Write-Log "Service Status:"
    kubectl get services -n $Namespace
    
    # Check if all pods are running
    $podStatus = kubectl get pods -n $Namespace --no-headers
    $failedPods = $podStatus | Where-Object { $_ -notmatch "Running|Completed" -and $_ -match "flight" }
    
    if ($failedPods) {
        Write-Warning "Some pods are not in Running state:"
        $failedPods | ForEach-Object { Write-Host $_ }
    }
    else {
        Write-Success "All pods are running successfully"
    }
    
    # Get ingress information
    Write-Host ""
    Write-Log "Ingress Status:"
    kubectl get ingress -n $Namespace
    
    Write-Host ""
    Write-Success "Deployment verification completed"
}

# Load test data
function Import-TestData {
    Write-Log "Loading test flight data..."
    
    # Get a vector-db pod name
    $vectorPod = kubectl get pods -n $Namespace -l app=vector-db -o jsonpath='{.items[0].metadata.name}' 2>$null
    
    if ($vectorPod) {
        # Copy and run data loading script
        kubectl cp ".\data\flights_dataset.json" "$Namespace/$vectorPod`:/tmp/"
        
        $pythonScript = @"
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
"@
        
        $scriptFile = [System.IO.Path]::GetTempFileName() + ".py"
        Set-Content -Path $scriptFile -Value $pythonScript
        
        kubectl cp $scriptFile "$Namespace/$vectorPod`:/tmp/load_data.py"
        kubectl exec -n $Namespace $vectorPod -- python /tmp/load_data.py
        
        Remove-Item $scriptFile
        Write-Success "Test data loaded successfully"
    }
    else {
        Write-Warning "Could not find vector-db pod for data loading"
    }
}

# Performance test
function Test-Performance {
    Write-Log "Running basic performance test..."
    
    # Get LLM service URL
    $ingressUrl = kubectl get ingress llm-service-ingress -n $Namespace -o jsonpath='{.spec.rules[0].host}' 2>$null
    
    if ($ingressUrl) {
        Write-Log "Testing endpoint: https://$ingressUrl/health"
        
        # Simple health check
        try {
            $response = Invoke-RestMethod -Uri "https://$ingressUrl/health" -Method Get
            if ($response.status -eq "healthy") {
                Write-Success "Health check passed"
            }
            else {
                Write-Warning "Health check failed"
            }
        }
        catch {
            Write-Warning "Health check failed: $($_.Exception.Message)"
        }
        
        # Basic load test
        Write-Log "Running basic load test..."
        $responseTimes = @()
        
        for ($i = 1; $i -le 10; $i++) {
            $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
            try {
                Invoke-RestMethod -Uri "https://$ingressUrl/health" -Method Get | Out-Null
                $stopwatch.Stop()
                $responseTime = $stopwatch.ElapsedMilliseconds
                $responseTimes += $responseTime
                Write-Host "Request $i`: $($responseTime)ms"
            }
            catch {
                Write-Warning "Request $i failed"
            }
        }
        
        if ($responseTimes.Count -gt 0) {
            $avgTime = ($responseTimes | Measure-Object -Average).Average
            Write-Log "Average response time: $([math]::Round($avgTime, 2))ms"
        }
        
        Write-Success "Basic performance test completed"
    }
    else {
        Write-Warning "Could not determine ingress URL for testing"
    }
}

# Main execution
function Main {
    Write-Host "Flight Search System - Production Deployment" -ForegroundColor Cyan
    Write-Host "===========================================" -ForegroundColor Cyan
    
    try {
        Test-Prerequisites
        
        # Ask for confirmation
        $confirmation = Read-Host "Deploy version $Version to $Namespace namespace? (y/N)"
        if ($confirmation -notmatch '^[Yy]$') {
            Write-Log "Deployment cancelled"
            exit 0
        }
        
        Build-AndPushImages
        Update-Manifests
        Deploy-ToKubernetes
        Test-Deployment
        
        # Optional steps
        $loadData = Read-Host "Load test data? (y/N)"
        if ($loadData -match '^[Yy]$') {
            Import-TestData
        }
        
        $perfTest = Read-Host "Run performance test? (y/N)"
        if ($perfTest -match '^[Yy]$') {
            Test-Performance
        }
        
        Write-Host ""
        Write-Success "🎉 Deployment completed successfully!"
        Write-Host ""
        Write-Log "Access your application:"
        Write-Host "  Console Frontend: https://console.flightsearch.com"
        Write-Host "  API Endpoint: https://api.flightsearch.com"
        Write-Host ""
        Write-Log "For local development access:"
        Write-Host "  kubectl port-forward service/console-frontend-service 3000:8000 -n $Namespace"
        Write-Host "  kubectl port-forward service/llm-service 8080:8000 -n $Namespace"
        Write-Host "  Then visit: http://localhost:3000"
        Write-Host ""
        Write-Log "Next steps:"
        Write-Host "  1. Configure DNS to point console.flightsearch.com and api.flightsearch.com to your ingress"
        Write-Host "  2. Set up monitoring dashboards"
        Write-Host "  3. Configure backup for vector database"
        Write-Host "  4. Set up CI/CD pipeline"
        Write-Host ""
        Write-Log "Useful commands:"
        Write-Host "  kubectl get pods -n $Namespace"
        Write-Host "  kubectl logs -f deployment/console-frontend -n $Namespace"
        Write-Host "  kubectl get ingress -n $Namespace"
    }
    catch {
        Write-Error "Deployment failed: $($_.Exception.Message)"
        exit 1
    }
}

# Run main function
Main