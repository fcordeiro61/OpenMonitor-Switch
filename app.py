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
        self.title('OpenMonitor Switch — MVP 0.3')
        self.geometry('1040x720')
        self.minsize(650, 510)
        self.widgets = []
        self._overlays = []
        self.status = tk.StringVar(value='Pronto. Descubra os monitores para configurar.')
        style = ttk.Style(self)
        style.configure('Title.TLabel', font=('Segoe UI', 17, 'bold'))
        style.configure('Monitor.TLabelframe.Label', font=('Segoe UI', 11, 'bold'))
        style.configure('Action.TButton', padding=(11, 8))
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
            name = monitor.description
            frame = ttk.LabelFrame(self.list_frame,
                  text=f'{monitor.display.split("DISPLAY")[-1]} — {name}', padding=12,
                  style='Monitor.TLabelframe')
            frame.pack(fill='x', pady=7)
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
            fields = ttk.Frame(frame)
            fields.pack(fill='x')
            title_row = ttk.Frame(fields)
            title_row.pack(fill='x')
            ttk.Label(title_row, text='Nome').pack(side='left')
            ttk.Entry(title_row, textvariable=label, width=36).pack(side='left', padx=(9, 0), fill='x', expand=True)
            ports = ttk.Frame(fields)
            ports.pack(fill='x', pady=(10, 0))
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
            def refresh_buttons(*_):
                button_a.configure(state='normal' if a.get().strip() else 'disabled')
                button_b.configure(state='normal' if b.get().strip() else 'disabled')
            a.trace_add('write', refresh_buttons)
            b.trace_add('write', refresh_buttons)
            refresh_buttons()
            self.widgets.append((monitor.id, label, a, b, enabled))
        self.status.set(f'{len(monitors)} monitor(es) encontrado(s). Configuração: {CONFIG_PATH}')

    def identify_screens(self):
        """Show DISPLAY labels on matching physical screens, never guessed."""
        import ctypes
        from ctypes import wintypes
        if not getattr(self, 'last_monitors', None):
            self.status.set('Detecte os monitores primeiro.')
            return
        for overlay in self._overlays:
            if overlay.winfo_exists():
                overlay.destroy()
        self._overlays = []
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        setpos = user32.SetWindowPos
        setpos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                           ctypes.c_int, ctypes.c_int, wintypes.UINT]
        setpos.restype = wintypes.BOOL
        monitor_from_window = user32.MonitorFromWindow
        monitor_from_window.argtypes = [wintypes.HWND, wintypes.DWORD]
        monitor_from_window.restype = wintypes.HMONITOR
        from backend import _enumerate
        display_handles = {display: (hmon.value if hasattr(hmon, 'value') else int(hmon))
                           for hmon, display, bounds in _enumerate()}
        seen = set()
        failed = []
        for monitor in self.last_monitors:
            if monitor.display in seen or not monitor.bounds:
                continue
            seen.add(monitor.display)
            left, top, right, bottom = monitor.bounds
            width, height = min(430, right - left), min(170, bottom - top)
            if width <= 0 or height <= 0:
                continue
            overlay = tk.Toplevel(self)
            overlay.withdraw()
            overlay.overrideredirect(True)
            panel = ttk.Frame(overlay, padding=20)
            panel.pack(fill='both', expand=True)
            identifier = monitor.display.rsplit('DISPLAY', 1)[-1]
            ttk.Label(panel, text=f'DISPLAY{identifier}',
                      font=('Segoe UI', 30, 'bold'), anchor='center').pack(fill='both', expand=True)
            ttk.Label(panel, text=monitor.description,
                      font=('Segoe UI', 11), anchor='center').pack(fill='x')
            overlay.geometry(f'{width}x{height}+0+0')
            overlay.deiconify()
            overlay.update_idletasks()
            x = left + (right - left - width) // 2
            y = top + (bottom - top - height) // 2
            ok = setpos(overlay.winfo_id(), -1, x, y, width, height, 0x0040)
            overlay.update_idletasks()
            actual = int(monitor_from_window(overlay.winfo_id(), 2))
            expected = display_handles.get(monitor.display)
            if not ok or expected != actual:
                overlay.destroy()
                failed.append(monitor.display)
                continue
            overlay.after(7000, overlay.destroy)
            self._overlays.append(overlay)
        self.status.set(f'Identificação: {len(self._overlays)} tela(s).' +
                        (f' Não foi possível posicionar: {", ".join(failed)}.' if failed else ''))

    def save_one(self, monitor_id, label, a, b, enabled):
        try:
            self.controller.register(monitor_id, label, a, b, enabled)
            self.status.set(f'Salvo: {label}')
        except Exception as exc:
            messagebox.showerror('Erro na configuração', str(exc))

    def save_all(self):
        for monitor_id, label, a, b, enabled in self.widgets:
            self.controller.register(monitor_id, label.get(), a.get(), b.get(), enabled.get())

    def switch_one(self, monitor_id, target):
        try:
            self.save_all()
        except Exception as exc:
            messagebox.showerror('Configuração inválida', str(exc))
            return
        self.task(lambda: self.controller.switch_one(monitor_id, target),
                  lambda result: self.status.set(f'Comando enviado ao monitor {monitor_id}: PC {target}. Sem confirmação visual.'))

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
        self.task(lambda: self.controller.switch_all(target), success)


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
