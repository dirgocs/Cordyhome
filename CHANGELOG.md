# Mudanças

O Cordyhome segue [versionamento semântico](https://semver.org/lang/pt-BR/): enquanto a versão
começar com 0, mudanças de recurso sobem o número do meio e correções sobem o último.

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
