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
from backend import SOURCE_CODES, source_name
from core import Controller, CONFIG_PATH
from api import serve


class Application(tk.Tk):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.title('OpenMonitor Switch — MVP 0.4.3')
        self.geometry('1040x720')
        self.minsize(650, 510)
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
        actions = ttk.Frame(self, padding=(18, 9))
        actions.pack(side='bottom', fill='x')
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
                foreground='#555').pack(anchor='w', pady=(0, 5))
            # Strictly list only VCP 0x60 values advertised by the firmware.
            # The current value is observed, NOT proof of selectable capability.
            supported = list(monitor.supported_inputs or [])
            source_row = ttk.Frame(frame)
            source_row.pack(anchor='w', pady=(0, 7))
            ttk.Label(source_row, text='Entradas detectadas:').pack(side='left', padx=(0, 8))
            if supported:
                for code in supported:
                    is_active = monitor.current == code
                    title = source_name(code)
                    if code not in SOURCE_CODES.values():
                        title = f'Código {code} (0x{code:02X})'
                    tk.Button(source_row, text=('● ' if is_active else '') + title,
                              bg='#0875DC' if is_active else '#E9EDF2',
                              fg='white' if is_active else '#26384B',
                              activebackground='#1B7BD0',
                              relief='flat', cursor='hand2', padx=10, pady=5,
                              font=('Segoe UI', 9, 'bold' if is_active else 'normal'),
                              command=lambda mid=monitor.id, val=code, title=title:
                                  self.choose_input(mid, val, title)
                              ).pack(side='left', padx=(0, 5))
            else:
                ttk.Label(source_row, text='Nenhuma entrada informada via DDC/CI.').pack(side='left')
            ttk.Label(frame,
                      text=('Entradas anunciadas pelo firmware via DDC/CI.'
                            if monitor.supported_inputs else
                            'Nenhuma entrada anunciada via DDC/CI.'),
                      foreground='#666').pack(anchor='w', pady=(0, 7))
            if monitor.capabilities_error:
                ttk.Label(frame, text='Diagnóstico: ' + monitor.capabilities_error,
                          foreground='#B3561B', wraplength=900).pack(anchor='w', pady=(0, 7))
            if monitor.current is not None and monitor.current not in supported:
                ttk.Label(frame, text=f'Leitura atual 0x{monitor.current:02X}: '
                          'valor não anunciado nas capacidades; não é uma porta confirmada.',
                          foreground='#9A6013').pack(anchor='w', pady=(0, 6))
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
            height = min(186, bottom - top - 30)
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
            tk.Label(panel, text='Entrada ativa: ' + source_name(monitor.current),
                     bg='#163C68', fg='#FFFFFF',
                     font=('Segoe UI', 10, 'bold')).pack(pady=(4, 0))
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

    def choose_input(self, monitor_id, code, title):
        if not messagebox.askyesno(
                'Confirmar troca de entrada',
                f'Selecionar {title} no monitor {monitor_id}?\n\n'
                'A tela pode perder o sinal. Isso não altera a associação PC A/PC B.'):
            return
        self.task(lambda: self.controller.switch_input(monitor_id, code),
                  lambda result: self._after_switch(
                      'Entrada já estava selecionada.' if result.get('unchanged')
                      else f'Comando enviado: {title} no monitor {monitor_id}.'))

    def _after_switch(self, message):
        self.status.set(message)
        self.scan()

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
