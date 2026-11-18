"""Windows DDC/CI monitor backend, using only the Python standard library."""
from __future__ import annotations
import ctypes
import re
import sys
from ctypes import wintypes
from dataclasses import dataclass, asdict

VCP_INPUT = 0x60
SOURCE_CODES = {"VGA": 0x01, "DVI": 0x03, "DisplayPort": 0x0F,
                "HDMI 1": 0x11, "HDMI 2": 0x12}

# These are common MCCS values, not a complete list of physical ports.
SOURCE_OPTIONS = tuple(f'{name} ({code})' for name, code in SOURCE_CODES.items())


def source_name(code):
    """Common name for a VCP input value, otherwise show its exact number."""
    for name, known in SOURCE_CODES.items():
        if code == known:
            return name
    return f'Código {code}' if code is not None else 'Leitura indisponível'


def source_option(code):
    """Display a saved mapping as a named option or an editable custom code."""
    if code is None:
        return ''
    name = source_name(code)
    return f'{name} ({code})' if code in SOURCE_CODES.values() else str(code)


@dataclass
class Monitor:
    id: str
    display: str
    description: str
    index: int
    current: int | None = None
    read_error: str | None = None
    bounds: tuple[int, int, int, int] | None = None
    hardware_id: str | None = None
    identity_source: str = 'ddc'
    supported_inputs: list[int] | None = None
    capabilities_error: str | None = None

    def to_dict(self):
        return asdict(self)


def parse_code(value):
    if isinstance(value, bool):
        raise ValueError("Código VCP inválido")
    if isinstance(value, int):
        code = value
    elif isinstance(value, str):
        value = value.strip()
        if value in SOURCE_OPTIONS:
            code = next(number for name, number in SOURCE_CODES.items()
                        if value == f'{name} ({number})')
        elif value in SOURCE_CODES:
            code = SOURCE_CODES[value]
        else:
            code = int(value, 16 if value.lower().startswith('0x') else 10)
    else:
        raise ValueError("Código deve ser inteiro, decimal ou hexadecimal 0xNN")
    if not 0 <= code <= 255:
        raise ValueError("Código de entrada deve estar entre 0 e 255")
    return code


if sys.platform == 'win32':
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    dxva2 = ctypes.WinDLL('dxva2', use_last_error=True)

    class RECT(ctypes.Structure):
        _fields_ = [('left', wintypes.LONG), ('top', wintypes.LONG),
                    ('right', wintypes.LONG), ('bottom', wintypes.LONG)]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', RECT),
                    ('rcWork', RECT), ('dwFlags', wintypes.DWORD),
                    ('szDevice', wintypes.WCHAR * 32)]

    class PHYSICAL_MONITOR(ctypes.Structure):
        _fields_ = [('hPhysicalMonitor', wintypes.HANDLE),
                    ('szPhysicalMonitorDescription', wintypes.WCHAR * 128)]

    CALLBACK = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR,
                                  wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM)
    user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(RECT), CALLBACK, wintypes.LPARAM]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, ctypes.POINTER(wintypes.DWORD)]
    dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
    dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, wintypes.DWORD, ctypes.POINTER(PHYSICAL_MONITOR)]
    dxva2.GetPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
    dxva2.DestroyPhysicalMonitors.argtypes = [wintypes.DWORD, ctypes.POINTER(PHYSICAL_MONITOR)]
    dxva2.DestroyPhysicalMonitors.restype = wintypes.BOOL
    dxva2.GetVCPFeatureAndVCPFeatureReply.argtypes = [wintypes.HANDLE, ctypes.c_ubyte,
                                                      ctypes.POINTER(wintypes.DWORD),
                                                      ctypes.POINTER(wintypes.DWORD),
                                                      ctypes.POINTER(wintypes.DWORD)]
    dxva2.GetVCPFeatureAndVCPFeatureReply.restype = wintypes.BOOL
    dxva2.SetVCPFeature.argtypes = [wintypes.HANDLE, ctypes.c_ubyte, wintypes.DWORD]
    dxva2.SetVCPFeature.restype = wintypes.BOOL
    dxva2.GetCapabilitiesStringLength.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    dxva2.GetCapabilitiesStringLength.restype = wintypes.BOOL
    dxva2.CapabilitiesRequestAndCapabilitiesReply.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    dxva2.CapabilitiesRequestAndCapabilitiesReply.restype = wintypes.BOOL


    class DISPLAY_DEVICEW(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('DeviceName', wintypes.WCHAR * 32),
                    ('DeviceString', wintypes.WCHAR * 128), ('StateFlags', wintypes.DWORD),
                    ('DeviceID', wintypes.WCHAR * 128), ('DeviceKey', wintypes.WCHAR * 128)]

    user32.EnumDisplayDevicesW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DISPLAY_DEVICEW), wintypes.DWORD]
    user32.EnumDisplayDevicesW.restype = wintypes.BOOL


