"""OpenMonitor Switch - Windows desktop MVP."""
import sys
# Set DPI awareness before creating *any* Tk or Win32 windows. This keeps
# GetMonitorInfo positions and SetWindowPos coordinates in the same space.
if sys.platform == 'win32':
    import ctypes
    try:
        fn = ctypes.windll.user32.SetProcessDpiAwarenessContext
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = ctypes.c_bool
        fn(ctypes.c_void_p(-4 & ((1 << (ctypes.sizeof(ctypes.c_void_p)*8))-1)))
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass
import argparse
import concurrent.futures
import json
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from backend import SOURCE_CODES
from core import Controller, CONFIG_PATH
from api import serve


class Application(tk.Tk):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.title('OpenMonitor Switch — MVP 0.3.4')
        self.geometry('1040x720')
        self.minsize(650, 510)
        self.widgets = []
        self._overlays = []
        self.status = tk.StringVar(value='Pronto. Descubra os monitores para configurar.')
        style = ttk.Style(self)
        style.configure('Title.TLabel', font=('Segoe UI', 17, 'bold'))
        style.configure('Monitor.TLabelframe.Label', font=('Segoe UI', 11, 'bold'))
        style.configure('Action.TButton', padding=(11, 8))
        style.configure('ActivePC.TLabel', foreground='#0875DC',
                        font=('Segoe UI', 10, 'bold'))
        style.configure('IdlePC.TLabel', foreground='#767676',
                        font=('Segoe UI', 10))
        style.configure('UnknownPC.TLabel', foreground='#767676',
                        font=('Segoe UI', 9))
        header = ttk.Frame(self, padding=(18, 16, 18, 10))
        header.pack(fill='x')
        ttk.Label(header, text='OpenMonitor Switch', style='Title.TLabel').pack(anchor='w')
        tools = ttk.Frame(header)
        tools.pack(fill='x', pady=(12, 0))
        ttk.Button(tools, text='Detectar monitores', command=self.scan).pack(side='left', padx=(0, 8))
        ttk.Button(tools, text='Identificar telas', command=self.identify_screens).pack(side='left')
        ttk.Label(header, text='Configure os códigos de cada PC. A identificação não muda a entrada de vídeo.',
                  wraplength=900).pack(anchor='w', pady=(10, 0))
        actions = ttk.Frame(self, padding=(18, 9))
        actions.pack(side='bottom', fill='x')
        ttk.Button(actions, text='Todos → PC A', command=lambda: self.switch_all('A'),
                   style='Action.TButton').pack(side='left', padx=(0, 8))
        ttk.Button(actions, text='Todos → PC B', command=lambda: self.switch_all('B'),
                   style='Action.TButton').pack(side='left')
        ttk.Label(actions, textvariable=self.status, wraplength=470).pack(side='left', padx=(14, 0), fill='x', expand=True)
        middle = ttk.Frame(self)
        middle.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(middle, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(middle, orient='vertical', command=self.canvas.yview)
        self.list_frame = ttk.Frame(self.canvas, padding=(18, 4, 18, 16))
        self.list_frame.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas_window = self.canvas.create_window((0, 0), window=self.list_frame, anchor='nw')
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.canvas_window, width=e.width))
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        self.canvas.bind_all('<MouseWheel>', self._scroll_canvas)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(200, self.scan)

    def _scroll_canvas(self, event):
        if self.winfo_exists() and self.canvas.winfo_exists():
            self.canvas.yview_scroll(-int(event.delta / 120), 'units')

    def close(self):
        self.canvas.unbind_all('<MouseWheel>')
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.destroy()

    def task(self, func, success):
        self.status.set('Executando...')
        future = self.executor.submit(func)
        def check():
            if not self.winfo_exists():
                return
            if not future.done():
                self.after(100, check)
                return
            try:
                success(future.result())
            except Exception as exc:
                self.status.set(f'Erro: {exc}')
                messagebox.showerror('OpenMonitor Switch', str(exc))
        self.after(100, check)

    def scan(self):
        self.task(self.controller.scan, self.render)

    def render(self, monitors):
        for child in self.list_frame.winfo_children():
            child.destroy()
        self.widgets = []
        self.last_monitors = monitors
        if not monitors:
            ttk.Label(self.list_frame, text='Nenhum monitor físico detectado. Verifique DDC/CI e os cabos.').pack(anchor='w')
        for pos, monitor in enumerate(monitors):
            entry = self.controller.config['monitors'].get(monitor.id, {})
            if entry.get('hardware_id') and monitor.hardware_id and (
                    entry['hardware_id'].casefold() != monitor.hardware_id.casefold()):
                entry = {}
            name = monitor.description
            frame = ttk.LabelFrame(self.list_frame,
                  text=f'{monitor.display.split("DISPLAY")[-1]} — {name}', padding=12,
                  style='Monitor.TLabelframe')
            frame.pack(fill='x', pady=7)
            header_line = ttk.Frame(frame)
            header_line.pack(fill='x', pady=(0, 5))
            ttk.Label(header_line, text=monitor.description,
                      font=('Segoe UI', 11, 'bold')).pack(anchor='w')
            ttk.Label(frame, text=f'ID: {monitor.id}   |   VCP 0x60: ' +
                (f'0x{monitor.current:02X} ({monitor.current})'
                 if monitor.current is not None else 'não disponível'),
                foreground='#555').pack(anchor='w', pady=(0, 9))
            label = tk.StringVar(value=entry.get('label',
                name if name not in ('Generic PnP Monitor', 'Generic Non-PnP Monitor')
                else f'Monitor {pos + 1}'))
            a = tk.StringVar(value='' if entry.get('a') is None else str(entry['a']))
            b = tk.StringVar(value='' if entry.get('b') is None else str(entry['b']))
            enabled = tk.BooleanVar(value=entry.get('enabled', True))
            indicator = ttk.Frame(frame)
            indicator.pack(anchor='w', pady=(9, 0))
            ttk.Label(indicator, text='Entrada atual:').pack(side='left', padx=(0, 10))
            pc_a_status = ttk.Label(indicator, text='PC A', style='IdlePC.TLabel')
            pc_a_status.pack(side='left', padx=(0, 16))
            pc_b_status = ttk.Label(indicator, text='PC B', style='IdlePC.TLabel')
            pc_b_status.pack(side='left', padx=(0, 16))
            unknown_status = ttk.Label(indicator, text='', style='UnknownPC.TLabel')
            unknown_status.pack(side='left')

            def update_indicator(*_, source=monitor.current, av=a, bv=b,
                                 label_a=pc_a_status, label_b=pc_b_status,
                                 unknown=unknown_status):
                from backend import parse_code
                def value(variable):
                    try:
                        return parse_code(variable.get()) if variable.get().strip() else None
                    except ValueError:
                        return None
                ca, cb = value(av), value(bv)
                active_a = source is not None and ca is not None and source == ca
                active_b = source is not None and cb is not None and source == cb
                # The same VCP for both PCs is ambiguous: do not claim either is active.
                if active_a and active_b:
                    active_a = active_b = False
                    info = 'Ambíguo: entradas iguais'
                elif source is None:
                    info = 'Leitura indisponível'
                elif not active_a and not active_b:
                    info = ('Configure as entradas' if ca is None or cb is None
                            else f'Entrada atual: {source} (sem correspondência)')
                else:
                    info = ''
                label_a.configure(text=('● PC A' if active_a else '○ PC A'),
                                  style='ActivePC.TLabel' if active_a else 'IdlePC.TLabel')
                label_b.configure(text=('● PC B' if active_b else '○ PC B'),
                                  style='ActivePC.TLabel' if active_b else 'IdlePC.TLabel')
                unknown.configure(text=info)
            a.trace_add('write', update_indicator)
            b.trace_add('write', update_indicator)
            update_indicator()
            fields = ttk.Frame(frame)
            fields.pack(fill='x')
            title_row = ttk.Frame(fields)
            title_row.pack(fill='x')
            ttk.Label(title_row, text='Nome').pack(side='left')
            ttk.Entry(title_row, textvariable=label, width=36).pack(side='left', padx=(9, 0), fill='x', expand=True)
            ports = ttk.Frame(fields)
            ports.pack(fill='x', pady=(10, 0))
            ttk.Label(fields,
                      text='Entradas por monitor: informe o código VCP real (decimal ou 0xNN). '
                           'Não há portas padrão.',
                      foreground='#555').pack(anchor='w', pady=(6, 0))
            ttk.Label(ports, text='PC A').pack(side='left')
            ttk.Entry(ports, textvariable=a, width=7).pack(side='left', padx=(7, 18))
            ttk.Label(ports, text='PC B').pack(side='left')
            ttk.Entry(ports, textvariable=b, width=7).pack(side='left', padx=(7, 18))
            ttk.Checkbutton(ports, text='Ativo', variable=enabled).pack(side='left')
            buttons = ttk.Frame(frame)
            buttons.pack(anchor='w', pady=(12, 0))
            ttk.Button(buttons, text='Salvar', style='Action.TButton',
                       command=lambda m=monitor.id, l=label, av=a, bv=b, en=enabled:
                       self.save_one(m, l.get(), av.get(), bv.get(), en.get())).pack(side='left', padx=(0, 9))
            button_a = ttk.Button(buttons, text='→ PC A', style='Action.TButton',
                       command=lambda m=monitor.id: self.switch_one(m, 'A'))
            button_a.pack(side='left', padx=(0, 9))
            button_b = ttk.Button(buttons, text='→ PC B', style='Action.TButton',
                       command=lambda m=monitor.id: self.switch_one(m, 'B'))
            button_b.pack(side='left')
            def refresh_buttons(*_, av=a, bv=b, ba=button_a, bb=button_b):
                ba.configure(state='normal' if av.get().strip() else 'disabled')
                bb.configure(state='normal' if bv.get().strip() else 'disabled')
            a.trace_add('write', refresh_buttons)
            b.trace_add('write', refresh_buttons)
            refresh_buttons()
            self.widgets.append((monitor.id, label, a, b, enabled))
        self.status.set(f'{len(monitors)} monitor(es) encontrado(s). Configuração: {CONFIG_PATH}')

    def identify_screens(self):
        """Show the GDI DISPLAY identifier on each matching physical screen."""
        import ctypes
        from ctypes import wintypes
        from backend import _enumerate

        if not getattr(self, 'last_monitors', None):
            self.status.set('Detecte os monitores primeiro.')
            return

        for overlay in self._overlays:
            if overlay.winfo_exists():
                overlay.destroy()
        self._overlays = []

        user32 = ctypes.WinDLL('user32', use_last_error=True)
        get_ancestor = user32.GetAncestor
        get_ancestor.argtypes = [wintypes.HWND, wintypes.UINT]
        get_ancestor.restype = wintypes.HWND
        setpos = user32.SetWindowPos
        setpos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                           ctypes.c_int, ctypes.c_int, wintypes.UINT]
        setpos.restype = wintypes.BOOL
        monitor_from_window = user32.MonitorFromWindow
        monitor_from_window.argtypes = [wintypes.HWND, wintypes.DWORD]
        monitor_from_window.restype = wintypes.HMONITOR

        # Tkinter's winfo_id() can refer to a child HWND. Only the real
        # top-level HWND uses virtual-desktop coordinates in SetWindowPos.
        native_displays = {
            display: (handle.value if hasattr(handle, 'value') else int(handle))
            for handle, display, _bounds in _enumerate()
        }
        shown = set()
        failures = []
        for monitor in self.last_monitors:
            if monitor.display in shown or not monitor.bounds:
                continue
            shown.add(monitor.display)
            left, top, right, bottom = monitor.bounds
            width = min(325, right - left - 30)
            height = min(158, bottom - top - 30)
            if width < 100 or height < 80:
                failures.append(f'{monitor.display}: dimensões inválidas')
                continue

            overlay = tk.Toplevel(self)
            overlay.withdraw()
            overlay.overrideredirect(True)
            panel = tk.Frame(overlay, bg='#163C68', padx=14, pady=10)
            panel.pack(fill='both', expand=True)
            tk.Label(panel, text=monitor.display.rsplit('\\', 1)[-1],
                     bg='#163C68', fg='#FFFFFF',
                     font=('Segoe UI', 21, 'bold'),
                     anchor='center').pack(fill='both', expand=True)
            tk.Label(panel, text=monitor.description, bg='#163C68',
                     fg='#E5F1FF', font=('Segoe UI', 10),
                     anchor='center').pack(fill='x')
            # Status derived from the actual VCP value and saved mapping.
            from backend import parse_code
            entry = self.controller.config['monitors'].get(monitor.id, {})
            def configured_code(key):
                raw = entry.get(key)
                try:
                    return parse_code(raw) if raw is not None and str(raw).strip() else None
                except (ValueError, TypeError):
                    return None
            code_a, code_b = configured_code('a'), configured_code('b')
            active = None
            if monitor.current is not None and code_a != code_b:
                if code_a is not None and monitor.current == code_a:
                    active = 'A'
                elif code_b is not None and monitor.current == code_b:
                    active = 'B'
            statuses = tk.Frame(panel, bg='#163C68')
            statuses.pack(pady=(6, 0))
            for pc in ('A', 'B'):
                selected = pc == active
                tk.Label(statuses, text=('● ' if selected else '○ ') + 'PC ' + pc,
                         bg='#163C68', fg='#42A5FF' if selected else '#B3C4D5',
                         font=('Segoe UI', 11, 'bold' if selected else 'normal'),
                         padx=12).pack(side='left')
            overlay.geometry(f'{width}x{height}+0+0')
            overlay.deiconify()
            overlay.update_idletasks()

            # GA_ROOT=2: outer window, not Tk's embedded child HWND.
            hwnd = get_ancestor(overlay.winfo_id(), 2)
            if not hwnd:
                overlay.destroy()
                failures.append(f'{monitor.display}: HWND indisponível')
                continue
            x = right - width - 20
            y = top + 20
            # SWP_SHOWWINDOW=0x0040, keeps the label on top while visible.
            ok = setpos(hwnd, -1, x, y, width, height, 0x0040)
            expected = native_displays.get(monitor.display)
            actual = int(monitor_from_window(hwnd, 2)) if ok else None
            if not ok or actual != expected:
                overlay.destroy()
                failures.append(f'{monitor.display}: posição não confirmada')
                continue
            overlay.after(8000, overlay.destroy)
            self._overlays.append(overlay)

        self.status.set(f'Identificação: {len(self._overlays)}/{len(shown)} tela(s) exibida(s).' +
                        (' Falhas: ' + '; '.join(failures) if failures else ''))

    def save_one(self, monitor_id, label, a, b, enabled):
        try:
            self.controller.register(monitor_id, label, a, b, enabled)
            self.status.set(f'Salvo: {label}. Identidade física vinculada.')
        except Exception as exc:
            messagebox.showerror('Erro na configuração', str(exc))

    def save_all(self):
        for monitor_id, label, a, b, enabled in self.widgets:
            self.controller.register(monitor_id, label.get(), a.get(), b.get(), enabled.get())

    def _after_switch(self, message):
        self.status.set(message)
        self.scan()

    def switch_one(self, monitor_id, target):
        try:
            self.save_all()
        except Exception as exc:
            messagebox.showerror('Configuração inválida', str(exc))
            return
        self.task(lambda: self.controller.switch_one(monitor_id, target),
                  lambda result: self._after_switch(
                      (f'{monitor_id}: entrada já selecionada, nenhum comando enviado.'
                       if result.get('unchanged') else
                       f'Comando enviado ao monitor {monitor_id}: PC {target}. Estado será relido.')))

    def switch_all(self, target):
        try:
            self.save_all()
        except Exception as exc:
            messagebox.showerror('Configuração inválida', str(exc))
            return
        def success(results):
            skipped = [r for r in results if r.get('skipped')]
            errors = [r for r in results if not r['ok'] and not r.get('skipped')]
            ok = sum(bool(r['ok']) for r in results)
            self.status.set(f'PC {target}: {ok} enviado(s), {len(skipped)} pendente(s), {len(errors)} erro(s).')
            if errors:
                messagebox.showwarning('Falhas de envio',
                    '\n'.join(f"{r['id']}: {r['error']}" for r in errors))
        self.task(lambda: self.controller.switch_all(target),
                  lambda results: (success(results), self.scan()))


def main():
    parser = argparse.ArgumentParser(description='OpenMonitor Switch')
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('scan', help='Lista os monitores e valores de VCP 0x60')
    single = sub.add_parser('switch', help='Troca um monitor configurado')
    single.add_argument('monitor_id')
    single.add_argument('target', choices=['A', 'B'])
    allp = sub.add_parser('profile', help='Troca todos os monitores configurados')
    allp.add_argument('target', choices=['A', 'B'])
    api = sub.add_parser('api', help='Inicia API HTTP opcional; default localhost')
    api.add_argument('--host', default='127.0.0.1')
    api.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    controller = Controller()
    if args.command == 'scan':
        print(json.dumps([m.to_dict() for m in controller.scan()], ensure_ascii=False, indent=2))
    elif args.command == 'switch':
        print(controller.switch_one(args.monitor_id, args.target))
    elif args.command == 'profile':
        results = controller.switch_all(args.target)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        if any(not r['ok'] for r in results):
            sys.exit(1)
    elif args.command == 'api':
        token = controller.config['api']['token']
        serve(controller, args.host, args.port, token)
    else:
        Application(controller).mainloop()

if __name__ == '__main__':
    main()
