"""OpenMonitor Switch - Windows desktop MVP."""
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
        self.title('OpenMonitor Switch — MVP 0.2')
        self.geometry('880x590')
        self.minsize(750, 450)
        self.widgets = []
        self.status = tk.StringVar(value='Pronto. Descubra os monitores para configurar.')
        top = ttk.Frame(self, padding=16)
        top.pack(fill='x')
        ttk.Label(top, text='OpenMonitor Switch', font=('Segoe UI', 17, 'bold')).pack(side='left')
        ttk.Button(top, text='Detectar monitores', command=self.scan).pack(side='right')
        ttk.Button(top, text='Identificar telas', command=self.identify_screens).pack(side='right', padx=8)
        ttk.Label(self, text='Configure a entrada de cada PC em cada monitor. Os códigos podem variar por modelo.',
                  padding=(16, 0)).pack(anchor='w')
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.list_frame = ttk.Frame(self.canvas, padding=16)
        self.list_frame.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.create_window((0, 0), window=self.list_frame, anchor='nw')
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(1, width=e.width))
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        bottom = ttk.Frame(self, padding=16)
        bottom.pack(side='bottom', fill='x')
        ttk.Button(bottom, text='Todos → PC A', command=lambda: self.switch_all('A')).pack(side='left', padx=(0, 8))
        ttk.Button(bottom, text='Todos → PC B', command=lambda: self.switch_all('B')).pack(side='left', padx=(0, 16))
        ttk.Label(bottom, textvariable=self.status, wraplength=450).pack(side='left', fill='x', expand=True)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(200, self.scan)

    def close(self):
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
            box = ttk.LabelFrame(self.list_frame, text=f'Monitor detectado {pos + 1}: {monitor.description}', padding=10)
            box.pack(fill='x', pady=6)
            ttk.Label(box, text=f'ID: {monitor.id} | VCP 0x60: ' +
                      (f'0x{monitor.current:02X} ({monitor.current})' if monitor.current is not None else 'não disponível'),
                      foreground='#555').grid(row=0, column=0, columnspan=8, sticky='w', pady=(0, 7))
            label = tk.StringVar(value=entry.get('label', monitor.description if monitor.description != 'Generic PnP Monitor' else f'Monitor {pos + 1}'))
            a = tk.StringVar(value=str(entry.get('a', 15)))
            b = tk.StringVar(value=str(entry.get('b', 17)))
            enabled = tk.BooleanVar(value=entry.get('enabled', True))
            ttk.Label(box, text='Nome:').grid(row=1, column=0, sticky='w')
            ttk.Entry(box, textvariable=label, width=23).grid(row=1, column=1, padx=5, sticky='w')
            ttk.Label(box, text='PC A:').grid(row=1, column=2)
            ttk.Entry(box, textvariable=a, width=7).grid(row=1, column=3, padx=5)
            ttk.Label(box, text='PC B:').grid(row=1, column=4)
            ttk.Entry(box, textvariable=b, width=7).grid(row=1, column=5, padx=5)
            ttk.Checkbutton(box, text='Ativo', variable=enabled).grid(row=1, column=6, padx=10)
            ttk.Button(box, text='Salvar', command=lambda m=monitor.id, l=label, av=a, bv=b, en=enabled:
                       self.save_one(m, l.get(), av.get(), bv.get(), en.get())).grid(row=2, column=1, pady=8)
            ttk.Button(box, text='→ PC A', command=lambda m=monitor.id: self.switch_one(m, 'A')).grid(row=2, column=3)
            ttk.Button(box, text='→ PC B', command=lambda m=monitor.id: self.switch_one(m, 'B')).grid(row=2, column=5)
            self.widgets.append((monitor.id, label, a, b, enabled))
        self.status.set(f'{len(monitors)} monitor(es) encontrado(s). Configuração: {CONFIG_PATH}')

    def identify_screens(self):
        """Identifica visualmente telas enumeradas sem trocar entradas de vídeo."""
        monitors = getattr(self, 'last_monitors', None)
        if not monitors:
            self.status.set('Detecte os monitores primeiro.')
            return
        shown, overlays = set(), []
        for monitor in monitors:
            if monitor.display in shown or not monitor.bounds:
                continue
            shown.add(monitor.display)
            left, top, right, bottom = monitor.bounds
            width, height = min(440, right - left), min(170, bottom - top)
            if width <= 0 or height <= 0:
                continue
            overlay = tk.Toplevel(self)
            overlay.withdraw()
            overlay.overrideredirect(True)
            frame = ttk.Frame(overlay, padding=12)
            frame.pack(fill='both', expand=True)
            ttk.Label(frame, text='DISPLAY' + monitor.display.split('DISPLAY')[-1],
                      font=('Segoe UI', 34, 'bold'), anchor='center').pack(fill='both', expand=True)
            ttk.Label(frame, text='OpenMonitor Switch - identificação visual',
                      anchor='center').pack(fill='x', pady=(0, 8))
            overlay.geometry(f'{width}x{height}+0+0')
            overlay.deiconify()
            overlay.update_idletasks()
            import ctypes
            # Coordenadas absolutas também funcionam em telas à esquerda da principal.
            from ctypes import wintypes
            set_window_pos = ctypes.windll.user32.SetWindowPos
            set_window_pos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
            set_window_pos.restype = wintypes.BOOL
            set_window_pos(
                overlay.winfo_id(), -1,
                left + (right - left - width) // 2,
                top + (bottom - top - height) // 2,
                width, height, 0x0040)
            overlays.append(overlay)
        for overlay in overlays:
            overlay.after(6000, overlay.destroy)
        self.status.set(f'Identificando {len(overlays)} tela(s) por 6 segundos.')

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
            errors = [r for r in results if not r['ok']]
            ok = len(results) - len(errors)
            self.status.set(f'PC {target}: {ok} comando(s) enviado(s), {len(errors)} erro(s).')
            if errors:
                messagebox.showwarning('Falhas de envio', '\n'.join(f"{r['id']}: {r['error']}" for r in errors))
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
