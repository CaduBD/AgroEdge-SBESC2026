# Comandos do chatbot. No Windows sem make, use: .\tarefas.ps1 <alvo>
PY ?= .venv/bin/python

.PHONY: venv bot console verificar test lint fmt

venv:           ## cria o ambiente, instala e copia o .env de exemplo
	python3 -m venv .venv
	$(PY) -m pip install -e ".[dev]"
	@test -f .env || (cp .env.exemplo .env && echo "criei o .env: preencha os tokens")

bot:            ## bot do Telegram + alertas do SSE
	$(PY) -m agroedge_bot

console:        ## conversa no terminal, sem Telegram
	$(PY) -m agroedge_bot --console

verificar:      ## confere .env, plataforma e token
	$(PY) -m agroedge_bot --verificar

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check . && $(PY) -m ruff format --check . && $(PY) -m mypy agroedge_bot

fmt:
	$(PY) -m ruff format . && $(PY) -m ruff check --fix .
