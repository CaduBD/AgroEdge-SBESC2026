# Placa de bancada (Fase 7 sem sensores)

Programa para a **BitDogLab sem os sensores** conversar com a plataforma seguindo o contrato
MQTT (seção 7 da especificação). Serve para testar a integração placa ↔ plataforma antes dos
sensores chegarem.

| De verdade, na placa | Fictício |
|---|---|
| Wi-Fi e hora por NTP (`relogio.py` do firmware) | temperatura, umidade, vento, radiação e chuva (curva de um dia de Petrolina) |
| MQTT com usuário/senha, LWT `offline`, config retida | |
| ET₀ FAO-56, Kc, **classificador MLP** e lâmina (`processar_dia` do firmware) | |
| buffer quando a rede cai e envio do atrasado | |
| relé da válvula no GPIO19 (comando do painel ou irrigação automática) | |

O firmware **não é alterado**: os módulos de cálculo são copiados como estão, e o `main.py` do
firmware vai para a placa com o nome `estacao.py` (para não rodar sozinho ao ligar).

## Fechamento do dia acelerado

Para ver vários fechamentos numa tarde, os primeiros `ACELERADO_DIAS` dias (padrão 7) fecham a
cada `DIA_MINUTOS` minutos (padrão 10), com datas a partir de hoje − 7 (nunca no futuro). Depois
disso a placa passa a fechar à meia-noite, como no campo. A irrigação automática do dia acelerado
liga o relé por um tempo comprimido na mesma proporção, e informa à plataforma os minutos
equivalentes. Todo fechamento leva o aviso "placa de bancada: clima fictício".

## Passo a passo

1. **Plataforma no ar** no notebook: `make up` (ou `.\tarefas.ps1 up`) e `make seed`.
2. **Mesma rede, em 2,4 GHz:** a Pico W **não enxerga redes de 5 GHz**. Use a rede 2,4 GHz do
   roteador (num roteador de duas bandas, o notebook pode ficar na 5 GHz: é a mesma rede interna).
3. **Firewall:** libere a porta 1883 no Windows (PowerShell como administrador, uma vez):
   ```powershell
   New-NetFirewallRule -DisplayName "AgroEdge MQTT 1883" -Direction Inbound -Protocol TCP -LocalPort 1883 -Action Allow
   ```
4. **Placa instalada num cultivo** na plataforma (tela Dispositivo). Sem config, a placa manda
   telemetria mas não fecha o dia.
5. **Gerar os arquivos** (a partir de `plataforma/`; a senha do Wi-Fi é pedida e não aparece):
   ```bash
   python placa_bancada/preparar.py --listar-ips          # descubra o IP do notebook
   python placa_bancada/preparar.py --host 192.168.0.10 --wifi "NomeDaRede2.4GHz"
   ```
   Isso cria `placa_bancada/para_a_placa/` (fora do git: tem as senhas do Wi-Fi e do MQTT).
   Sem `--wifi`, a placa usa o `WIFI_SSID` do `config_local.py` do firmware.
6. **Cliente MQTT na placa** (uma vez; o MicroPython não traz o `umqtt`):
   ```bash
   pip install mpremote
   mpremote mip install umqtt.simple
   ```
