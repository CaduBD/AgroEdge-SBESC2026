# Comandos do dia a dia. No Windows sem make, use o equivalente: .\tarefas.ps1 <alvo>
PY ?= python
SERIAL ?=
SIM_ARGS ?= --dias 3 --acelerar 288

.PHONY: env passwd up down logs migrate seed dispositivo sim test lint fmt

env:            ## cria o .env com segredos aleatórios (não sobrescreve)
	$(PY) backend/scripts/gerar_env.py

passwd:         ## cria mosquitto/passwd (plataforma + placa padrão) a partir do .env
	$(PY) backend/scripts/gerar_passwd.py

up: env passwd  ## sobe broker e app
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

migrate:
	docker compose exec app alembic upgrade head

seed:           ## usuário, token, placa padrão, fazenda e cultivo de exemplo
	docker compose exec app python -m scripts.seed

dispositivo:    ## make dispositivo SERIAL=agroedge-00002
	@test -n "$(SERIAL)" || (echo "use: make dispositivo SERIAL=agroedge-00002" && exit 1)
	$(PY) backend/scripts/criar_dispositivo.py $(SERIAL)

sim:            ## simulador acelerado com a placa padrão
	$(PY) simulador/simulador.py $(SIM_ARGS)

test:
	cd backend && $(PY) -m pytest -q

lint:
	cd backend && $(PY) -m ruff check . ../simulador && $(PY) -m mypy app

fmt:
	cd backend && $(PY) -m ruff format . ../simulador && $(PY) -m ruff check --fix . ../simulador
