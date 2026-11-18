import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from backend import parse_code, source_name, source_option
from core import Controller


class FakeBackend:
    def __init__(self):
        self.calls = []

    def enumerate_monitors(self):
        return [SimpleNamespace(id=monitor_id, hardware_id=f'MONITOR\\\\{monitor_id}',
                                current=None) for monitor_id in ['a|0', 'b|0', 'dell|0', 'samsung|0']]

    def set_input(self, monitor_id, code):
        self.calls.append((monitor_id, code))
        return {'id': monitor_id, 'code': code, 'sent': True}


class Tests(unittest.TestCase):
    def test_codes(self):
        self.assertEqual(parse_code('0x11'), 17)
        self.assertEqual(parse_code('15'), 15)
        self.assertEqual(parse_code('DisplayPort (15)'), 15)
        self.assertEqual(parse_code('HDMI 2 (18)'), 18)
        self.assertEqual(parse_code('5'), 5)
        self.assertEqual(source_name(5), 'Código 5')
        self.assertEqual(source_name(15), 'DisplayPort')
        self.assertEqual(source_option(15), 'DisplayPort (15)')
        self.assertEqual(source_option(5), '5')
        with self.assertRaises(ValueError):
            parse_code('256')
        with self.assertRaises(ValueError):
            parse_code(True)

    def test_switch(self):
        with tempfile.TemporaryDirectory() as d:
            backend = FakeBackend()
            ctrl = Controller(Path(d) / 'config.json', backend)
            ctrl.scan()
            ctrl.register('a|0', 'Dell', '0x0F', '0x03')
            ctrl.register('b|0', 'Samsung', '17', '15')
            result = ctrl.switch_all('B')
            self.assertEqual(len(result), 2)
            self.assertEqual(backend.calls, [('a|0', 3), ('b|0', 15)])
            with self.assertRaises(ValueError):
                ctrl.switch_one('a|0', 'C')
            reload = Controller(Path(d) / 'config.json', backend)
            self.assertEqual(reload.config['monitors']['a|0']['b'], 3)

    def test_unconfigured_sources_are_safe(self):
        with tempfile.TemporaryDirectory() as d:
            backend = FakeBackend()
            ctrl = Controller(Path(d) / 'config.json', backend)
            ctrl.scan()
            ctrl.register('dell|0', 'Dell', 15, None)
            ctrl.register('samsung|0', 'Samsung', '', '')
            result = ctrl.switch_all('A')
            self.assertEqual(backend.calls, [('dell|0', 15)])
            self.assertEqual(len(result), 2)
            self.assertTrue(result[1]['skipped'])
            with self.assertRaisesRegex(ValueError, 'não configurada'):
                ctrl.switch_one('dell|0', 'B')
            self.assertIsNone(ctrl.config['monitors']['samsung|0']['a'])

    def test_reenumeration_and_noop(self):
        with tempfile.TemporaryDirectory() as d:
            backend = FakeBackend()
            ctrl = Controller(Path(d) / 'config.json', backend)
            ctrl.scan()
            ctrl.register('a|0', 'Dell', 15, 17)
            def changed():
                return [SimpleNamespace(id='a|0', hardware_id='MONITOR\\\\other',
                                        current=15)]
            backend.enumerate_monitors = changed
            with self.assertRaisesRegex(RuntimeError, 'alterou a associação'):
                ctrl.switch_one('a|0', 'B')
            self.assertEqual(backend.calls, [])
            backend.enumerate_monitors = lambda: [
                SimpleNamespace(id='a|0', hardware_id='MONITOR\\\\a|0', current=15)]
            result = ctrl.switch_one('a|0', 'A')
            self.assertTrue(result['unchanged'])
            self.assertEqual(backend.calls, [])

if __name__ == '__main__':
    unittest.main()
