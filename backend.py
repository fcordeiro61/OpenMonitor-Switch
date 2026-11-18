"""Windows DDC/CI monitor backend, using only the Python standard library."""
from __future__ import annotations
import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass, asdict

VCP_INPUT = 0x60
SOURCE_CODES = {"VGA": 0x01, "DVI": 0x03, "DisplayPort": 0x0F,
                "HDMI 1": 0x11, "HDMI 2": 0x12}


@dataclass
class Monitor:
    id: str
    display: str
    description: str
    index: int
    current: int | None = None
    read_error: str | None = None
    bounds: tuple[int, int, int, int] | None = None

    def to_dict(self):
        return asdict(self)


def parse_code(value):
    if isinstance(value, bool):
        raise ValueError("Código VCP inválido")
    if isinstance(value, int):
        code = value
    elif isinstance(value, str):
        value = value.strip()
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
            for i in range(count):
                item = array[i]
                m = Monitor(f'{display}|{i}', display, item.szPhysicalMonitorDescription, i,
                            bounds=bounds)
                if read_current:
                    try:
                        m.current = _read(item.hPhysicalMonitor)
                    except OSError as exc:
                        m.read_error = str(exc)
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
