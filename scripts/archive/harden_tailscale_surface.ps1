param(
    [string]$TailscaleIp = "100.114.51.121",
    [int]$CorePort = 8000,
    [string]$InterfaceAlias = "Tailscale"
)

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $isAdmin) {
    throw "Run this script from PowerShell as Administrator."
}

Write-Host "Disabling broad Tailscale inbound service exposure..."
Get-NetFirewallRule -DisplayName "Tailscale-In" -ErrorAction SilentlyContinue |
    Disable-NetFirewallRule

Write-Host "Keeping Tailscale process rule enabled so the VPN client itself still works."

Write-Host "Disabling Windows file-sharing bindings on the Tailscale adapter..."
Disable-NetAdapterBinding -Name $InterfaceAlias -ComponentID ms_server -ErrorAction SilentlyContinue

Write-Host "Disabling broad Hyper-V/WMI/RPC inbound management rules..."
Get-NetFirewallRule -Direction Inbound -Enabled True -Action Allow -ErrorAction SilentlyContinue |
    Where-Object {
        $_.DisplayName -match "Hyper-V|Clients de gestion Microsoft Hyper-V|WMI|RPC-EPMAP|REMOTE_DESKTOP_TCP_IN|MIG-TCP|Assistance . distance"
    } |
    Disable-NetFirewallRule

Get-NetFirewallRule -DisplayName "Core Equity Tailscale 8000" -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule

New-NetFirewallRule `
    -DisplayName "Core Equity Tailscale 8000" `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort $CorePort `
    -LocalAddress $TailscaleIp `
    -Profile Any | Out-Null

Get-NetFirewallRule -DisplayName "Core Equity Block Windows Services on Tailscale" -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule

$blockedTcpPorts = @(
    "135",        # RPC endpoint mapper
    "139",        # NetBIOS session service
    "445",        # SMB
    "2179",       # Hyper-V VM console
    "2869",       # UPnP/SSDP eventing
    "5040",       # Windows CDPSvc
    "5357",       # Web Services on Devices
    "49664-49690",
    "54235"
)

New-NetFirewallRule `
    -DisplayName "Core Equity Block Windows Services on Tailscale" `
    -Direction Inbound `
    -Action Block `
    -Protocol TCP `
    -LocalAddress $TailscaleIp `
    -InterfaceAlias $InterfaceAlias `
    -LocalPort $blockedTcpPorts `
    -Profile Any | Out-Null

Get-NetFirewallRule -DisplayName "Core Equity Block NetBIOS UDP on Tailscale" -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule

New-NetFirewallRule `
    -DisplayName "Core Equity Block NetBIOS UDP on Tailscale" `
    -Direction Inbound `
    -Action Block `
    -Protocol UDP `
    -LocalAddress $TailscaleIp `
    -InterfaceAlias $InterfaceAlias `
    -LocalPort 137,138 `
    -Profile Any | Out-Null

Get-NetFirewallRule -DisplayName "Core Equity Block Windows Services on Tailscale Outbound Test Guard" -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule

New-NetFirewallRule `
    -DisplayName "Core Equity Block Windows Services on Tailscale Outbound Test Guard" `
    -Direction Outbound `
    -Action Block `
    -Protocol TCP `
    -RemoteAddress $TailscaleIp `
    -RemotePort $blockedTcpPorts `
    -Profile Any | Out-Null

Write-Host "Tailscale surface hardened. Expected open port: TCP $CorePort only."
Write-Host "Verify with:"
Write-Host '  Test-NetConnection 100.114.51.121 -Port 445'
Write-Host '  Test-NetConnection 100.114.51.121 -Port 8000'
