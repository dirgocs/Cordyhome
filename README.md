# Cordyhome

Hub **gratuito e local** para controlar os aparelhos Wi‑Fi da casa e acompanhar o consumo de
energia, sem depender de nuvem, assinatura ou compras dentro do app.

- **Energia:** potência em tempo real, consumo por hora, dia e mês, por aparelho e por cômodo,
  custo em R$ pela sua tarifa e previsão da conta do mês.
- **Controle:** liga e desliga cada aparelho ou o cômodo inteiro. Aparelhos protegidos (como a
  geladeira) pedem confirmação e ficam de fora do "desligar tudo".
- **Rotinas:** liga e desliga em horários e dias da semana. Rodam no hub, mesmo com o celular
  desligado.
- **Alertas:** aparelho sem conexão, consumo acima de um limite, comando ou rotina que falhou.
- **Tomadas Tuya / Smart Life** (Steck e outras marcas): importação pela conta do app, com QR code
  e sem conta de desenvolvedor. Depois disso, o controle e a leitura de energia são 100% pela rede
  local.
- Interface web instalável (PWA) no celular e no computador, com tema claro e escuro.

> Estado atual: **Fase 1** do [plano de arquitetura](docs/ARQUITETURA.md). Por enquanto só há
> suporte a Tuya; Shelly, Tasmota, ESPHome, MQTT e Matter estão nas próximas fases.

## Como funciona

```
Celular / PC  ──►  Cordyhome (hub, na sua rede)  ──►  tomadas Tuya (protocolo local)
                   interface + API + SQLite
```

O hub precisa ficar ligado 24h (PC, Raspberry Pi, mini PC ou NAS) para gravar o consumo e
executar as rotinas. A interface é aberta pelo navegador de qualquer aparelho da casa.

## Instalação

### Windows: instalador de dois cliques

