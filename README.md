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

### Windows: app de desktop

1. Baixe o [**Cordyhome-Setup.exe**](https://github.com/dirgocs/Cordyhome/releases/latest/download/Cordyhome-Setup.exe).
2. Dê dois cliques. Se aparecer "O Windows protegeu o computador", clique em
   **Mais informações → Executar assim mesmo** (o instalador não tem assinatura paga).
3. Na primeira abertura, o app prepara o Python (alguns minutos). Se o Windows perguntar sobre o
   firewall, clique em **Permitir**: é o que deixa as tomadas e o celular acharem o Cordyhome.

O app abre numa janela própria. Ao fechar a janela, ele continua no ícone perto do relógio,
gravando o consumo e rodando as rotinas; para encerrar, use **Sair** nesse ícone. Ele também
inicia com o Windows (dá para desligar no mesmo menu). Não precisa de Git, Node.js nem Python
instalados: o instalador traz o [uv](https://docs.astral.sh/uv/), que baixa um Python 3.12 só
para o Cordyhome, num venv isolado.

- Dados (banco, contas, histórico): `%USERPROFILE%\.cordyhome`, mantidos em atualizações.
- Python do app e logs: `%LOCALAPPDATA%\com.cordyhome.app` (`logs\cordyhome.log`).
- Para atualizar: em **Ajustes → Sobre** o app avisa quando há versão nova; baixe e rode o
  instalador por cima.

O código do app está em `desktop/` (Tauri 2). O instalador é gerado pelo workflow
`.github/workflows/release.yml`.

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

### Tomadas numa rede separada (VLAN de IoT)

O Cordyhome acha as tomadas pelos avisos de broadcast que elas mandam, e broadcast não passa de
uma rede para outra. Se as tomadas ficam numa rede só para IoT e o computador do Cordyhome em
outra:

1. No roteador, permita que o computador do Cordyhome acesse a rede das tomadas na **porta TCP
   6668** (no UniFi: uma regra de firewall da rede principal para a rede IoT; a resposta volta
   por ser uma conexão já estabelecida).
2. Em **Ajustes → Tomadas Tuya → Rede das tomadas**, informe a faixa da rede IoT, por exemplo
   `192.168.20.0/24` (até /22, no máximo 4 faixas).

O Cordyhome testa a porta 6668 em cada endereço da faixa e reconhece cada tomada pela chave local
que veio da conta. Vale reservar IPs fixos para as tomadas no DHCP do roteador.

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

## Versões

O Cordyhome segue [versionamento semântico](https://semver.org/lang/pt-BR/). A versão fica no
arquivo `VERSION`, e o [CHANGELOG.md](CHANGELOG.md) descreve cada uma. Para lançar uma versão:

```bash
node scripts/version.mjs 0.3.0   # muda hub, interface e app de desktop (e o uv.lock)
# descreva as mudanças em "## 0.3.0" no CHANGELOG.md e faça o merge na main
```

Na `main`, o workflow **Release** cria a release `v0.3.0` com o instalador assim que essa versão
aparece. O CI confere se todos os arquivos estão na mesma versão.

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
desktop/                   App de desktop (Tauri 2): janela, bandeja e o hub embutido
scripts/version.mjs        Versão única de hub, interface e app de desktop
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
