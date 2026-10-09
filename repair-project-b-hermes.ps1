# Corrects the Project B profile created by an earlier setup script that used a second API port.
# Preserves its model, MCP server, other profile settings, and existing API key.
$ErrorActionPreference = 'Stop'
$profileHome = Join-Path (Join-Path $env:LOCALAPPDATA 'hermes\profiles') 'community-project-b'
$profileConfig = Join-Path $profileHome 'config.yaml'
$profileEnv = Join-Path $profileHome '.env'
$appEnv = Join-Path $PSScriptRoot '.env'

if (-not (Test-Path -LiteralPath $profileConfig)) { throw "Project B Hermes profile not found: $profileHome" }
if (-not (Test-Path -LiteralPath $profileEnv)) { throw "Profile .env not found: $profileEnv" }

$config = [System.IO.File]::ReadAllText($profileConfig)
# The old prototype script added only this gateway.api_server block to the secondary profile.
$config = [regex]::Replace($config, '(?m)^  api_server:\r?\n(?:^    .*(?:\r?\n|$))*', '')
$config = [regex]::Replace($config, '(?m)^gateway:\r?\n(?=(?:\r?\n)*mcp_servers:)', '')

$envLines = @([System.IO.File]::ReadAllLines($profileEnv) | Where-Object { $_ -notmatch '^\s*API_SERVER_(ENABLED|HOST|PORT)=' })
$keyLine = $envLines | Where-Object { $_ -match '^\s*API_SERVER_KEY=' } | Select-Object -First 1
if ($keyLine) {
    $apiKey = ($keyLine -split '=', 2)[1].Trim().Trim('"').Trim("'")
} else {
    $apiBytes = [byte[]]::new(32)
    $randomGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $randomGenerator.GetBytes($apiBytes)
    $randomGenerator.Dispose()
    $apiKey = [Convert]::ToBase64String($apiBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}
$envLines = @($envLines | Where-Object { $_ -notmatch '^\s*API_SERVER_KEY=' })
$envLines += "API_SERVER_KEY=$apiKey"
$appEnvLines = @()
if (Test-Path -LiteralPath $appEnv) { $appEnvLines = @([System.IO.File]::ReadAllLines($appEnv) | Where-Object { $_ -notmatch '^\s*HERMES_COMMUNITY_PROJECT_B_API_KEY=' }) }
$appEnvLines += "HERMES_COMMUNITY_PROJECT_B_API_KEY=$apiKey"

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($profileConfig, $config.TrimStart([char]0xFEFF).TrimEnd() + [Environment]::NewLine, $utf8NoBom)
[System.IO.File]::WriteAllText($profileEnv, ($envLines -join [Environment]::NewLine) + [Environment]::NewLine, $utf8NoBom)
[System.IO.File]::WriteAllText($appEnv, ($appEnvLines -join [Environment]::NewLine) + [Environment]::NewLine, $utf8NoBom)

Write-Host 'Project B now uses the shared Hermes API listener on port 8642.'
Write-Host 'Its API key is in the Hermes profile .env and this project’s ignored .env; no key was displayed.'
Write-Host 'Reload the profile: hermes -p community-project-b gateway restart'