1. Baixe o [**Instalar-Cordyhome.cmd**](https://github.com/dirgocs/Cordyhome/releases/latest/download/Instalar-Cordyhome.cmd).
2. Dê dois cliques no arquivo. Se aparecer "O Windows protegeu o computador", clique em
   **Mais informações → Executar assim mesmo** (o instalador não tem assinatura paga).
3. Quando o Windows pedir permissão de administrador, clique em **Sim**. É só para liberar o
   Cordyhome no firewall em redes privadas.

O instalador baixa a versão mais recente, instala o Python pelo [uv](https://docs.astral.sh/uv/),
cria atalhos na área de trabalho e no menu Iniciar, configura o Cordyhome para iniciar junto com
o Windows e abre o app no navegador. Não precisa de Git nem de Node.js. Para atualizar, rode o
instalador de novo; os dados ficam em `%USERPROFILE%\.cordyhome` e são mantidos.

O programa fica em `%LOCALAPPDATA%\Cordyhome`, com o log em `logs\cordyhome.log`. Para parar,
use o atalho **Parar Cordyhome** no menu Iniciar.

O pacote usado pelo instalador é gerado a cada atualização da `main` e publicado na release
`latest` pelo workflow `.github/workflows/release.yml`.

### Opção 1: Docker (recomendado; Linux e Raspberry Pi)

```bash
git clone https://github.com/dirgocs/Cordyhome.git
cd Cordyhome
docker compose up -d --build
```

Abra `http://IP-DO-COMPUTADOR:8420` e crie a sua conta. Os dados ficam em `./data`.

O `docker-compose.yml` usa `network_mode: host`, necessário para achar as tomadas na rede por
broadcast UDP. No Docker Desktop para Windows e Mac, o modo host tem limitações; nesses sistemas,
prefira a opção 2.

### Opção 2: direto no computador (Windows, macOS, Linux)

Requisitos: [uv](https://docs.astral.sh/uv/getting-started/installation/) (gerenciador Python)
e [Node.js 22+](https://nodejs.org/).

```bash
git clone https://github.com/dirgocs/Cordyhome.git
cd Cordyhome/web && npm ci && npm run build
cd ../hub && uv run cordyhome
```

No Windows, permita o Python no firewall em **redes privadas** quando o sistema perguntar.
Isso libera a porta 8420 da interface e as portas UDP 6666/6667 da descoberta das tomadas.

### Configuração (variáveis de ambiente)

| Variável | Padrão | Uso |
|---|---|---|
| `CORDYHOME_PORT` | `8420` | Porta da interface e da API |
| `CORDYHOME_HOST` | `0.0.0.0` | Interface de rede |
| `CORDYHOME_DATA` | `~/.cordyhome` | Pasta do banco de dados |
| `CORDYHOME_DEMO` | desligado | `1` cria uma casa simulada com 60 dias de histórico |

## Conectando as tomadas Tuya

1. As tomadas precisam estar pareadas no app **Tuya Smart** ou **Smart Life** (gratuitos).
2. No Cordyhome: **Ajustes → Tomadas Tuya → Conectar conta**.
3. No app: **Eu → configurações → Conta e segurança → Código de usuário**. Copie o código para o
   Cordyhome.
4. Escaneie o QR code com o app (**Eu → ícone de leitura** no canto superior direito). Faça esta
   etapa com o Cordyhome aberto no computador, para escanear a tela com o celular.
5. Escolha as tomadas e importe.

Na autorização, o app mostra **"Home Assistant"**. É o nome do serviço oficial de
compartilhamento de dispositivos da Tuya que o Cordyhome usa (o mesmo da integração do Home
Assistant). A Tuya só emite esse tipo de credencial para parceiros. O Cordyhome usa a conta
apenas para ler a lista de aparelhos e as chaves locais.

**Depois da importação:**
- Tudo acontece pela rede local; a internet pode cair que o controle e a medição continuam.
- Se uma tomada for **pareada de novo** no app, a chave muda. Use **Ajustes → Adicionar ou
  sincronizar** para atualizar.
- Se o roteador trocar o IP de uma tomada, o Cordyhome a procura sozinho na rede a cada 10
  minutos. Também dá para usar **Ajustes → Procurar na rede**.

## Acesso de fora de casa

**Não abra portas no roteador.** Use o [Tailscale](https://tailscale.com/), gratuito para uso
pessoal:

1. Instale o Tailscale no computador do hub e no celular, com a mesma conta.
2. No celular, com o Tailscale ligado, abra `http://NOME-DO-PC:8420` (o nome aparece no app do
   Tailscale).
3. Para HTTPS e instalar como app: no computador do hub, rode `tailscale serve --bg 8420` e use o
   endereço `https://….ts.net` exibido.

O acesso é protegido pelo login do Cordyhome: senha com hash scrypt, sessão em cookie HttpOnly,
limite de tentativas e bloqueio de requisições vindas de outros sites.

## Desenvolvimento

```bash
# Hub com dados simulados (porta 8420)
cd hub && CORDYHOME_DEMO=1 CORDYHOME_DATA=/tmp/cordy uv run cordyhome

# Interface com recarga automática (porta 5173, repassa /api para o hub)
cd web && npm install && npm run dev
```

Testes e verificação:

```bash
cd hub && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd web && npm run check && npm run build
```

### Estrutura

```
hub/                       Python 3.11+ · FastAPI · SQLite
  cordyhome/adapters/      Contrato de adaptadores + Tuya (tinytuya, SDK de compartilhamento) + simulador
  cordyhome/services/      Estado e comandos (hub.py), energia, rotinas, alertas, vínculo Tuya
  cordyhome/api/           REST + WebSocket de tempo real
web/                       SvelteKit (Svelte 5), SPA estática servida pelo hub
docs/ARQUITETURA.md        Decisões de arquitetura e fases
```

## Limitações conhecidas

- A tomada não guarda histórico: o consumo passa a ser registrado quando o Cordyhome começa a
  rodar. O histórico antigo da nuvem Tuya não é importado.
- A precisão do consumo depende do medidor da tomada. O Cordyhome integra a potência lida a cada
  intervalo (10 s por padrão).
- Aparelhos Tuya que não suportam controle local (câmeras, alguns sensores) aparecem na
  importação como "Sem controle local" e não são importados.

## Licença

MIT
