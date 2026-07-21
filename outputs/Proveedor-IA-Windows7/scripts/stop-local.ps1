$ErrorActionPreference = "Stop"

$ports = 3000..3010
$listeners = @()

foreach ($line in (netstat -ano | Select-String "LISTENING")) {
    $text = $line.ToString().Trim()
    if ($text -match ":(\d+)\s+.*\s+LISTENING\s+(\d+)$") {
        $port = [int]$Matches[1]
        $processId = [int]$Matches[2]
        if ($ports -contains $port) {
            $listeners += [pscustomobject]@{ Port = $port; PID = $processId }
        }
    }
}

$targets = $listeners | Sort-Object PID -Unique

if (-not $targets -or $targets.Count -eq 0) {
    Write-Host "No se encontraron servidores escuchando entre los puertos 3000 y 3010." -ForegroundColor Green
    exit 0
}

Write-Host "Se cerraran procesos locales en puertos 3000-3010:" -ForegroundColor Yellow
$targets | ForEach-Object {
    Write-Host "PID $($_.PID), puerto $($_.Port)"
}

foreach ($target in $targets) {
    try {
        Stop-Process -Id $target.PID -Force -ErrorAction Stop
        Write-Host "Cerrado PID $($target.PID)" -ForegroundColor Green
    }
    catch {
        Write-Host "No se pudo cerrar PID $($target.PID): $($_.Exception.Message)" -ForegroundColor Red
    }
}