def _device_identity(display):
    """Resolve a screen using its GDI display name, not display order.

    EnumDisplayDevicesW(display, index) lists monitor devices belonging to the
    adapter. DeviceString may be generic; the monitor hardware ID can be used
    to read an EDID model name from the matching Windows registry entry.
    """
    if sys.platform != 'win32':
        return None, None, 'unsupported'
    devices = []
    index = 0
    while True:
        mon = DISPLAY_DEVICEW()
        mon.cb = ctypes.sizeof(mon)
        if not user32.EnumDisplayDevicesW(display, index, ctypes.byref(mon), 0):
            break
        devices.append(mon)
        index += 1
    if not devices:
        return None, None, 'no_monitor_device'
    for mon in devices:
        label = mon.DeviceString.strip()
        hardware_id = mon.DeviceID.strip()
        if label and label.casefold() not in ('generic pnp monitor', 'generic non-pnp monitor'):
            return label, hardware_id, 'windows'
        name = _registry_edid_name(hardware_id)
        if name:
            return name, hardware_id, 'edid'
    return None, devices[0].DeviceID.strip(), 'generic'


def _registry_edid_name(hardware_id):
    import winreg
    parts = hardware_id.split('\\')
    if len(parts) < 2 or parts[0].upper() not in ('MONITOR', 'DISPLAY'):
        return None
    code = parts[1]
    if not code or '/' in code:
        return None
    path = 'SYSTEM\\CurrentControlSet\\Enum\\DISPLAY\\' + code
    names = set()
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
            i = 0
            while True:
                try:
                    instance = winreg.EnumKey(key, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(key, instance + '\\Device Parameters') as sub:
                        data, _ = winreg.QueryValueEx(sub, 'EDID')
                        name = _edid_name(data)
                        if name:
                            names.add(name)
                except OSError:
                    continue
    except OSError:
        return None
    return next(iter(names)) if len(names) == 1 else None


def _edid_name(data):
    if not isinstance(data, bytes) or len(data) < 128 or data[:8] != bytes.fromhex('00ffffffffffff00'):
        return None
    for at in range(54, 126, 18):
        descriptor = data[at:at + 18]
        if len(descriptor) == 18 and descriptor[:5] == bytes.fromhex('000000fc00'):
            name = descriptor[5:18].split(b'\\n')[0].strip(b'\\x00 ').decode('ascii', 'replace').strip()
            if name:
                return name
    return None


def _winerr(message):
    return OSError(f'{message} (erro Windows {ctypes.get_last_error()})')


def _enumerate():
    if sys.platform != 'win32':
        raise RuntimeError('Controle DDC/CI disponível apenas no Windows neste MVP')
    found = []

    def cb(hmon, _hdc, _rect, _param):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        if not user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            return True
        found.append((hmon, info.szDevice, (info.rcMonitor.left, info.rcMonitor.top,
                                            info.rcMonitor.right, info.rcMonitor.bottom)))
        return True
    callback = CALLBACK(cb)
    if not user32.EnumDisplayMonitors(None, None, callback, 0):
        raise _winerr('Erro ao enumerar os monitores')
    return sorted(found, key=lambda item: item[1])


def _physical(hmon):
    count = wintypes.DWORD()
    if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, ctypes.byref(count)):
        raise _winerr('Não foi possível obter os monitores físicos')
    if count.value == 0:
        return None, 0
    array = (PHYSICAL_MONITOR * count.value)()
    if not dxva2.GetPhysicalMonitorsFromHMONITOR(hmon, count, array):
        raise _winerr('Não foi possível abrir monitores físicos')
    return array, count.value


