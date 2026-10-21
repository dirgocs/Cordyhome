# Mudanças

O Cordyhome segue [versionamento semântico](https://semver.org/lang/pt-BR/): enquanto a versão
começar com 0, mudanças de recurso sobem o número do meio e correções sobem o último.

## 0.6.0

- Nova integração **MQTT**, compatível com os SONOFF **OpenEdge** (MINI ONE PM e MINI PM), Tasmota,
  ESPHome, Shelly e Zigbee2MQTT. O Cordyhome tem um servidor MQTT embutido, com usuário e senha
  gerados, ou usa um servidor que já exista na casa.
- Os aparelhos MQTT aparecem sozinhos pela descoberta do Home Assistant, com liga/desliga, brilho
  das lâmpadas e medição de potência, tensão e corrente. O estado chega na hora, sem esperar a
  próxima leitura.
- Medidores sem relé aparecem sem o botão de liga/desliga e ficam de fora do "ligar tudo".

## 0.5.0

- Aparelhos passam a ter **capacidades** (liga/desliga, mede energia, brilho, tom do branco, cor),
  e a tela de cada aparelho mostra os controles que ele tem, de qualquer marca.
- Lâmpadas Tuya / Smart Life: brilho, tom do branco e cor pela rede local.
- Novos tipos de aparelho: relé e ar-condicionado.

## 0.4.0

- Nova tela **Adicionar aparelhos**, aberta pelo início e por Ajustes: você escolhe de onde vêm
  os aparelhos (por enquanto Tuya / Smart Life), e novas integrações entram na mesma lista.
- Ajustes ganha as seções **Integrações** e **Rede dos aparelhos**, no lugar de "Tomadas Tuya".
- Os textos do app falam em aparelhos, não só em tomadas.

## 0.3.0

- Tomadas numa rede separada (VLAN de IoT): novo campo **Ajustes → Tomadas Tuya → Rede das
  tomadas**. O Cordyhome procura as tomadas nessa faixa de IP pela porta TCP 6668, onde o
  broadcast não chega, na importação e na busca automática.
- A busca automática por tomadas offline roda em segundo plano, sem atrasar as leituras.
- Corrige o QR code da autorização Tuya, que saía cortado e não era lido pelo app.

## 0.2.2

- Corrige o app de desktop que fechava ao abrir em alguns Windows ("O identificador da janela é
  inválido", WebView2 0x80070578). A janela agora é criada já visível e só quando necessária.
- Se a janela não puder ser criada, o Cordyhome abre no navegador padrão e segue na bandeja.
- Novo item **Abrir no navegador** no menu do ícone da bandeja.
- Iniciado com o Windows, o app fica só na bandeja, sem criar a janela até ser aberto.

## 0.2.1

- App de desktop: registro de diagnóstico em `%LOCALAPPDATA%\com.cordyhome.app\logs\app.log`
  e mensagem de erro na tela se o app não conseguir abrir no Windows.

## 0.2.0

- App de desktop para Windows (Tauri): instalador `.exe` único, janela própria, ícone na bandeja,
  inicia com o Windows e mantém o hub gravando o consumo com a janela fechada.
- O Python do hub é preparado pelo próprio app, isolado do Python que o PC já tenha.
- Versão do app em **Ajustes → Sobre**, com aviso quando há uma versão nova.
- Releases numeradas (`vX.Y.Z`) geradas automaticamente a partir do arquivo `VERSION`.

## 0.1.0

- Fase 1: hub em Python com controle local das tomadas Tuya, importação pela conta do app,
  energia em tempo real e histórico, custo em R$, rotinas, alertas e interface web instalável.
