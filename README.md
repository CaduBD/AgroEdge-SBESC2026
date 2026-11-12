# AgroEdge

Sistema embarcado de irrigação de precisão para o Vale do São Francisco, na Competição de Sistemas Embarcados do SBESC 2026. A placa (BitDogLab, RP2040) calcula a evapotranspiração pelo FAO-56, classifica o estado hídrico da lavoura com uma rede neural pequena e indica a lâmina de irrigação, tudo localmente.

## Pastas
- [`modelo/`](modelo/README.md): dataset rotulado (uva Itália, Petrolina 2000–2009), comparação MLP × SVM × Random Forest, treino da MLP final e conferência do firmware no PC.
- `firmware/modelo/`: o que vai para a placa, em MicroPython: programa principal (`main.py`), ET0 Penman-Monteith, drivers dos sensores (AM2302, piranômetro RS-485, anemômetro, pluviômetro, relógio DS3231/NTP), classificador, histórico de 28 dias, lâmina de irrigação e configuração do local. Ver [`firmware/modelo/LEIA-ME_ESTACAO.md`](firmware/modelo/LEIA-ME_ESTACAO.md).
- [`chatbot/`](chatbot/README.md): bot do Telegram para o produtor (hoje, válvula com confirmação, histórico e alertas), usando a API da plataforma.

## Documentação
- [`modelo/README.md`](modelo/README.md): como rodar e o resumo dos resultados.
- [`modelo/GUIA.md`](modelo/GUIA.md): explicação passo a passo.
- [`modelo/CODIGO_EXPLICADO.md`](modelo/CODIGO_EXPLICADO.md): o código, função por função.
- [`modelo/DECISOES.md`](modelo/DECISOES.md): por que o modelo é assim.
- [`modelo/versoes/README.md`](modelo/versoes/README.md): **as três versões do classificador (v1 em uso, v2 e v3 candidatas), comparação e o que a equipe precisa decidir.**

Equipe: Carlos Eduardo Batista Diniz, Thalles Inácio Araújo e Raimundo Ferreira do Nascimento Júnior. Orientador: Prof. Max Santana Rolemberg Farias (UNIVASF).
