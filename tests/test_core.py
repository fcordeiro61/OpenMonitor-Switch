import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from backend import parse_code, source_name, source_option, parse_input_capabilities
from core import Controller


class FakeBackend:
    def __init__(self):
        self.calls = []

    def enumerate_monitors(self):
        return [SimpleNamespace(id=monitor_id, hardware_id=f'MONITOR\\\\{monitor_id}',
                                current=None, supported_inputs=[3, 15, 17]) for monitor_id in ['a|0', 'b|0', 'dell|0', 'samsung|0']]

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

    def test_monitor_capabilities_parser(self):
        raw = '(prot(monitor)type(LCD)model(TEST)vcp(10 12 60(01 03 0F 11) D6(01 04)))'
        self.assertEqual(parse_input_capabilities(raw), [1, 3, 15, 17])
        self.assertEqual(parse_input_capabilities('(vcp(60(05 0F)))'), [5, 15])
        self.assertEqual(parse_input_capabilities('(prot(monitor)vcp(60(01 11)))'), [1, 17])
        self.assertEqual(parse_input_capabilities('(VCP(60(03 0f)))'), [3, 15])
        self.assertEqual(parse_input_capabilities('(vcp(60(05 1B 20 FF)))'), [5, 27, 32, 255])
        self.assertIsNone(parse_input_capabilities('(vcp(10 12 60))'))
        self.assertIsNone(parse_input_capabilities('(vcp(10 12))'))

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

    def test_direct_input_requires_observed_or_advertised_code(self):
        with tempfile.TemporaryDirectory() as d:
            backend = FakeBackend()
            ctrl = Controller(Path(d) / 'config.json', backend)
            def detected():
                return [SimpleNamespace(id='a|0', hardware_id='MONITOR\\\\a|0',
                                        current=15, supported_inputs=[3, 15])]
            backend.enumerate_monitors = detected
            ctrl.scan()
            result = ctrl.switch_input('a|0', 3)
            self.assertEqual(result['code'], 3)
            with self.assertRaisesRegex(ValueError, 'não identificada'):
                ctrl.switch_input('a|0', 17)
            self.assertEqual(backend.calls, [('a|0', 3)])

    def test_no_fallback_to_observed_input(self):
        with tempfile.TemporaryDirectory() as d:
            backend = FakeBackend()
            ctrl = Controller(Path(d) / 'config.json', backend)
            backend.enumerate_monitors = lambda: [
                SimpleNamespace(id='a|0', hardware_id='MONITOR\\\\a|0',
                                current=5, supported_inputs=None)]
            ctrl.scan()
            with self.assertRaisesRegex(ValueError, 'indisponíveis'):
                ctrl.register('a|0', 'Monitor', '5', '')
            with self.assertRaisesRegex(ValueError, 'não identificada'):
                ctrl.switch_input('a|0', 5)
            self.assertEqual(backend.calls, [])

    def test_reenumeration_and_noop(self):
        with tempfile.TemporaryDirectory() as d:
            backend = FakeBackend()
            ctrl = Controller(Path(d) / 'config.json', backend)
            ctrl.scan()
            ctrl.register('a|0', 'Dell', 15, 17)
            def changed():
                return [SimpleNamespace(id='a|0', hardware_id='MONITOR\\\\other',
                                        current=15, supported_inputs=[15, 17])]
            backend.enumerate_monitors = changed
            with self.assertRaisesRegex(RuntimeError, 'alterou a associação'):
                ctrl.switch_one('a|0', 'B')
            self.assertEqual(backend.calls, [])
            backend.enumerate_monitors = lambda: [
                SimpleNamespace(id='a|0', hardware_id='MONITOR\\\\a|0', current=15, supported_inputs=[15, 17])]
            result = ctrl.switch_one('a|0', 'A')
            self.assertTrue(result['unchanged'])
            self.assertEqual(backend.calls, [])

if __name__ == '__main__':
    unittest.main()
