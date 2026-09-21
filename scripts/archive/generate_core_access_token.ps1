param(
    [int]$Bytes = 32,
    [ValidatePattern('^[A-Z0-9_]+$')]
    [string]$Name = "CORE_ACCESS_TOKEN"
)

$buffer = New-Object byte[] $Bytes
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $rng.GetBytes($buffer)
}
finally {
    $rng.Dispose()
}
$token = [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')

Write-Output "$Name=$token"
