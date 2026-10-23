# Reset the admin password in the production backend container.
# Usage:
#   .\RESET-ADMIN.ps1                       -> prompts securely for the new password
#   .\RESET-ADMIN.ps1 -Password "New@12345" -> non-interactive
# Minimum length: 8 characters.

param([string]$Password)

$root = "E:\ParkingSystem"
Set-Location $root

if (-not $Password) {
    $sec = Read-Host "Enter NEW admin password" -AsSecureString
    $bss = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    $Password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bss)
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bss)
}

if ($Password.Length -lt 8) {
    Write-Host "ERROR: password must be at least 8 characters." -ForegroundColor Red
    exit 1
}

Write-Host "Resetting admin password ..." -ForegroundColor Cyan
docker compose -f "$root\docker-compose.prod.yml" --env-file "$root\.env.prod" exec backend python -m scripts.reset_admin --password "$Password"

if ($LASTEXITCODE -eq 0) {
    Write-Host "DONE: admin password UPDATED. Login with username 'admin' + the new password." -ForegroundColor Green
} else {
    Write-Host "FAILED: is the backend container running? Try: .\pcompose.ps1 ps" -ForegroundColor Red
}
