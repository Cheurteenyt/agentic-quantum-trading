param(
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"
$connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue

if (-not $connections) {
    Write-Output "No local LLM server listening on port $Port"
    exit 0
}

$processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($processId in $processIds) {
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process -and $process.ProcessName -match "llama") {
        Stop-Process -Id $processId -Force
        Write-Output "Stopped $($process.ProcessName) PID $processId"
    } else {
        Write-Output "Skipped PID $processId because it does not look like llama-server"
    }
}
