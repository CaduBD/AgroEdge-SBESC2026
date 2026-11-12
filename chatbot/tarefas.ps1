# Comandos do chatbot no Windows (PowerShell). Uso: .\tarefas.ps1 <alvo>
#   .\tarefas.ps1 venv        (uma vez: cria o ambiente e instala tudo)
#   .\tarefas.ps1 verificar   (confere .env, plataforma e token)
#   .\tarefas.ps1 console     (conversa no terminal, sem Telegram)
#   .\tarefas.ps1 bot         (bot do Telegram + alertas)
param(
    [Parameter(Position = 0)][string]$Alvo = "ajuda",
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)][string[]]$Resto
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = "python"
if (Test-Path ".venv\Scripts\python.exe") { $py = ".venv\Scripts\python.exe" }

function Rodar([string]$exe, [string[]]$argumentos) {
    & $exe @argumentos
    if ($LASTEXITCODE -ne 0) { throw "falhou: $exe $($argumentos -join ' ')" }
}

switch ($Alvo) {
    "venv" {
        Rodar "python" @("-m", "venv", ".venv")
        Rodar ".venv\Scripts\python.exe" @("-m", "pip", "install", "-e", ".[dev]")
        if (-not (Test-Path ".env")) { Copy-Item ".env.exemplo" ".env"; Write-Host "criei o .env: preencha os tokens" }
    }
    "bot"       { Rodar $py (@("-m", "agroedge_bot") + $Resto) }
    "console"   { Rodar $py @("-m", "agroedge_bot", "--console") }
    "verificar" { Rodar $py @("-m", "agroedge_bot", "--verificar") }
    "test"      { Rodar $py @("-m", "pytest", "-q") }
    "lint" {
        Rodar $py @("-m", "ruff", "check", ".")
        Rodar $py @("-m", "ruff", "format", "--check", ".")
        Rodar $py @("-m", "mypy", "agroedge_bot")
    }
    "fmt" {
        Rodar $py @("-m", "ruff", "format", ".")
        Rodar $py @("-m", "ruff", "check", "--fix", ".")
    }
    default { Write-Host "alvos: venv bot console verificar test lint fmt" }
}
