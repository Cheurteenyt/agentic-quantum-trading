param(
    [string]$ServerExe = "D:\llama-server\llama-b8407-bin-win-cuda-12.4-x64\llama-server.exe",
    [string]$ModelPath = "D:\llama-server\models\qwen3.5\Qwen3.5-9B-Claude-4.6-HighIQ-INSTRUCT-HERETIC-UNCENSORED.Q4_K_M.gguf",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8080,
    [int]$ContextSize = 16384,
    [int]$GpuLayers = 34,
    [int]$Threads = 8,
    [int]$Parallel = 1,
    [switch]$Visible,
    [switch]$UseIkLlama
)

$ErrorActionPreference = "Stop"

if ($UseIkLlama) {
    $ServerExe = "D:\ik_llama.cpp\llama-server.exe"
}

if (-not (Test-Path $ServerExe)) {
    throw "LLM server executable not found: $ServerExe"
}

if (-not (Test-Path $ModelPath)) {
    throw "Model file not found: $ModelPath"
}

$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Output "LLM server already listening on http://$HostAddress`:$Port"
    exit 0
}

$args = @(
    "-m", "`"$ModelPath`"",
    "--host", $HostAddress,
    "--port", "$Port",
    "-c", "$ContextSize",
    "-ngl", "$GpuLayers",
    "--threads", "$Threads",
    "--parallel", "$Parallel",
    "-fa"
)

$windowStyle = if ($Visible) { "Normal" } else { "Hidden" }
$processArgs = @{
    FilePath = $ServerExe
    ArgumentList = ($args -join " ")
    WorkingDirectory = (Split-Path $ServerExe -Parent)
}

try {
    Start-Process @processArgs -WindowStyle $windowStyle
} catch {
    if ($Visible) {
        throw
    }

    Write-Output "Hidden launch failed, retrying with .NET ProcessStartInfo: $($_.Exception.Message)"
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $ServerExe
    $startInfo.Arguments = ($args -join " ")
    $startInfo.WorkingDirectory = Split-Path $ServerExe -Parent
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $process = [System.Diagnostics.Process]::Start($startInfo)
    if (-not $process) {
        throw "Failed to start local LLM server with .NET ProcessStartInfo"
    }
    Write-Output "Started PID $($process.Id)"
}

Write-Output "Starting local LLM server: http://$HostAddress`:$Port"
Write-Output "Executable: $ServerExe"
Write-Output "Model: $ModelPath"
Write-Output "RTX 3070 preset: ctx=$ContextSize ngl=$GpuLayers parallel=$Parallel"
