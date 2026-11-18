import tempfile
import unittest
from pathlib import Path
from backend import parse_code
from core import Controller


class FakeBackend:
    def __init__(self):
        self.calls = []

    def set_input(self, monitor_id, code):
        self.calls.append((monitor_id, code))
        return {'id': monitor_id, 'code': code, 'sent': True}


class Tests(unittest.TestCase):
    def test_codes(self):
        self.assertEqual(parse_code('0x11'), 17)
        self.assertEqual(parse_code('15'), 15)
        with self.assertRaises(ValueError):
            parse_code('256')
        with self.assertRaises(ValueError):
            parse_code(True)

    def test_switch(self):
        with tempfile.TemporaryDirectory() as d:
            backend = FakeBackend()
            ctrl = Controller(Path(d) / 'config.json', backend)
            ctrl.register('a|0', 'Dell', '0x0F', '0x03')
            ctrl.register('b|0', 'Samsung', '17', '15')
            result = ctrl.switch_all('B')
            self.assertEqual(len(result), 2)
            self.assertEqual(backend.calls, [('a|0', 3), ('b|0', 15)])
            with self.assertRaises(ValueError):
                ctrl.switch_one('a|0', 'C')
            reload = Controller(Path(d) / 'config.json', backend)
            self.assertEqual(reload.config['monitors']['a|0']['b'], 3)

if __name__ == '__main__':
    unittest.main()
