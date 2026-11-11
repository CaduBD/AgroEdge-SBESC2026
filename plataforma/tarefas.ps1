# Equivalente do Makefile para Windows (PowerShell), para quem não tem o make.
# Uso: .\tarefas.ps1 <alvo> [argumentos]
#   .\tarefas.ps1 up
#   .\tarefas.ps1 seed
#   .\tarefas.ps1 dispositivo agroedge-00002
#   .\tarefas.ps1 sim                       (padrão: --dias 3 --acelerar 288)
#   .\tarefas.ps1 sim --dias 30 --acelerar 2000 --queda 02:00-04:00
param(
    [Parameter(Position = 0)][string]$Alvo = "ajuda",
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)][string[]]$Resto
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = "python"
if (Test-Path "backend\.venv\Scripts\python.exe") { $py = "backend\.venv\Scripts\python.exe" }
$pyAbs = if ($py -eq "python") { "python" } else { (Resolve-Path $py).Path }

function Rodar([string]$exe, [string[]]$argumentos) {
    & $exe @argumentos
    if ($LASTEXITCODE -ne 0) { throw "falhou: $exe $($argumentos -join ' ')" }
}

switch ($Alvo) {
    "env"         { Rodar $py @("backend/scripts/gerar_env.py") }
    "passwd"      { Rodar $py @("backend/scripts/gerar_passwd.py") }
    "up" {
        Rodar $py @("backend/scripts/gerar_env.py")
        Rodar $py @("backend/scripts/gerar_passwd.py")
        Rodar "docker" @("compose", "up", "-d", "--build")
    }
    "down"        { Rodar "docker" @("compose", "down") }
    "logs"        { Rodar "docker" @("compose", "logs", "-f", "--tail=100") }
    "migrate"     { Rodar "docker" @("compose", "exec", "app", "alembic", "upgrade", "head") }
    "seed"        { Rodar "docker" @("compose", "exec", "app", "python", "-m", "scripts.seed") }
    "dispositivo" {
        if (-not $Resto) { throw "uso: .\tarefas.ps1 dispositivo agroedge-00002" }
        Rodar $py (@("backend/scripts/criar_dispositivo.py") + $Resto)
    }
    "sim" {
        $simArgs = if ($Resto) { $Resto } else { @("--dias", "3", "--acelerar", "288") }
        Rodar $py (@("simulador/simulador.py") + $simArgs)
    }
    "test"        { Push-Location backend; try { Rodar $pyAbs @("-m", "pytest", "-q") } finally { Pop-Location } }
    "lint" {
        Push-Location backend
        try {
            Rodar $pyAbs @("-m", "ruff", "check", ".", "../simulador")
            Rodar $pyAbs @("-m", "mypy", "app")
        } finally { Pop-Location }
    }
    "fmt" {
        Push-Location backend
        try {
            Rodar $pyAbs @("-m", "ruff", "format", ".", "../simulador")
            Rodar $pyAbs @("-m", "ruff", "check", "--fix", ".", "../simulador")
        } finally { Pop-Location }
    }
    "venv" {
        # Ambiente local para testes, lint e simulador
        Rodar "python" @("-m", "venv", "backend/.venv")
        Rodar "backend\.venv\Scripts\python.exe" @("-m", "pip", "install", "-e", "backend[dev]", "paho-mqtt>=2.1")
    }
    default {
        Write-Host "alvos: venv env passwd up down logs migrate seed dispositivo sim test lint fmt"
    }
}
