# Cordyhome — Arquitetura (proposta, em revisão)

App de gestão de dispositivos IoT Wi‑Fi da casa: dispositivos, ambientes, consumo de energia,
liga/desliga, agendamentos, alertas e falhas — com o máximo de compatibilidade possível,
incluindo desbloqueio de dispositivos presos à nuvem.

## Princípio: núcleo + adaptadores em qualquer linguagem

```
            Interface (SvelteKit PWA) — celular · desktop · navegador (local ou remoto)
                                   │ REST + WebSocket (autenticado)
 ┌──────────────────────────── HUB (núcleo, TypeScript) ────────────────────────────┐
 │ dispositivos · ambientes · estado · agendamentos · regras · alertas · energia    │
 │ usuários · SQLite                                                                │
 └──────┬──────────────────┬────────────────────┬────────────────────┬──────────────┘
        │   protocolo de adaptadores (JSON-RPC sobre WebSocket)
   TS embutidos       Python (processo)     Matter (TS)         Ponte Home Assistant
   Shelly, Tasmota,   Tuya local            matter.js           (opcional)
   ESPHome, MQTT,     (tinytuya)
   HTTP, Sonoff LAN
```

- O núcleo usa um **modelo único de dispositivo por capacidades** (onoff, power, energy, dimmer,
  color, temperature, climate…) e não conhece protocolos.
- **Adaptadores** traduzem cada família para esse modelo. Os TS rodam no processo do hub; os de
  outras linguagens rodam como processos separados falando o mesmo protocolo. Assim usamos a
  melhor biblioteca de cada protocolo, seja qual for a linguagem.
- **MQTT** como língua franca (Tasmota, ESPHome, Shelly, Zigbee2MQTT).

## Compatibilidade por família

| Família | Controle | Adaptador | Desbloqueio |
|---|---|---|---|
| Shelly / Tasmota / ESPHome | Local (HTTP/MQTT/WS) | TS | Já abertos |
| Tuya / Smart Life | Local com *local key* | Python (tinytuya, protocolos 3.3–3.5) | Assistente de obtenção de local keys (Tuya IoT); troca de firmware (OpenBeken/ESPHome) quando possível |
| Sonoff / eWeLink | Modo LAN; nuvem eWeLink como fallback | TS | Assistente de gravação Tasmota/ESPHome |
| Matter (Wi‑Fi) | Local | TS (matter.js) | Não necessário; pareamento multi-admin |
| Outros | API local, nuvem ou ponte HA | Varia | Caso a caso |

Gravação de firmware pelo navegador via ESP Web Tools (Web Serial). Dispositivos com secure boot
ou firmware assinado sem API são reportados como não suportados.

## Stack

- **Hub:** TypeScript, Node LTS (avaliar Bun), Fastify, SQLite + Drizzle.
- **Interface:** SvelteKit (Svelte 5), Tailwind, PWA instalável.
- **Distribuição:** Docker (network host para mDNS) primeiro; app desktop Tauri com o hub como sidecar depois.
- **Acesso remoto:** autenticação própria (usuários, hash de senha, sessões; passkeys depois) +
  Tailscale ou Cloudflare Tunnel. Sem abrir portas no roteador.

## Fases

1. **MVP:** núcleo, UI, login, ambientes, liga/desliga, consumo/custo (R$), agendamentos, alertas
   de falha/offline, descoberta na rede. Adaptadores: Shelly, Tasmota, ESPHome, MQTT, HTTP genérico, simulador.
2. **Tuya + Sonoff:** adaptador Python, assistente de local key, eWeLink LAN.
3. **Matter e mais:** Matter, assistente de firmware, regras "se X então Y", notificações (push/Telegram).
4. **Distribuição:** Tauri, ponte Home Assistant, guia de acesso remoto.
