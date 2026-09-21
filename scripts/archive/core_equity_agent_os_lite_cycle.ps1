param(
    [int]$EventReaderRunId = 1,
    [int]$MaxRpcCalls = 25,
    [switch]$RequireQdrant
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function New-Candidate {
    param(
        [string]$RuntimeId,
        [string]$Command,
        [string[]]$PrefixArgs = @()
    )
    [pscustomobject]@{
        runtime_id = $RuntimeId
        command = $Command
        prefix_args = $PrefixArgs
    }
}

function Format-Preview {
    param([object]$Value, [int]$MaxLength = 500)
    $text = (($Value | Out-String).Trim() -replace "`r?`n", " ")
    if ($text.Length -le $MaxLength) {
        return $text
    }
    return $text.Substring(0, $MaxLength)
}

$candidates = @()
$venvWin = Join-Path $ProjectRoot ".venv-win\Scripts\python.exe"
$venvFallback = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$venvRag = Join-Path $ProjectRoot ".venv-rag\Scripts\python.exe"

if (Test-Path $venvWin) {
    $candidates += New-Candidate -RuntimeId "windows_project_venv" -Command $venvWin
}
if (Test-Path $venvFallback) {
    $candidates += New-Candidate -RuntimeId "windows_project_fallback_venv" -Command $venvFallback
}
if (Test-Path $venvRag) {
    $candidates += New-Candidate -RuntimeId "windows_project_rag_venv" -Command $venvRag
}

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCmd) {
    $candidates += New-Candidate -RuntimeId "system_python" -Command $pythonCmd.Source
}

$pyCmd = Get-Command py -ErrorAction SilentlyContinue
if ($pyCmd) {
    $candidates += New-Candidate -RuntimeId "py_launcher" -Command $pyCmd.Source -PrefixArgs @("-3")
}

$pythonCode = @'
import json
import os
import sys
from pathlib import Path

project_root = Path.cwd()
sys.path.insert(0, str(project_root / "backend"))

from services.onchain_engine import (  # noqa: E402
    get_core_equity_agent_os_lite_cycle_preview,
    get_core_equity_agent_os_lite_runtime_preflight,
)

event_reader_run_id = int(os.environ.get("CORE_EQUITY_EVENT_READER_RUN_ID", "1"))
max_rpc_calls = int(os.environ.get("CORE_EQUITY_MAX_RPC_CALLS", "25"))
require_qdrant = os.environ.get("CORE_EQUITY_REQUIRE_QDRANT", "0") == "1"

preflight = get_core_equity_agent_os_lite_runtime_preflight(
    dry_run=True,
    event_reader_run_id=event_reader_run_id,
    require_qdrant=require_qdrant,
)
cycle = get_core_equity_agent_os_lite_cycle_preview(
    dry_run=True,
    event_reader_run_id=event_reader_run_id,
    max_rpc_calls=max_rpc_calls,
    require_qdrant=require_qdrant,
)

result = {
    "ok": True,
    "runner": "scripts/core_equity_agent_os_lite_cycle.ps1",
    "mode": "safe_read_only",
    "source_of_truth": "rag/memory",
    "legacy_memory_md_used": False,
    "preflight_status": preflight.get("preflight_status"),
    "selected_runtime": preflight.get("selected_runtime"),
    "runtime_blockers": preflight.get("blockers"),
    "degraded_conditions": preflight.get("degraded_conditions"),
    "cycle_preview_status": cycle.get("cycle_preview_status"),
    "selected_task": cycle.get("selected_task"),
    "cycle_blockers": cycle.get("blockers"),
    "next_safe_step": cycle.get("next_safe_step") or preflight.get("next_safe_step"),
    "would_call_rpc": cycle.get("would_call_rpc"),
    "would_call_external": cycle.get("would_call_external"),
    "would_write": cycle.get("would_write"),
    "writes_performed": cycle.get("writes_performed"),
    "would_create_mapping": cycle.get("would_create_mapping"),
    "would_create_client_signal": cycle.get("would_create_client_signal"),
    "would_execute_trade": cycle.get("would_execute_trade"),
    "would_create_client_opt_in": cycle.get("would_create_client_opt_in"),
}
print(json.dumps(result, ensure_ascii=False, indent=2))
'@

$failures = @()
$env:CORE_EQUITY_EVENT_READER_RUN_ID = [string]$EventReaderRunId
$env:CORE_EQUITY_MAX_RPC_CALLS = [string]$MaxRpcCalls
$env:CORE_EQUITY_REQUIRE_QDRANT = if ($RequireQdrant) { "1" } else { "0" }
$tempPythonScript = Join-Path ([System.IO.Path]::GetTempPath()) ("core_equity_agent_os_lite_cycle_" + [System.Guid]::NewGuid().ToString("N") + ".py")
Set-Content -LiteralPath $tempPythonScript -Value $pythonCode -Encoding UTF8

try {
    foreach ($candidate in $candidates) {
        try {
            $candidateArgs = @()
            $candidateArgs += $candidate.prefix_args
            $candidateArgs += @($tempPythonScript)
            $previousErrorActionPreference = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            $output = & $candidate.command @candidateArgs 2>&1
            $exitCode = $LASTEXITCODE
            $ErrorActionPreference = $previousErrorActionPreference
            if ($exitCode -eq 0) {
                $output
                exit 0
            }
            $failures += [pscustomobject]@{
                runtime_id = $candidate.runtime_id
                command = $candidate.command
                exit_code = $exitCode
                output_preview = Format-Preview -Value $output
            }
        } catch {
            $ErrorActionPreference = "Stop"
            $failures += [pscustomobject]@{
                runtime_id = $candidate.runtime_id
                command = $candidate.command
                exit_code = $null
                output_preview = $_.Exception.Message
            }
        }
    }
} finally {
    Remove-Item -LiteralPath $tempPythonScript -Force -ErrorAction SilentlyContinue
}

$blocked = [pscustomobject]@{
    ok = $false
    runner = "scripts/core_equity_agent_os_lite_cycle.ps1"
    mode = "safe_read_only"
    cycle_status = "blocked_actionable"
    blocker = "no_usable_python_runtime"
    project_root = $ProjectRoot
    source_of_truth = "rag/memory"
    legacy_memory_md_used = $false
    failures = $failures
    would_write = $false
    writes_performed = 0
}
$blocked | ConvertTo-Json -Depth 8
exit 1