def _read(handle):
    kind = wintypes.DWORD()
    current = wintypes.DWORD()
    maximum = wintypes.DWORD()
    if not dxva2.GetVCPFeatureAndVCPFeatureReply(handle, VCP_INPUT,
                                                  ctypes.byref(kind), ctypes.byref(current),
                                                  ctypes.byref(maximum)):
        raise _winerr('Falha ao ler VCP 0x60')
    return current.value


def _balanced_section(source, name):
    """Find a named parenthesized MCCS section, preserving nested items."""
    match = re.search(r'(?i)(?:^|[\\s(])' + re.escape(name) + r'\\s*\\(', source)
    if not match:
        return None
    opening = source.find('(', match.start())
    depth = 1
    for index in range(opening + 1, len(source)):
        if source[index] == '(':
            depth += 1
        elif source[index] == ')':
            depth -= 1
            if depth == 0:
                return source[opening + 1:index]
    return None


def parse_input_capabilities(source):
    """Return supported values advertised by VCP 60, or None if absent."""
    vcp = _balanced_section(source, 'vcp')
    if vcp is None:
        return None
    inputs = _balanced_section(vcp, '60')
    if inputs is None:
        return None
    tokens = re.findall(r'(?i)(?<![0-9a-f])[0-9a-f]{2}(?![0-9a-f])', inputs)
    values = sorted(set(int(token, 16) for token in tokens))
    return values or None


def _capabilities(handle):
    length = wintypes.DWORD()
    if not dxva2.GetCapabilitiesStringLength(handle, ctypes.byref(length)):
        raise _winerr('Monitor não respondeu à consulta de capacidades')
    if not 2 <= length.value <= 65536:
        raise ValueError('Comprimento inválido de capacidades DDC/CI')
    buffer = ctypes.create_string_buffer(length.value + 1)
    if not dxva2.CapabilitiesRequestAndCapabilitiesReply(
            handle, ctypes.cast(buffer, ctypes.c_void_p), length.value):
        raise _winerr('Monitor não retornou capacidades DDC/CI')
    raw = buffer.value.decode('ascii', errors='replace')
    return parse_input_capabilities(raw)


def enumerate_monitors(read_current=True):
    result = []
    for hmon, display, bounds in _enumerate():
        try:
            array, count = _physical(hmon)
        except OSError as exc:
            result.append(Monitor(f'{display}|0', display, 'Não acessível por DDC/CI', 0,
                                  read_error=str(exc), bounds=bounds))
            continue
        if not array:
            continue
        try:
            model, hardware_id, identity_source = _device_identity(display)
            for i in range(count):
                item = array[i]
                m = Monitor(f'{display}|{i}', display,
                            model or item.szPhysicalMonitorDescription, i,
                            bounds=bounds, hardware_id=hardware_id,
                            identity_source=identity_source if model else 'ddc')
                if read_current:
                    try:
                        m.current = _read(item.hPhysicalMonitor)
                    except OSError as exc:
                        m.read_error = str(exc)
                    try:
                        m.supported_inputs = _capabilities(item.hPhysicalMonitor)
                        if m.supported_inputs is None:
                            m.capabilities_error = 'VCP 0x60 não anunciado pelo monitor'
                    except (OSError, ValueError) as exc:
                        m.capabilities_error = str(exc)
                result.append(m)
        finally:
            dxva2.DestroyPhysicalMonitors(count, array)
    return result


def set_input(monitor_id, value):
    code = parse_code(value)
    for hmon, display, bounds in _enumerate():
        if not monitor_id.startswith(display + '|'):
            continue
        try:
            wanted = int(monitor_id.rsplit('|', 1)[1])
        except (ValueError, IndexError):
            raise ValueError('ID de monitor inválido')
        array, count = _physical(hmon)
        if not array:
            raise RuntimeError('Sem monitor físico disponível')
        try:
            if not 0 <= wanted < count:
                raise ValueError('Índice de monitor não encontrado')
            if not dxva2.SetVCPFeature(array[wanted].hPhysicalMonitor, VCP_INPUT, code):
                raise _winerr('Falha ao escrever VCP 0x60')
        finally:
            dxva2.DestroyPhysicalMonitors(count, array)
        return {'id': monitor_id, 'code': code, 'sent': True}
    raise ValueError(f'Monitor {monitor_id} não está disponível neste PC')
