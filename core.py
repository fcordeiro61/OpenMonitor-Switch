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


class Controller:
    def __init__(self, path=CONFIG_PATH, backend=None):
        self.path = Path(path)
        self.backend = backend
        self.lock = Lock()
        self.config = self._load()
        self._detected = {}

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
        monitors = self.backend.enumerate_monitors() if self.backend else enumerate_monitors()
        self._detected = {m.id: m for m in monitors}
        return monitors

    def register(self, monitor_id, label, pc_a, pc_b, enabled=True):
        a = None if pc_a is None or str(pc_a).strip() == '' else parse_code(pc_a)
        b = None if pc_b is None or str(pc_b).strip() == '' else parse_code(pc_b)
        with self.lock:
            previous = self.config['monitors'].get(monitor_id, {})
            detected = self._detected.get(monitor_id)
            hardware_id = previous.get('hardware_id') or getattr(detected, 'hardware_id', None)
            if previous.get('hardware_id') and detected and getattr(detected, 'hardware_id', None) and (
                    previous['hardware_id'].casefold() != detected.hardware_id.casefold()):
                raise RuntimeError('O monitor mudou de DISPLAY. Revise o mapeamento antes de salvar.')
            self.config['monitors'][monitor_id] = {
                'label': str(label).strip() or monitor_id,
                'a': a, 'b': b, 'enabled': bool(enabled),
                'hardware_id': hardware_id
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
            code = entry.get(target.lower())
            if code is None:
                raise ValueError(f'Entrada PC {target} não configurada: {entry.get("label", monitor_id)}')

            # Re-enumerate to ensure DISPLAYN still points to the same hardware.
            monitors = self.backend.enumerate_monitors() if self.backend else enumerate_monitors()
            actual = next((m for m in monitors if m.id == monitor_id), None)
            if actual is None:
                raise RuntimeError('Monitor indisponível; detecte novamente.')
            expected_id = entry.get('hardware_id')
            actual_id = getattr(actual, 'hardware_id', None)
            if not expected_id or not actual_id:
                raise RuntimeError('Identidade do monitor não confirmada. Detecte e salve novamente.')
            if expected_id.casefold() != actual_id.casefold():
                raise RuntimeError('O Windows alterou a associação DISPLAY/monitor. Detecte e salve novamente.')
            if getattr(actual, 'current', None) == code:
                return {'id': monitor_id, 'code': code, 'sent': False,
                        'unchanged': True, 'message': 'Entrada já selecionada'}
            return (self.backend.set_input(monitor_id, code) if self.backend
                    else set_input(monitor_id, code))

    def switch_input(self, monitor_id, value):
        """Select a discovered input without assigning it to PC A or PC B."""
        code = parse_code(value)
        with self.lock:
            detected = self._detected.get(monitor_id)
            if detected is None or not getattr(detected, 'hardware_id', None):
                raise RuntimeError('Detecte o monitor antes de selecionar uma entrada.')
            known = getattr(detected, 'supported_inputs', None)
            allowed = set(known or [])
            if detected.current is not None:
                allowed.add(detected.current)
            if code not in allowed:
                raise ValueError('Entrada não identificada nas capacidades deste monitor.')
            monitors = self.backend.enumerate_monitors() if self.backend else enumerate_monitors()
            actual = next((m for m in monitors if m.id == monitor_id), None)
            if (actual is None or not getattr(actual, 'hardware_id', None)
                    or actual.hardware_id.casefold() != detected.hardware_id.casefold()):
                raise RuntimeError('Associação física mudou. Detecte novamente.')
            if actual.current == code:
                return {'id': monitor_id, 'code': code, 'unchanged': True, 'sent': False}
            return (self.backend.set_input(monitor_id, code) if self.backend
                    else set_input(monitor_id, code))

    def switch_all(self, target):
        results = []
        for monitor_id, entry in list(self.config['monitors'].items()):
            if not entry.get('enabled', True):
                continue
            if entry.get(target.lower()) is None:
                results.append({'id': monitor_id, 'ok': False, 'skipped': True,
                                'error': f'PC {target} não configurado'})
                continue
            try:
                result = self.switch_one(monitor_id, target)
                results.append({'id': monitor_id, 'ok': True, 'result': result})
            except Exception as exc:
                results.append({'id': monitor_id, 'ok': False, 'error': str(exc)})
        return results
