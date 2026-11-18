# OpenMonitor Switch — MVP 0.4.3

Aplicativo Windows, open-source (MIT), para alterar a entrada de vídeo de monitores físicos usando DDC/CI e o comando VCP `0x60`. Interface Tkinter e API HTTP opcional. **Sem bibliotecas de terceiros.**

## Requisitos

- Windows 10/11 com Python 3.10 ou superior instalado (incluindo Tcl/Tk).
- DDC/CI habilitado no menu dos monitores.
- Um caminho físico funcional entre a GPU, cabo/adaptador e o monitor que permita o DDC/CI.
- Teste bem-sucedido de troca de entrada VCP `0x60` (você já confirmou essa possibilidade).

## Como iniciar

```cmd
py app.py
```

1. Clique em **Detectar monitores** para consultar os dispositivos por DDC/CI.
2. As entradas anunciadas por cada monitor em `vcp(60(...))` aparecem como botões clicáveis. A entrada atual fica azul quando coincidir com um código anunciado.
3. Clique em uma entrada e confirme para enviar o comando. Essa operação pode interromper o vídeo; teste com acesso ao menu físico.

A interface **não exibe mais** campos de Nome, PC A, PC B, Ativo, Salvar, nem comandos globais de troca por PC. O aplicativo não pré-configura portas. A função **Identificar telas** continua mostrando o identificador no canto superior direito da tela.

Se o firmware não anunciar capacidades, a interface mostrará esse limite e não criará botões fictícios. O comando `py app.py scan` agora apresenta `capabilities_raw` (resposta textual original do monitor), `capabilities_error` e `supported_inputs` para diagnóstico. A API nativa do Windows faz até duas tentativas de leitura em caso de falha, sem enviar comandos de troca. O valor VCP lido é mostrado separadamente, mas não prova que seja uma porta suportada.

## Linha de comando

```powershell
py app.py scan   # detecta automaticamente todos os monitores
py app.py profile A
py -3 app.py profile B
py -3 app.py switch '\\.\DISPLAY1|0' A
```

Copie o ID exato retornado por `scan` (ou do arquivo de configuração). IDs são **locais a cada Windows** e podem mudar quando cabos, adaptadores ou disposição das telas mudarem. Reconfigure quando necessário.

## API HTTP opcional

A API serve para automações e futura comunicação entre os PCs. Por segurança **não é iniciada automaticamente**.

```powershell
py -3 app.py api
```

Por padrão só recebe conexões do mesmo computador (`127.0.0.1:8765`). No arquivo de configuração (`%APPDATA%\OpenMonitorSwitch\config.json`) há um token gerado automaticamente em `api.token`.

Exemplo PowerShell:

```powershell
$config = Get-Content "$env:APPDATA\OpenMonitorSwitch\config.json" | ConvertFrom-Json
$headers = @{ Authorization = "Bearer $($config.api.token)" }
Invoke-RestMethod http://127.0.0.1:8765/api/monitors -Headers $headers
Invoke-RestMethod http://127.0.0.1:8765/api/profile -Method POST -Headers $headers -ContentType 'application/json' -Body '{"target":"B"}'
```

Para acesso a partir do outro PC, inicie manualmente com `py -3 app.py api --host 0.0.0.0`, libere a porta **somente na rede privada e para o IP do outro computador**, configure o token de forma segura, e evite redes públicas. **HTTP não tem criptografia**: não encaminhe a API à internet. Considere uma VPN ou autenticação TLS antes do uso em redes não confiáveis.

### Rotas

- `GET /api/monitors`: descoberta com estado VCP reportado.
- `POST /api/switch`: `{"monitor_id":"ID_LOCAL","target":"A"}`.
- `POST /api/profile`: `{"target":"B"}`.

Todas exigem o header `Authorization: Bearer TOKEN`.

## Proteção contra troca no monitor errado

Antes de enviar VCP 0x60, o aplicativo relê a lista de monitores e confere o hardware ID associado ao `DISPLAYN`. Quando a identificação muda, a troca é bloqueada. O usuário deve detectar, revisar e salvar novamente. Um pedido para a entrada já ativa não envia comando (evita piscadas desnecessárias). Configurações existentes sem `hardware_id` precisam ser salvas novamente com o monitor detectado. Esse mecanismo reduz, mas não elimina, possíveis inconsistências de controladores DDC/CI.

## Limitações importantes (especialmente dois PCs)

- Alterar a entrada para o outro PC **pode cortar a comunicação DDC/CI** com o PC original.
- Dois agentes Windows não garantem reversão: a troca de volta depende de **pelo menos um dos PCs conseguir emitir o comando DDC/CI ao monitor naquele estado**. Teste cada sentido com **cada monitor**.
- Um monitor pode desaparecer da enumeração do Windows depois da troca de entrada. Nesse caso, o programa mostra a falha e não tenta alternar monitores por índice automaticamente.
- `GetVCPFeatureAndVCPFeatureReply` pode falhar mesmo quando a escrita VCP funciona em um modelo.
- Não implementa KVM de teclado/mouse, nem comuta sinais por software: somente controla o seletor de entrada do hardware.
- Um monitor que não expõe DDC/CI pela porta/cabo atual pode exigir troca manual ou um switch HDMI/DP externo.
- IDs por `\\.\DISPLAYN|índice` são temporários por configuração Windows; antes do uso definitivo vamos implementar associação persistente com EDID/serial.

