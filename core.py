"""Local settings and profile switching."""
from __future__ import annotations
import json
import os
import secrets
from pathlib import Path
from threading import Lock
from backend import enumerate_monitors, set_input, parse_code

APP_DIR = Path(os.environ.get('APPDATA', str(Path.home()))) / 'OpenMonitorSwitch'
CONFIG_PATH = APP_DIR / 'config.json'
DEFAULT_MODELS = ['Dell P2314H', 'Samsung LS27AG32X', 'Samsung LT27T35']


class Controller:
    def __init__(self, path=CONFIG_PATH, backend=None):
        self.path = Path(path)
        self.backend = backend
        self.lock = Lock()
        self.config = self._load()

    def _load(self):
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not isinstance(data.get('monitors', {}), dict):
                raise ValueError('Configuração inválida')
            return data
        return {'monitors': {}, 'api': {'enabled': False, 'host': '127.0.0.1',
                'port': 8765, 'token': secrets.token_hex(24)}}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.config, indent=2, ensure_ascii=False), encoding='utf-8')
        temp.replace(self.path)

    def scan(self):
        return (self.backend.enumerate_monitors() if self.backend else enumerate_monitors())

    def register(self, monitor_id, label, pc_a, pc_b, enabled=True):
        a, b = parse_code(pc_a), parse_code(pc_b)
        with self.lock:
            self.config['monitors'][monitor_id] = {
                'label': str(label).strip() or monitor_id,
                'a': a, 'b': b, 'enabled': bool(enabled)
            }
            self.save()

    def switch_one(self, monitor_id, target):
        target = target.upper()
        if target not in ('A', 'B'):
            raise ValueError('Destino deve ser A ou B')
        with self.lock:
            entry = self.config['monitors'].get(monitor_id)
            if entry is None or not entry.get('enabled', True):
                raise ValueError('Monitor não configurado ou desativado')
            code = entry[target.lower()]
            return (self.backend.set_input(monitor_id, code) if self.backend
                    else set_input(monitor_id, code))

    def switch_all(self, target):
        results = []
        for monitor_id, entry in list(self.config['monitors'].items()):
            if not entry.get('enabled', True):
                continue
            try:
                result = self.switch_one(monitor_id, target)
                results.append({'id': monitor_id, 'ok': True, 'result': result})
            except Exception as exc:
                results.append({'id': monitor_id, 'ok': False, 'error': str(exc)})
        return results
