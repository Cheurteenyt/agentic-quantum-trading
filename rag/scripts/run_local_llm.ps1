param(
    [string]$ServerExe = "",
    [string]$ModelPath = "D:\llama-server\models\qwen3.5\Qwen3.5-9B-Claude-4.6-HighIQ-INSTRUCT-HERETIC-UNCENSORED.Q4_K_M.gguf",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8080,
    [int]$ContextSize = 12288,
    [int]$GpuLayers = 30,
    [int]$Threads = 8,
    [int]$Parallel = 1,
    [switch]$UseIkLlama
)

$ErrorActionPreference = "Stop"

if (-not $ServerExe) {
    $ServerExe = "D:\ik_llama.cpp\build\bin\llama-server.exe"
    if (-not (Test-Path $ServerExe)) {
        $ServerExe = "D:\llama-server\llama-b8407-bin-win-cuda-12.4-x64\llama-server.exe"
    }
}

if ($UseIkLlama) {
    $ServerExe = "D:\ik_llama.cpp\build\bin\llama-server.exe"
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

$arguments = @(
    "-m", "`"$ModelPath`"",
    "--host", $HostAddress,
    "--port", "$Port",
    "-c", "$ContextSize",
    "-ngl", "$GpuLayers",
    "--threads", "$Threads",
    "--parallel", "$Parallel",
    "-fa", "on",
    "--reasoning", "off",
    "--reasoning-format", "none"
) -join " "

$startInfo = [System.Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = $ServerExe
$startInfo.Arguments = $arguments
$startInfo.WorkingDirectory = Split-Path $ServerExe -Parent
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$logDir = "D:\trading-agent\rag\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stdoutLog = Join-Path $logDir "local_llm.stdout.log"
$stderrLog = Join-Path $logDir "local_llm.stderr.log"
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true
$process = [System.Diagnostics.Process]::Start($startInfo)

if (-not $process) {
    throw "Failed to start local LLM server"
}

Write-Output "Starting local LLM server: http://$HostAddress`:$Port"
Write-Output "PID: $($process.Id)"
Write-Output "Executable: $ServerExe"
Write-Output "Model: $ModelPath"
Write-Output "RTX 3070 preset: ctx=$ContextSize ngl=$GpuLayers parallel=$Parallel"

Start-Job -ScriptBlock {
    param($ProcessId, $StdoutLog, $StderrLog)
    $process = [System.Diagnostics.Process]::GetProcessById($ProcessId)
    $process.StandardOutput.ReadToEnd() | Out-File -FilePath $StdoutLog -Encoding utf8
    $process.StandardError.ReadToEnd() | Out-File -FilePath $StderrLog -Encoding utf8
} -ArgumentList $process.Id, $stdoutLog, $stderrLog | Out-Null

Write-Output "Logs: $stdoutLog / $stderrLog"
