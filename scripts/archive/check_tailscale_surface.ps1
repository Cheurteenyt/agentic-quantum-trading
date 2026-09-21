param(
    [string]$TailscaleIp = "100.114.51.121",
    [int]$CorePort = 8000,
    [int]$TimeoutMs = 800
)

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$Timeout
    )

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($Timeout, $false)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

$ports = @(
    22, 80, 135, 139, 445, 3389, 5040, 5357, 6333, 8080, 11434,
    2179, 2869, 49664, 49665, 49666, 49669, 49672, 49684, 49690, 54235,
    $CorePort
) | Sort-Object -Unique

$localTailscaleIps = @(tailscale ip -4 2>$null) + @(tailscale ip -6 2>$null)
$isSelfTest = $localTailscaleIps -contains $TailscaleIp
if ($isSelfTest) {
    Write-Warning "Testing your own Tailscale IP from the same Windows host can show false positives on Windows RPC/system ports. Run this same script from a separate Tailscale client for the authoritative result."
}

$rows = foreach ($port in $ports) {
    [PSCustomObject]@{
        Port = $port
        Open = Test-TcpPort -HostName $TailscaleIp -Port $port -Timeout $TimeoutMs
        Expected = if ($port -eq $CorePort) { "open when site is shared" } else { "closed" }
    }
}

$rows | Format-Table -AutoSize

$unexpected = $rows | Where-Object { $_.Port -ne $CorePort -and $_.Open }
if ($unexpected) {
    Write-Warning "Unexpected open ports on ${TailscaleIp}: $($unexpected.Port -join ', ')"
    if ($isSelfTest) {
        Write-Warning "Because this is a same-host self-test, verify again from a real client device after adding it to Tailscale."
    }
    exit 1
}

Write-Host "Tailscale surface check passed: no unexpected tested ports are open."
