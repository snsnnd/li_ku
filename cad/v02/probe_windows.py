"""Read-only Windows dialog diagnostics for a specified SolidWorks PID. No clicks."""
import ctypes
from ctypes import wintypes
import sys


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    pid = int(sys.argv[1])
    user = ctypes.WinDLL('user32', use_last_error=True)
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user.IsWindowVisible.argtypes = (wintypes.HWND,)
    user.EnumWindows.argtypes = (callback, wintypes.LPARAM)
    user.EnumChildWindows.argtypes = (wintypes.HWND, callback, wintypes.LPARAM)
    user.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    def text(hwnd):
        length = user.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length+1)
        user.GetWindowTextW(hwnd, buffer, length+1)
        return buffer.value
    @callback
    def child(hwnd, unused):
        value = text(hwnd)
        if value:
            print(' CHILD', int(hwnd), repr(value))
        return True
    @callback
    def window(hwnd, unused):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user.IsWindowVisible(hwnd):
            print('WINDOW', int(hwnd), repr(text(hwnd)))
            if '--cancel-owned-tube-import' in sys.argv and text(hwnd) == 'Open Progress...':
                labels = []
                buttons = []
                @callback
                def inspect(h, unused):
                    value = text(h); labels.append(value)
                    if value in ('取消', 'Cancel'):
                        buttons.append(h)
                    return True
                user.EnumChildWindows(hwnd, inspect, 0)
                if not any('Tray_Al_Tube_25x25x2_L227' in v for v in labels) or len(buttons) != 1:
                    raise RuntimeError('Refusing to cancel an unidentified operation')
                print('CANCEL_OWNED_TUBE_IMPORT', bool(user.PostMessageW(buttons[0], 0xF5, 0, 0)))
            elif '--top-level' not in sys.argv:
                user.EnumChildWindows(hwnd, child, 0)
        return True
    user.EnumWindows(window, 0)


if __name__ == '__main__':
    main()
