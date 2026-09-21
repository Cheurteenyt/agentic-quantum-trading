param(
    [string]$ProjectRoot = "D:\trading-agent",
    [int]$Port = 6333,
    [string]$ContainerName = "core-equity-qdrant"
)

$ErrorActionPreference = "Stop"
$storage = Join-Path $ProjectRoot "rag\indexes\qdrant_server"
New-Item -ItemType Directory -Force -Path $storage | Out-Null

docker info | Out-Null

$existing = docker ps -a --filter "name=$ContainerName" --format "{{.Names}}"
if ($existing -contains $ContainerName) {
    docker start $ContainerName | Out-Null
} else {
    docker run `
        --name $ContainerName `
        --restart unless-stopped `
        -e QDRANT__TELEMETRY_DISABLED=true `
        -p "127.0.0.1:${Port}:6333" `
        -v "${storage}:/qdrant/storage" `
        -d qdrant/qdrant | Out-Null
}

Write-Output "Qdrant server: http://127.0.0.1:$Port"
Write-Output "Storage: $storage"
