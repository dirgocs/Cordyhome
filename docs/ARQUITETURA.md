# Cordyhome — Arquitetura (proposta, em revisão)

App **gratuito e sem nuvem obrigatória** para gestão de dispositivos IoT Wi‑Fi da casa:
dispositivos, ambientes, **consumo de energia (prioridade nº 1)**, liga/desliga, agendamentos,
alertas e falhas — com o máximo de compatibilidade possível, incluindo desbloqueio de
dispositivos presos à nuvem.

## Requisitos

- **Custo zero:** apenas software livre e serviços gratuitos; nada de assinatura ou compra no app.
- **Local first:** controle e medição pela rede local; a internet é opcional.
- **Energia em primeiro lugar:** potência instantânea, consumo total, por período, por aparelho e
  por ambiente, custo estimado em R$.
- **Parque atual:** 17 tomadas **Steck compatíveis com Tuya**, com medição de energia. Mais
  dispositivos no futuro, de outras famílias.
- **Acesso remoto** seguro, sem abrir portas no roteador.
- Local de hospedagem do hub ainda indefinido → precisa rodar em PC, Raspberry Pi, mini PC ou NAS.

## Princípio: núcleo + adaptadores

```
            Interface (SvelteKit PWA) — celular · desktop · navegador (local ou remoto)
                                   │ REST + WebSocket (autenticado)
 ┌──────────────────────────── HUB (núcleo, Python) ────────────────────────────────┐
 │ dispositivos · ambientes · estado · energia · agendamentos · regras · alertas    │
 │ usuários · SQLite                                                                │
 └──────┬──────────────────┬────────────────────┬────────────────────┬──────────────┘
        │  interface de adaptadores (in-process) + protocolo externo (JSON-RPC/WebSocket)
   Tuya local         Shelly, Tasmota,       Matter                Adaptadores externos
   (tinytuya)         ESPHome, MQTT, HTTP    (python-matter-server) em qualquer linguagem
   Sonoff LAN                                                      / ponte Home Assistant
```

- O núcleo usa um **modelo único de dispositivo por capacidades** (onoff, power, energy, voltage,
  current, dimmer, color, temperature, climate…) e não conhece protocolos.
- **Adaptadores Python** rodam no processo do hub. Quando a melhor biblioteca de um protocolo
  estiver em outra linguagem, o adaptador roda como processo separado falando o **protocolo
  externo** (JSON-RPC sobre WebSocket) — é assim que contornamos limitações de linguagem.
- **MQTT** como língua franca (Tasmota, ESPHome, Shelly, Zigbee2MQTT).

## Tuya (tomadas Steck) — caminho gratuito

1. As tomadas precisam estar pareadas numa conta do app **Smart Life** ou **Tuya Smart** (ambos
   gratuitos). O app só é usado no pareamento inicial.
2. Assistente no Cordyhome guia a criação de uma conta gratuita na **Tuya IoT Platform**, a
   vinculação da conta do app e a extração automática de `device id` + `local key` + IP de todas
   as tomadas de uma vez (via tinytuya).
3. Daí em diante tudo é **local** via tinytuya (protocolos 3.1–3.5), com conexão persistente
   recebendo atualizações por push. A conta da nuvem não é mais necessária (só para re-extrair
   a chave se uma tomada for pareada de novo).
4. **Energia:** leitura dos data points típicos de tomadas com medição
   (ex.: `cur_power`, `cur_current`, `cur_voltage`, `add_ele`), com mapeamento configurável por
   modelo e detecção automática. A validar com uma tomada Steck real.
5. **Histórico:** a tomada só informa valores instantâneos e contadores; o histórico por período é
   gravado pelo próprio Cordyhome a partir do momento em que ele começa a rodar. Importar o
   histórico antigo da nuvem Tuya fica como opcional.
6. **Opcional/avançado:** trocar o firmware (OpenBeken/ESPHome) se o chip permitir — elimina a
   dependência da Tuya para sempre, mas exige abrir a tomada. A identificar o chip das Steck.

## Compatibilidade por família

| Família | Controle | Adaptador | Desbloqueio |
|---|---|---|---|
| Tuya / Smart Life (Steck etc.) | Local com *local key* | tinytuya | Assistente de local keys; troca de firmware quando possível |
| Shelly / Tasmota / ESPHome | Local (HTTP/MQTT/WS) | Python | Já abertos |
| Sonoff / eWeLink | Modo LAN; nuvem eWeLink como fallback | Python | Assistente de gravação Tasmota/ESPHome |
| Matter (Wi‑Fi) | Local | python-matter-server | Não necessário; pareamento multi-admin |
| Outros | API local, nuvem ou ponte HA | Varia | Caso a caso |

Gravação de firmware pelo navegador via ESP Web Tools (Web Serial). Dispositivos com secure boot
ou firmware assinado sem API são reportados como não suportados.

## Stack

- **Hub:** Python 3.12+, FastAPI (REST + WebSocket), SQLite (SQLAlchemy/SQLModel + Alembic),
  asyncio para polling/push, agendador e alertas.
- **Interface:** SvelteKit (Svelte 5, build estático servido pelo hub), Tailwind, PWA instalável.
- **Distribuição:** Docker (network host para descoberta na rede) primeiro; app desktop Tauri com o
  hub como sidecar depois.
- **Acesso remoto:** autenticação própria (usuários, hash de senha, sessões; passkeys depois) +
  **Tailscale** (gratuito para uso pessoal, sem domínio). Sem abrir portas no roteador.

## Fases

1. **MVP (Tuya + energia):** núcleo, UI, login, ambientes, adaptador Tuya com assistente de local
   keys, liga/desliga, painel de energia (instantâneo, por período, por aparelho/ambiente, custo
   em R$), agendamentos, alertas de falha/offline/consumo alto, simulador para desenvolvimento.
2. **Mais famílias:** Shelly, Tasmota, ESPHome, MQTT, HTTP genérico, Sonoff LAN, descoberta na rede.
3. **Matter e mais:** Matter, assistente de firmware, regras "se X então Y", notificações
   (push/Telegram, gratuitos).
4. **Distribuição:** Tauri, ponte Home Assistant, guia de acesso remoto com Tailscale.

## Pendências

- Identificar modelo exato e chip das tomadas Steck (etiqueta, caixa ou app).
- Confirmar em qual app as tomadas estão pareadas (Smart Life / Tuya Smart / outro).
- Definir onde o hub vai rodar 24h.