7. **Gravar na placa:** copie **todos** os arquivos de `para_a_placa/` para a raiz da placa.
   - Thonny: *Visualizar → Arquivos*, selecione os arquivos e *Enviar para /*.
   - ou: `cd placa_bancada/para_a_placa` e `mpremote cp *.py :`
   - Se o programa estiver rodando, o mpremote às vezes não consegue interromper
     ("could not enter raw repl"): tente de novo.
8. **Ligar ou reiniciar** a placa (Ctrl+D no Thonny). O `main.py` roda sozinho. No console aparece:
   ```
   [agroedge-00001] MQTT conectado em 192.168.0.10
   [agroedge-00001] telemetria seq=1 temp=29.2 buf=0
   [agroedge-00001] FECHAMENTO 2026-11-05: ET0=6.91 classe=0 lâmina=0.0 mm
   ```
9. **No painel:** a pill fica "Ao vivo", o Início mostra o clima e, a cada 10 min, um fechamento
   novo (com toast). Abra a válvula pelo Início e ouça o relé.

## Testes da Fase 7 com a placa

- **Comando:** "Abrir manualmente" por 1 min → relé liga, "Executado pela placa", relé desliga.
- **Config:** mude o solo do cultivo → a placa loga "config v2 aplicada" e o painel mostra
  "Aplicado na placa (v2)" na próxima telemetria.
- **Queda de rede:** desligue o Wi-Fi (ou o hotspot) por alguns minutos → a placa loga
  "(sem rede)" e guarda as leituras; ao religar, "rede de volta: enviando N leituras atrasadas",
  e o Histórico fica sem buracos.
- **Placa desligada:** tire da USB → em ~90 s a pill vira "Sem contato".

## Testar no PC antes (sem placa)

Roda o mesmo `bancada.py` contra o broker, com substitutos do MicroPython e uma queda simulada:

```bash
backend/.venv/Scripts/python placa_bancada/testar_no_pc.py --segundos 120 --dias 3 --dia-minutos 0.6 --queda 30-60
```

## Arquivos

| Arquivo | O que é |
|---|---|
| `bancada.py` | o programa (MicroPython) |
| `main.py` | chama a bancada ao ligar |
| `preparar.py` | monta `para_a_placa/` com o firmware e a config |
| `config_bancada.exemplo.py` | modelo da config (broker, senha, tempos) |
| `testar_no_pc.py` | roda o `bancada.py` no PC |

## Para quem for levar o MQTT para o firmware de verdade

As partes de conexão, buffer, config e comandos podem ser copiadas daqui para o `main.py`.
Três detalhes que **só apareceram na placa real** (no PC não acontecem):

1. **Publique bytes, não texto:** `client.publish(topico, json.dumps(d).encode("utf-8"))`. O
   `umqtt.simple` mede a mensagem com `len()`; num texto com acento ("histórico") isso conta
   caracteres e não bytes, e o JSON chega cortado (a plataforma rejeita como "JSON inválido").
2. **O `relogio.py` acerta o RTC na hora LOCAL** (UTC−3). O `ts` do contrato é UTC: some 3 h
   (`ts = time.time() + 10800`).
3. **Tempos medidos antes do NTP** pulam quando a hora é acertada. Marque os inícios de
   contagem (dia, ping) só depois do `relogio.iniciar()`.

Também: reconectar o Wi-Fi **sem bloquear** o laço (senão a telemetria para e a válvula pode
ficar aberta além do tempo durante uma queda).

4. **Com TLS, o RTC precisa estar em UTC.** O mbedTLS confere a validade do certificado lendo o
   RTC como se fosse UTC. Com o RTC na hora local (3 h atrás), um certificado recém-emitido ou
   renovado parece "do futuro": `ValueError: The certificate validity starts in the future`, e a
   placa fica até 3 h sem conectar depois de cada renovação (a cada ~60 dias). O programa de
   bancada passa o RTC para UTC logo depois do NTP (`rtc_para_utc()` no `bancada.py`). No
   firmware, o mais simples é o `relogio.py` guardar o RTC em UTC e converter para a hora local só
   ao mostrar ou ao decidir o dia.
5. **Erro de certificado é `ValueError`, não `OSError`:** pegue os dois na conexão, senão o
   programa para.

## Na VPS (broker com TLS na internet)

A placa fala com `mqtt.agroedge.tech:8883` com TLS e confere o certificado com a raiz
**ISRG Root X2** (`isrg_root_x2.pem`, público, ~0,5 KB). Testado em 13/11/2026:

- TLS 1.2 com ECDHE-ECDSA-AES256-GCM, verificando a cadeia `YE1 ← Root YE ← ISRG Root X2`;
- telemetria a cada 60 s, config v6 confirmada e reconexão sozinha 12 s depois de um reset.

```bash
python placa_bancada/preparar.py --vps     # lê a senha da placa na VPS pela chave SSH
```

Sem `--wifi`, o script reaproveita o Wi-Fi da última preparação. Grave na placa os arquivos de
`para_a_placa/`: no mínimo `bancada.py`, `config_bancada.py` e `isrg_root_x2.der`.

Para voltar ao broker do notebook, rode de novo com `--host IP-DO-NOTEBOOK`.

## Teste de memória do TLS (MQTT criptografado, para o deploy na web)

Medido na BitDogLab (Pico W, MicroPython 1.29, mbedTLS) com o programa de bancada inteiro
carregado, conectando a um broker de teste só com TLS, com usuário e senha, **verificando o
certificado** (CA de teste; SAN com o IP do servidor), TLS 1.3.

| Etapa | RAM livre |
|---|---|
| MicroPython vazio | 184 KB |
| Programa de bancada carregado (classificador, ET₀, histórico…) | 139 KB |
| Contexto TLS + CA carregada | 135 KB |
| Conectado por TLS | 112 KB |
| Fechamento do dia (ET₀ + MLP) com o TLS aberto | 110 KB |

- **Conexão TLS aberta:** ~23 KB.
- **Pico do handshake:** precisa de **~64 KB livres** (com 56 KB falha com `ENOMEM`). Igual com
  certificado ECDSA P-256 e RSA-2048.
- **Folga:** o programa deixa ~135 KB livres, então sobram **~70 KB** além do pico.
- **Tempo do handshake + login:** 1,3–1,9 s (só na conexão; depois não pesa).

**Conclusão:** o MQTT com TLS cabe na placa com folga, inclusive com o classificador. Cuidados
para o firmware definitivo:

1. Faça o handshake **logo depois de ligar** ou depois de um `gc.collect()`, com a memória menos
   fragmentada; não com o buffer de leituras cheio.
2. Um certificado real (Let's Encrypt) vem com a cadeia intermediária, um pouco maior que a CA de
   teste: confirme a folga no servidor de verdade.
3. A placa precisa da **CA raiz** para verificar o servidor. Na VPS é a **ISRG Root X2**
   (543 bytes em DER), porque o certificado do broker é ECDSA.
4. No `umqtt.simple`, passe o contexto: `MQTTClient(..., ssl=ctx)` com
   `ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)`, `ctx.verify_mode = ssl.CERT_REQUIRED` e
   `ctx.load_verify_locations(cadata=CA_DER)`.
