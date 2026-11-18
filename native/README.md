# OpenMonitor Switch — prévia nativa

Primeira etapa da reescrita em **Rust + Slint**, na branch `feature/native-ui-rewrite`.

## Requisitos

- Windows 10/11 x64.
- Rust estável instalado via rustup e toolchain MSVC (`rustup default stable-x86_64-pc-windows-msvc`).
- Visual Studio Build Tools (C++ build tools e Windows SDK), necessários para o linker MSVC.

## Rodar

No **PowerShell do Windows**, na raiz do repositório:

```powershell
cd native
cargo run
```

Para compilar um executável:

```powershell
cargo build --release
```

Executável: `native/target/release/openmonitor-switch.exe`.

## Implementado nesta prévia

- Janela nativa Slint com tema escuro.
- Ícone de bandeja do Windows, clique para restaurar janela.
- Menu **Abrir / Sair**.
- Fechar a janela ou clicar em **Ocultar na bandeja** mantém o processo ativo.
- Não abre janela de console na versão Windows.

## Ainda não implementado

- Comunicação DDC/CI, entradas e detecção de monitores.
- Identificação/overlay das telas (preservar comportamento do Python).
- Troca de entrada pelo menu de bandeja.
- Inicialização automática, instância única e restauração do ícone após reinicialização do Explorer.

Os menus dependentes de hardware permanecem desabilitados; nenhum monitor ou porta fictícia é exibido.

A versão Python continua na raiz do repositório e não é afetada.
