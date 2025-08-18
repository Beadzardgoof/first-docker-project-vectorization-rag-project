# Flight Search System - Management Script for PowerShell
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("deploy", "status", "logs", "scale", "cleanup", "test")]
    [string]$Action,
    
    [string]$Service = "all",
    [string]$Namespace = "flight-search",
    [int]$Replicas = 3
)

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

# Deploy basic configuration
function Deploy-Basic {
    Write-Log "Deploying basic configuration..."
    
    # Create namespace
    kubectl apply -f k8s\namespace.yaml
    
    # Apply configs
    kubectl apply -f k8s\configmap.yaml
    
    # Deploy services
    kubectl apply -f k8s\vector-db-deployment.yaml
    kubectl apply -f k8s\rag-service-deployment.yaml
    kubectl apply -f k8s\llm-service-deployment.yaml
    kubectl apply -f k8s\console-frontend-deployment.yaml
    
    Write-Success "Basic deployment completed"
}

# Check status
function Get-Status {
    Write-Log "Checking system status..."
    
    Write-Host "`n=== PODS ===" -ForegroundColor Cyan
    kubectl get pods -n $Namespace
    
    Write-Host "`n=== SERVICES ===" -ForegroundColor Cyan
    kubectl get services -n $Namespace
    
    Write-Host "`n=== HPA ===" -ForegroundColor Cyan
    kubectl get hpa -n $Namespace
    
    Write-Host "`n=== RESOURCE USAGE ===" -ForegroundColor Cyan
    kubectl top pods -n $Namespace
}

# Get logs
function Get-Logs {
    if ($Service -eq "all") {
        $services = @("vector-db", "rag-service", "llm-service", "console-frontend")
        foreach ($svc in $services) {
            Write-Host "`n=== $svc LOGS ===" -ForegroundColor Cyan
            kubectl logs deployment/$svc -n $Namespace --tail=20
        }
    }
    else {
        Write-Log "Getting logs for $Service..."
        kubectl logs deployment/$Service -n $Namespace --tail=50 -f
    }
}

# Scale service
function Set-Scale {
    if ($Service -eq "all") {
        Write-Warning "Please specify a specific service to scale"
        return
    }
    
    Write-Log "Scaling $Service to $Replicas replicas..."
    kubectl scale deployment/$Service --replicas=$Replicas -n $Namespace
    
    Write-Success "Scaled $Service to $Replicas replicas"
}

# Cleanup
function Remove-All {
    $confirmation = Read-Host "Are you sure you want to delete all resources in namespace $Namespace? (y/N)"
    if ($confirmation -match '^[Yy]$') {
        Write-Log "Cleaning up all resources..."
        kubectl delete namespace $Namespace
        Write-Success "Cleanup completed"
    }
    else {
        Write-Log "Cleanup cancelled"
    }
}

# Test connectivity
function Test-Connectivity {
    Write-Log "Testing service connectivity..."
    
    # Port-forward to LLM service
    Write-Log "Setting up port-forward to LLM service..."
    Start-Job -ScriptBlock {
        kubectl port-forward service/llm-service 8080:8000 -n $using:Namespace
    } | Out-Null
    
    Start-Sleep -Seconds 3
    
    try {
        # Test health endpoint
        $response = Invoke-RestMethod -Uri "http://localhost:8080/health" -Method Get
        Write-Success "Health check: $($response.status)"
        
        # Test chat endpoint
        $chatPayload = @{
            message = "Hello, test query"
        } | ConvertTo-Json
        
        $chatResponse = Invoke-RestMethod -Uri "http://localhost:8080/chat" -Method Post -Body $chatPayload -ContentType "application/json"
        Write-Success "Chat test: Response received"
        Write-Host "Intent detected: $($chatResponse.detected_intent)"
    }
    catch {
        Write-Warning "Connectivity test failed: $($_.Exception.Message)"
    }
    finally {
        # Clean up port-forward jobs
        Get-Job | Where-Object { $_.Name -like "*kubectl*" } | Stop-Job | Remove-Job
    }
}

# Main switch
switch ($Action) {
    "deploy" {
        Deploy-Basic
    }
    "status" {
        Get-Status
    }
    "logs" {
        Get-Logs
    }
    "scale" {
        Set-Scale
    }
    "cleanup" {
        Remove-All
    }
    "test" {
        Test-Connectivity
    }
    default {
        Write-Host "Usage: .\manage.ps1 -Action <deploy|status|logs|scale|cleanup|test> [-Service <service-name>] [-Replicas <number>]"
        Write-Host ""
        Write-Host "Examples:"
        Write-Host "  .\manage.ps1 -Action deploy"
        Write-Host "  .\manage.ps1 -Action status"
        Write-Host "  .\manage.ps1 -Action logs -Service llm-service"
        Write-Host "  .\manage.ps1 -Action scale -Service llm-service -Replicas 5"
        Write-Host "  .\manage.ps1 -Action test"
        Write-Host "  .\manage.ps1 -Action cleanup"
    }
}