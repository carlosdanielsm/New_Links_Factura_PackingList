$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

function Stop-WithMessage {
    param([string]$Message)
    Write-Host ""
    Write-Host $Message -ForegroundColor Red
    exit 1
}

function Get-MaskedKey {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return "no configurada"
    }

    $key = $Value.Trim().Trim('"').Trim("'")
    if ($key.Length -le 12) {
        return "configurada, pero demasiado corta"
    }

    return "$($key.Substring(0, 7))...$($key.Substring($key.Length - 4)) ($($key.Length) caracteres)"
}

function Get-EnvValue {
    param(
        [string]$Path,
        [string]$Name
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    $match = Select-String -LiteralPath $Path -Pattern "^$Name=(.+)$" | Select-Object -First 1
    if (-not $match) {
        return $null
    }

    return $match.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
}

function Save-EnvEverywhere {
    param([string]$ApiKey)

    $userConfigDir = Join-Path $env:LOCALAPPDATA "ProveedorIA"
    $projectEnvPath = Join-Path $ProjectRoot ".env.local"
    $projectDotEnvPath = Join-Path $ProjectRoot ".env"
    $userEnvPath = Join-Path $userConfigDir ".env.local"
    $envContents = "OPENAI_API_KEY=$ApiKey`r`nOPENAI_MODEL=gpt-4.1-mini`r`n"

    if (-not (Test-Path -LiteralPath $userConfigDir)) {
        New-Item -ItemType Directory -Path $userConfigDir | Out-Null
    }

    [IO.File]::WriteAllText($projectEnvPath, $envContents, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($projectDotEnvPath, $envContents, [Text.UTF8Encoding]::new($false))
    try {
        [IO.File]::WriteAllText($userEnvPath, $envContents, [Text.UTF8Encoding]::new($false))
    }
    catch {
        Write-Host "Aviso: no se pudo guardar la API key en el guardado local de usuario. Quedo guardada en .env y .env.local." -ForegroundColor Yellow
    }
}

$projectEnvPath = Join-Path $ProjectRoot ".env.local"
$projectDotEnvPath = Join-Path $ProjectRoot ".env"
$userEnvPath = Join-Path (Join-Path $env:LOCALAPPDATA "ProveedorIA") ".env.local"

Write-Host ""
Write-Host "Actualizar OPENAI_API_KEY de Proveedor IA" -ForegroundColor Cyan
Write-Host "No se mostrara la clave completa." -ForegroundColor DarkGray
Write-Host ""
Write-Host ".env.local actual: $(Get-MaskedKey (Get-EnvValue $projectEnvPath 'OPENAI_API_KEY'))"
Write-Host ".env actual:       $(Get-MaskedKey (Get-EnvValue $projectDotEnvPath 'OPENAI_API_KEY'))"
Write-Host "Usuario local:    $(Get-MaskedKey (Get-EnvValue $userEnvPath 'OPENAI_API_KEY'))"
Write-Host ""
Write-Host "Pega una API key valida creada en https://platform.openai.com/api-keys"
Write-Host "Importante: ChatGPT Plus no crea automaticamente saldo/API key de Platform." -ForegroundColor Yellow

$secureKey = Read-Host "OPENAI_API_KEY nueva" -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)

try {
    $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
}

$apiKey = $apiKey.Trim().Trim('"').Trim("'")

if ([string]::IsNullOrWhiteSpace($apiKey) -or -not $apiKey.StartsWith("sk-")) {
    Stop-WithMessage "La clave no parece valida. Debe comenzar con sk-."
}

Save-EnvEverywhere $apiKey
Write-Host ""
Write-Host "API key actualizada en .env, .env.local y guardado local de usuario." -ForegroundColor Green
Write-Host "Huella guardada: $(Get-MaskedKey $apiKey)" -ForegroundColor Green
Write-Host ""
Write-Host "Ahora reinicia el servidor:" -ForegroundColor Cyan
Write-Host "npm run stop" -ForegroundColor Yellow
Write-Host "npm run dev" -ForegroundColor Yellow

$apiKey = $null
