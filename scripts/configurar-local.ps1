$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

function Stop-WithMessage {
    param([string]$Message)
    Write-Host ""
    Write-Host $Message -ForegroundColor Red
    exit 1
}

if (-not (Get-Command node.exe -ErrorAction SilentlyContinue)) {
    Stop-WithMessage "Node.js no esta instalado. Instala Node.js 20 o superior desde https://nodejs.org y vuelve a ejecutar este archivo."
}

$nodeVersion = (& node.exe --version).Trim()
Write-Host "Node.js detectado: $nodeVersion" -ForegroundColor Green

$envPath = Join-Path $ProjectRoot ".env.local"
$needsKey = $true

if (Test-Path -LiteralPath $envPath) {
    $currentEnv = Get-Content -Raw -LiteralPath $envPath
    if ($currentEnv -match "(?m)^OPENAI_API_KEY=sk-[^\s]+$") {
        $needsKey = $false
        Write-Host "Se encontro una API key configurada en .env.local." -ForegroundColor Green
    }
}

if ($needsKey) {
    Write-Host ""
    Write-Host "Crea o copia tu API key desde: https://platform.openai.com/api-keys"
    Write-Host "La clave se guardara solamente en .env.local dentro de esta carpeta."
    $secureKey = Read-Host "Pega tu OPENAI_API_KEY" -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)

    try {
        $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }

    if ([string]::IsNullOrWhiteSpace($apiKey) -or -not $apiKey.StartsWith("sk-")) {
        Stop-WithMessage "La clave no parece valida. Debe comenzar con sk-."
    }

    $envContents = "OPENAI_API_KEY=$apiKey`r`nOPENAI_MODEL=gpt-5.4-mini`r`n"
    [IO.File]::WriteAllText($envPath, $envContents, [Text.UTF8Encoding]::new($false))
    $apiKey = $null
    Write-Host ".env.local creado correctamente." -ForegroundColor Green
}

Write-Host ""
Write-Host "Instalando dependencias..." -ForegroundColor Cyan
& npm.cmd install
if ($LASTEXITCODE -ne 0) {
    Stop-WithMessage "npm install fallo. Comprueba tu conexion a internet e intenta nuevamente."
}

Write-Host ""
Write-Host "El proyecto se abrira en http://localhost:3000" -ForegroundColor Green
Write-Host "Para detenerlo, presiona Ctrl+C en esta ventana." -ForegroundColor Yellow
Write-Host ""

Start-Job -ScriptBlock {
    Start-Sleep -Seconds 3
    Start-Process "http://localhost:3000"
} | Out-Null
& npm.cmd run dev
