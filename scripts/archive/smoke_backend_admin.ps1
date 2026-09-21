param(
    [int]$Port = 8000,
    [int]$HealthTimeoutSec = 60,
    [int]$EvidenceId = 1,
    [string]$TargetConfidence = "high"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BackendDir = Join-Path $RepoRoot "backend"
$EnvPath = Join-Path $BackendDir ".env"
$WslRepo = "/mnt/d/trading-agent"
$WslBackend = "$WslRepo/backend"
$WslVenvActivate = "$WslRepo/.venv.wsl/bin/activate"
$HealthUrl = "http://localhost:$Port/health"
$SqlPlanUrl = "http://localhost:$Port/api/onchain/rpc/cex-label-confidence-upgrade-sql-plan?evidence_id=$EvidenceId&target_confidence=$TargetConfidence&dry_run=true"
$LogDir = Join-Path $env:TEMP "core-equity-smoke"
$StdoutLog = Join-Path $LogDir "backend-smoke-stdout.log"
$StderrLog = Join-Path $LogDir "backend-smoke-stderr.log"
$WslLog = "/tmp/core-equity-smoke-backend.log"

function Invoke-WslText {
    param([Parameter(Mandatory = $true)][string]$Command)
    $output = & wsl.exe -e bash -lc $Command
    if ($LASTEXITCODE -ne 0) {
        throw "WSL command failed with exit code $LASTEXITCODE"
    }
    return ($output -join "`n").Trim()
}

function Get-UvicornPids {
    $cmd = "ps -eo pid,args | awk '/[p]ython3 -m uvicorn main:app/ {print `$1}'"
    $text = Invoke-WslText $cmd
    if ([string]::IsNullOrWhiteSpace($text)) {
        return @()
    }
    return @($text -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Read-CoreAdminToken {
    if (-not (Test-Path $EnvPath)) {
        throw "backend/.env not found"
    }
    $line = Get-Content $EnvPath | Where-Object { $_ -match "^CORE_ADMIN_TOKEN=" } | Select-Object -First 1
    if (-not $line) {
        throw "CORE_ADMIN_TOKEN missing in backend/.env"
    }
    $token = $line -replace "^CORE_ADMIN_TOKEN=", ""
    if ([string]::IsNullOrWhiteSpace($token)) {
        throw "CORE_ADMIN_TOKEN is empty"
    }
    return $token
}

function Assert-NoExistingBackend {
    $existingPids = Get-UvicornPids
    if ($existingPids.Count -gt 0) {
        throw "Refusing to start: uvicorn already running in WSL (pid(s): $($existingPids -join ', ')). Stop it manually before smoke."
    }
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" })
    if ($listeners.Count -gt 0) {
        $owners = ($listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
        throw "Refusing to start: port $Port already has listener process(es): $owners"
    }
}

function Wait-Health {
    param([Parameter(Mandatory = $true)][Diagnostics.Process]$Process)
    $deadline = (Get-Date).AddSeconds($HealthTimeoutSec)
    do {
        if ($Process.HasExited) {
            $stdout = (Get-Content $StdoutLog -ErrorAction SilentlyContinue | Select-Object -Last 40) -join "`n"
            $stderr = (Get-Content $StderrLog -ErrorAction SilentlyContinue | Select-Object -Last 40) -join "`n"
            throw "Backend exited before health became ready. stdout:`n$stdout`nstderr:`n$stderr"
        }
        try {
            $health = Invoke-RestMethod -Method Get -Uri $HealthUrl -TimeoutSec 3
            if ($health.status -eq "ok") {
                return $health
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)
    $stdout = (Get-Content $StdoutLog -ErrorAction SilentlyContinue | Select-Object -Last 40) -join "`n"
    $stderr = (Get-Content $StderrLog -ErrorAction SilentlyContinue | Select-Object -Last 40) -join "`n"
    throw "Backend health timeout after $HealthTimeoutSec seconds. stdout:`n$stdout`nstderr:`n$stderr"
}

function Assert-SqlPlan {
    param([string]$Token)
    $headers = @{ "x-core-admin-token" = $Token }
    $result = Invoke-RestMethod -Method Post -Uri $SqlPlanUrl -Headers $headers -TimeoutSec 15
    if ($result.plan_status -ne "ready_but_disabled") { throw "Unexpected plan_status: $($result.plan_status)" }
    if ($result.planned_confidence -ne "high") { throw "Unexpected planned_confidence: $($result.planned_confidence)" }
    if ($result.rollback_confidence -ne "medium") { throw "Unexpected rollback_confidence: $($result.rollback_confidence)" }
    if ($result.write_enabled_now -ne $false) { throw "write_enabled_now must be false" }
    if ($result.mutation_allowed_now -ne $false) { throw "mutation_allowed_now must be false" }
    if ($result.real_write_enabled -ne $false) { throw "real_write_enabled must be false" }
    if ([int]$result.writes_performed -ne 0) { throw "writes_performed must be 0" }
    return $result
}

function Assert-DbUnchanged {
    $script = @'
import json
import sqlite3
from services import onchain_engine as e

conn = sqlite3.connect(str(e.DB_PATH))
try:
    evidence_rows = conn.execute("SELECT COUNT(*) FROM cex_independent_evidence_queue").fetchone()[0]
    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
finally:
    conn.close()

ledger = sqlite3.connect(str(e.LABEL_LEDGER_PATH))
try:
    candidate = ledger.execute("SELECT confidence, status FROM label_candidates WHERE id=1370").fetchone()
finally:
    ledger.close()

print(json.dumps({
    "evidence_rows": evidence_rows,
    "wallet_chain_state_rows": wallet_rows,
    "candidate_1370": list(candidate) if candidate else None,
}))
'@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($script))
    $cmd = "cd $WslRepo && source .venv.wsl/bin/activate && PYTHONPATH=backend python3 - <<'PY'`nimport base64; exec(base64.b64decode('$encoded').decode())`nPY"
    $json = Invoke-WslText $cmd
    $state = $json | ConvertFrom-Json
    if ([int]$state.evidence_rows -ne 1) { throw "Unexpected evidence row count: $($state.evidence_rows)" }
    if ([int]$state.wallet_chain_state_rows -ne 354) { throw "Unexpected wallet_chain_state row count: $($state.wallet_chain_state_rows)" }
    if (-not $state.candidate_1370 -or $state.candidate_1370[0] -ne "medium" -or $state.candidate_1370[1] -ne "candidate") {
        throw "Candidate 1370 mutated unexpectedly"
    }
    return $state
}

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
Remove-Item -LiteralPath $StdoutLog, $StderrLog -ErrorAction SilentlyContinue

$backendProcess = $null
$startedPids = @()
try {
    Assert-NoExistingBackend
    $token = Read-CoreAdminToken

    $backendCommand = "cd $WslBackend && source $WslVenvActivate && exec python3 -m uvicorn main:app --host 0.0.0.0 --port $Port"
    $backendArgs = "-e bash -lc `"$backendCommand`""
    $backendProcess = Start-Process -FilePath "wsl.exe" `
        -ArgumentList $backendArgs `
        -WindowStyle Hidden `
        -RedirectStandardOutput $StdoutLog `
        -RedirectStandardError $StderrLog `
        -PassThru

    $health = Wait-Health -Process $backendProcess
    $startedPids = Get-UvicornPids
    $plan = Assert-SqlPlan -Token $token
    $db = Assert-DbUnchanged

    [pscustomobject]@{
        ok = $true
        health = $health.status
        sql_plan = @{
            plan_status = $plan.plan_status
            planned_confidence = $plan.planned_confidence
            rollback_confidence = $plan.rollback_confidence
            write_enabled_now = $plan.write_enabled_now
            writes_performed = $plan.writes_performed
        }
        db = $db
        backend_pids = $startedPids
        logs = @{
            stdout = $StdoutLog
            stderr = $StderrLog
        }
    } | ConvertTo-Json -Depth 6
} finally {
    foreach ($linuxPid in $startedPids) {
        if ($linuxPid -match "^\d+$") {
            & wsl.exe -e bash -lc "kill $linuxPid 2>/dev/null || true" | Out-Null
        }
    }
    if ($backendProcess -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