## Entradas nomeadas e destaque da porta ativa

Cada monitor mostra etiquetas com os nomes comuns **VGA, DVI, DisplayPort, HDMI 1, HDMI 2**. Quando a leitura VCP 0x60 corresponde a um desses códigos, a etiqueta fica **azul**. Valores diferentes aparecem como **Código N**, sem identificação falsa (por exemplo, leitura 5 exibe Código 5). A identificação no canto superior direito também mostra a entrada atual. Os nomes comuns são apenas referência; não demonstram que o monitor possui todas essas conexões físicas.

A seleção de PC A e PC B usa listas não editáveis contendo apenas códigos anunciados pelo DDC/CI. **Nenhuma entrada é atribuída automaticamente**.

## Descoberta automática das entradas por DDC/CI

O comando **Detectar monitores** consulta a API nativa do Windows `GetCapabilitiesStringLength` e `CapabilitiesRequestAndCapabilitiesReply` para obter a `Capabilities String` DDC/CI de cada monitor e examinar os valores anunciados em `vcp(60(...))`. Mostra botões **clicáveis somente para os códigos anunciados**. A entrada atual é indicada separadamente; se seu valor não estiver anunciado nas capacidades, não se torna um botão nem é considerada porta confirmada. Cada clique solicita confirmação antes de enviar VCP 0x60; não atribui a porta automaticamente ao PC A ou PC B.

Não existem listas fixas de portas por monitor. Quando o dispositivo não fornece capacidades, mostra a entrada atual, se disponível, **mas não oferece portas nem permite configurar PC A/PC B**. A descoberta deve vir exclusivamente do DDC/CI. A lista declarada pelo firmware **não é uma API de inventário físico de conectores** e pode estar incorreta; um código não padrão como `5` permanece `Código 5` até ser identificado com segurança.

**Cuidado ao experimentar:** selecionar uma entrada pode causar perda do sinal e impedir novas solicitações DDC/CI a partir deste PC. Teste individualmente, com acesso ao menu físico do monitor para recuperação. Os controles `Todos → PC A/B` não devem ser usados antes de validar as portas de cada monitor.

## Estado visual da entrada

Abaixo do nome de cada monitor na interface e dentro do painel de identificação no canto superior direito, aparecem PC A / PC B. Ao detectar monitores, o aplicativo compara o VCP 0x60 lido com os códigos **explicitamente configurados** de PC A e PC B. O PC correspondente recebe um indicador **azul**. Sem correspondência (ou quando ambos os PCs possuem o mesmo código), o estado aparece como pendente/ambíguo: o aplicativo não presume o PC ativo. Depois de uma troca, faz nova leitura para atualizar o indicador, que depende de resposta DDC/CI do monitor.

## Configuração parcial

Cada monitor detectado aparece com o modelo EDID, sem supor quais portas cada computador utiliza. Se uma configuração antiga já tiver códigos salvos, eles serão preservados; remova-os pela interface ou limpe o arquivo de configuração se quiser começar do zero. Não confunda o valor de VCP lido com o mapeamento do PC A/B.

## Próximas versões

- v0.2.1: identificação visual com verificação do monitor real, ajuste de DPI, leitura do modelo pelo Windows/EDID e layout reorganizado para não cortar botões.
- v0.3: sem pré-configuração de entradas, suporte a campos vazios e bloqueio de envio sem configuração.
- Futuro: identificação persistente por EDID, bandeja, hotkeys e testes de ida/volta por monitor.
- v0.3: agentes nos dois PCs com recuperação/fallback e orquestração segura.
- v1.0: UI Tauri/Rust, empacotamento EXE, inicialização automática e instalador.

## Fontes técnicas

- Microsoft: https://learn.microsoft.com/en-us/windows/win32/monitor/using-the-low-level-monitor-configuration-functions
- Microsoft: https://learn.microsoft.com/en-us/windows/win32/api/lowlevelmonitorconfigurationapi/nf-lowlevelmonitorconfigurationapi-setvcpfeature
- Dell: https://dl.dell.com/manuals/all-products/esuprt_display_projector/esuprt_Display/dell-p2314h_setup%20guide_en-us.pdf
- Samsung G3: https://www.manualslib.com/manual/3220252/Samsung-S27ag32-Series.html
- Samsung T350: https://www.samsung.com/br/monitors/flat/t35f-27-inch-ips-fhd-1080p-freesync-lf27t350fhlmzd/
