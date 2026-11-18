# Reescrita nativa — requisitos de produto e bandeja do Windows

Branch: `feature/native-ui-rewrite`. A `main` em Python permanece intacta até a versão nativa ser validada em hardware real.

## Stack

- Rust compilado para Windows.
- Slint para UI nativa e `SystemTrayIcon` para bandeja do sistema (suportado pelo Slint atual).
- API Win32/DXVA2 para enumeração, identificação e comunicação DDC/CI.
- Identificação de telas (overlays), com a mesma posição, identificação física e funcionamento da aplicação Python existente.

## Comportamento da bandeja (essencial)

1. Ao iniciar, criar o ícone de bandeja; evitar mostrar console de terminal na versão Release.
2. Fechar a janela principal **oculta** a janela, mas **não encerra** a aplicação.
3. Clique duplo no ícone: abrir/restaurar a janela principal.
4. Menu contextual: **Abrir OpenMonitor Switch**, **Identificar telas**, **Detectar monitores**, submenu **Monitores** (cada monitor com suas entradas realmente anunciadas), **Iniciar com o Windows** (opcional; configuração por usuário), **Sair**.
5. **Sair** termina efetivamente o processo, liberando os recursos DDC/CI e o ícone.
6. O menu da bandeja usa apenas códigos retornados por `vcp(60(...))`; nenhuma porta presumida pelo modelo ou por tabelas fixas.
7. Troca sem caixa de confirmação. Se possível, indicar operação em andamento sem bloquear a UI ou o menu.
8. Ao reiniciar o Explorer do Windows, recuperar a presença do ícone da bandeja; validar este comportamento em testes Windows (pode exigir tratamento específico).
9. Evitar múltiplas instâncias via mutex de processo e, caso já exista, restaurar a janela da instância em execução.
10. Preservar acesso às configurações mesmo com janela oculta; monitoramento em segundo plano só quando necessário, evitando polling DDC/CI desnecessário.

## Segurança e testes

- Usar identificação física válida antes de `SetVCPFeature(0x60, valor)`.
- Separar leitura de `GetVCPFeature(0x60)` da leitura da string de capacidades; não deduzir suporte pela entrada atual.
- Se capacidades indisponíveis, registrar erro diagnóstico e não inventar botões/portas.
- Testar desligar e reconectar monitor, múltiplos monitores, suspensão/retomada, troca de input que corta sinal, duas instâncias, Explorer reiniciado e login do Windows.
- A implementação da UI/tray não deve degradar o recurso existente **Identificar telas**.

## Marco inicial

Entregar janela Slint + tray funcional com o menu **Abrir / Identificar telas / Sair** antes de migrar DDC/CI e a lista dinâmica de portas.
