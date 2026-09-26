# Cordyhome — Arquitetura

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
- Hospedagem: **PC do usuário** por enquanto; **Raspberry Pi** depois (build ARM64 obrigatório).
- O app oficial cobra para exibir o consumo → o Cordyhome lê os dados de energia **direto da tomada**,
  sem depender do app.

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

- **Hub:** Python 3.11+, FastAPI (REST + WebSocket), SQLite via `sqlite3` da biblioteca padrão
  (migrações numeradas no código; sem ORM, o esquema é pequeno), asyncio para leitura, agendador
  e alertas. Chamadas bloqueantes (tinytuya, SDK Tuya) rodam em threads.
- **Interface:** SvelteKit (Svelte 5, SPA estática servida pelo hub), CSS próprio com tokens de
  design (sem framework de utilitários), gráficos SVG próprios, PWA instalável.
- **Distribuição:** Docker (network host para descoberta na rede) primeiro; app desktop Tauri com o
  hub como sidecar depois.
- **Acesso remoto:** autenticação própria (usuários, hash de senha, sessões; passkeys depois) +
  **Tailscale** (gratuito para uso pessoal, sem domínio). Sem abrir portas no roteador.

## Energia

- Leitura de potência a cada ciclo (10 s por padrão); a energia é integrada pelo método do
  trapézio entre leituras consecutivas, sem extrapolar lacunas maiores que 60 s.
- Buckets de 1 minuto (14 dias, para curvas detalhadas) e de 1 hora (permanente, para
  relatórios). Dia, mês e 12 meses são agregados a partir das horas, no fuso configurado.
- Aparelho sem medidor: consumo estimado pela potência nominal informada, quando ligado.

## Segurança

- Usuários locais com senha em scrypt; sessão em cookie HttpOnly/SameSite=Lax (Secure em HTTPS).
- Limite de tentativas de login por IP; requisições que alteram estado precisam vir da mesma
  origem (proteção CSRF).
- A chave local das tomadas fica só no banco do hub e nunca é enviada para a interface.

## Fases

1. **MVP (Tuya + energia)** (implementado): núcleo, UI, login, ambientes, adaptador Tuya com assistente de local
   keys, liga/desliga, painel de energia (instantâneo, por período, por aparelho/ambiente, custo
   em R$), agendamentos, alertas de falha/offline/consumo alto, simulador para desenvolvimento.
2. **Mais famílias:** Shelly, Tasmota, ESPHome, MQTT, HTTP genérico, Sonoff LAN, descoberta na rede.
3. **Matter e mais:** Matter, assistente de firmware, regras "se X então Y", notificações
   (push/Telegram, gratuitos).
4. **Distribuição:** Tauri, ponte Home Assistant, guia de acesso remoto com Tailscale.

## Pendências

- Confirmar pela Tuya IoT Platform (depuração de dispositivo, gratuita) que as tomadas Steck expõem
  os data points de energia e em qual escala.
- Identificar o chip (opcional; via certificado Anatel da etiqueta ou abrindo a tomada).
- Confirmar em qual app as tomadas estão pareadas (Smart Life / Tuya Smart / outro).
- Sistema operacional do PC e modelo do Raspberry Pi.
