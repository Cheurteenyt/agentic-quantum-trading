param(
    [string]$TailscaleIp = "100.114.51.121",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $isAdmin) {
    throw "Run this script from PowerShell as Administrator."
}

Get-NetFirewallRule -DisplayName "Core Equity Tailscale 8000" -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule

New-NetFirewallRule `
    -DisplayName "Core Equity Tailscale 8000" `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort $Port `
    -LocalAddress $TailscaleIp `
    -Profile Any | Out-Null

Write-Host "Core Equity firewall hardened: TCP $Port allowed only on $TailscaleIp"
Get-NetFirewallRule -DisplayName "Core Equity Tailscale 8000" |
    Get-NetFirewallAddressFilter |
    Select-Object LocalAddress, RemoteAddress
Get-NetFirewallRule -DisplayName "Core Equity Tailscale 8000" |
    Get-NetFirewallPortFilter |
    Select-Object Protocol, LocalPort, RemotePort
