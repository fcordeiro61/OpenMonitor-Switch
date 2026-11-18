# OpenMonitor Switch — MVP 0.3.4

Aplicativo Windows, open-source (MIT), para alterar a entrada de vídeo de monitores físicos usando DDC/CI e o comando VCP `0x60`. Interface Tkinter e API HTTP opcional. **Sem bibliotecas de terceiros.**

## Requisitos

- Windows 10/11 com Python 3.10 ou superior instalado (incluindo Tcl/Tk).
- DDC/CI habilitado no menu dos monitores.
- Um caminho físico funcional entre a GPU, cabo/adaptador e o monitor que permita o DDC/CI.
- Teste bem-sucedido de troca de entrada VCP `0x60` (você já confirmou essa possibilidade).

## Como iniciar

Abra o PowerShell na pasta extraída:

```powershell
py app.py
```

Ou dê duplo clique em `iniciar.bat`.

1. Clique em **Detectar monitores**.
2. Clique em **Identificar telas**: por 8 segundos cada tela mostra seu identificador `DISPLAYN` em um painel azul no **canto superior direito**, sem alterar a fonte de vídeo. **A ordem de detecção não é necessariamente a ordem física da sua mesa!**
3. Associe os identificadores aos modelos físicos e informe nomes como Dell P2314H, Samsung LS27AG32X e Samsung LT27T35. O aplicativo tenta ler o nome por `EnumDisplayDevicesW` e, quando possível, pelo EDID no Registro do Windows. Se a identificação continuar genérica, o programa **não inventa** o modelo.
4. Configure para cada monitor os códigos de fonte de **PC A** e **PC B**.
5. Clique **Salvar** e experimente **→ PC A** ou **→ PC B** por monitor.
6. Depois de validar os monitores detectados, use **Todos → PC A/B**. O aplicativo enumera automaticamente quantas telas estão conectadas; não há parâmetro de quantidade.

**Nenhuma entrada é pré-configurada.** Os campos PC A e PC B começam vazios; o programa não usa o valor VCP atual como suposição de porta. Apenas entradas explicitamente preenchidas e salvas podem receber comandos. Perfis coletivos ignoram entradas vazias e informam quantas foram ignoradas. A configuração é salva automaticamente em `%APPDATA%\OpenMonitorSwitch\config.json`.

### Códigos VCP 0x60 comuns (MCCS)

**São exemplos, não valores fixos nem todas as possibilidades.** Os campos PC A e PC B aceitam qualquer código de 0 a 255, em decimal (`5`, `15`, `17`) ou hexadecimal (`0x05`, `0x0F`, `0x11`). Cada monitor pode ter várias entradas, e cada PC é associado apenas à entrada física correspondente. O VCP atualmente lido não identifica sozinho qual PC está conectado. A lista de entradas suportadas pode variar por modelo e firmware.

| Porta | Hexadecimal | Decimal |
|---|---:|---:|
| VGA | 0x01 | 1 |
| DVI | 0x03 | 3 |
| DisplayPort | 0x0F | 15 |
| HDMI 1 | 0x11 | 17 |
| HDMI 2 | 0x12 | 18 |

**Importante:** fabricantes podem implementar códigos diferentes ou ignorar certas solicitações. Use os códigos que funcionaram em seus testes; a API pode aceitar o comando sem o monitor efetivamente mudar de fonte. O programa não consegue validar visualmente a mudança.

### Entradas físicas dos seus modelos (a confirmar conforme variante exata)

- **Dell P2314H:** VGA, DVI-D, DisplayPort. *Não possui HDMI físico nativo*; HDMI→DVI depende de cabo/adaptador.
- **Samsung LS27AG32X:** HDMI e DisplayPort.
- **Samsung LT27T35 / série T350:** HDMI e VGA (D-Sub).

Cada monitor pode ter um mapeamento de fonte diferente. A quantidade de monitores não é fixa.

## Linha de comando

```powershell
py app.py scan   # detecta automaticamente todos os monitores
py -3 app.py profile A
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
