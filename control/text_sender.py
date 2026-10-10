# -*- coding: utf-8 -*-
"""
text_sender.py — 화상 키보드에서 쓴 글자를 "지금 커서가 깜빡이는 다른 프로그램"으로 보내는 부분

윈도우의 SendInput(유니코드 모드)으로 글자를 한 글자씩 직접 쳐 넣습니다.
    - 한글 입력기(IME) 상태와 상관없이 완성된 글자("안녕")가 그대로 들어갑니다.
    - 클립보드를 쓰지 않아서, 사용자가 복사해 둔 내용을 덮어쓰지 않습니다.
화상 키보드 창은 포커스를 가져가지 않게 만들어져 있어서(setup_floating_window),
키보드를 눌러도 글자를 받을 프로그램(메모장, 카톡, 브라우저 입력칸 등)의 포커스가 그대로 유지됩니다.

보낼 곳 기억: 키보드를 마우스로 누르는 순간 웹사이트 창이 비활성으로 바뀌어도, 마지막으로 쓰던 창을 기억해 두었다가
              보내기 직전에 그 창을 다시 앞으로 불러온 뒤 입력합니다 (foreground_other_window / activate).
주의: "관리자 권한으로 실행된 프로그램"에는 윈도우 보안 정책 때문에 보내지지 않습니다.
      그런 프로그램에 보내려면 이 데모도 관리자 권한 cmd에서 실행해야 합니다.
Qt와 무관한 순수 파이썬 파일입니다.
"""
import ctypes
import os
import sys

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_RETURN = 0x0D

if sys.platform == "win32":
    from ctypes import wintypes

    # 크기를 윈도우 정의와 똑같이 고정 (WORD=2바이트, DWORD/LONG=4바이트, ULONG_PTR=포인터 크기)
    ULONG_PTR = ctypes.c_size_t

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_uint16), ("wScan", ctypes.c_uint16), ("dwFlags", ctypes.c_uint32),
                    ("time", ctypes.c_uint32), ("dwExtraInfo", ULONG_PTR)]

    class MOUSEINPUT(ctypes.Structure):      # INPUT 구조체 크기를 윈도우와 똑같이 맞추기 위해 필요
        _fields_ = [("dx", ctypes.c_int32), ("dy", ctypes.c_int32), ("mouseData", ctypes.c_uint32),
                    ("dwFlags", ctypes.c_uint32), ("time", ctypes.c_uint32), ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", ctypes.c_uint32), ("wParamL", ctypes.c_uint16), ("wParamH", ctypes.c_uint16)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_uint32), ("u", _INPUTUNION)]

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    _user32.SendInput.restype = wintypes.UINT
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    _user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    _user32.IsWindow.argtypes = (wintypes.HWND,)
    _user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    _get_ex = getattr(_user32, "GetWindowLongPtrW", _user32.GetWindowLongW)
    _set_ex = getattr(_user32, "SetWindowLongPtrW", _user32.SetWindowLongW)
    _get_ex.argtypes = (wintypes.HWND, ctypes.c_int)
    _get_ex.restype = ctypes.c_ssize_t
    _set_ex.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
    _set_ex.restype = ctypes.c_ssize_t

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000


# ── 글자를 받을 창 기억하기 ─────────────────────────────────────────
# 키보드를 마우스로 누르면 웹브라우저 창이 "비활성"으로 바뀌어서 입력칸 커서가 사라질 수 있음.
# 그래서 "우리 프로그램이 아닌 창 중 마지막으로 앞에 있던 창"을 계속 기억해 두었다가,
# 보낼 때 그 창을 다시 앞으로 불러온 뒤 글자를 넣음. (브라우저는 다시 활성화되면 아까 클릭한 입력칸으로 커서를 되돌려 줌)
def foreground_other_window():
    """지금 맨 앞 창이 이 데모가 아닌 다른 프로그램이면 그 창 번호(hwnd), 아니면 None."""
    if sys.platform != "win32":
        return None
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return None if pid.value == os.getpid() else hwnd


def window_title(hwnd):
    if sys.platform != "win32" or not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def activate(hwnd):
    """hwnd 창을 다시 맨 앞(활성)으로. 이미 앞에 있으면 그대로 True."""
    if sys.platform != "win32" or not hwnd or not _user32.IsWindow(hwnd):
        return False
    if _user32.GetForegroundWindow() == hwnd:
        return True
    return bool(_user32.SetForegroundWindow(hwnd))


def make_no_activate(widget):
    """widget 창을 눌러도 다른 창의 활성 상태를 뺏지 않게 함 (WS_EX_NOACTIVATE).
    Qt 설정(WindowDoesNotAcceptFocus)만으로는 마우스 클릭 시 활성화되는 경우가 있어서 윈도우에 직접 지정."""
    if sys.platform != "win32":
        return
    hwnd = int(widget.winId())
    style = _get_ex(hwnd, GWL_EXSTYLE)
    if not style & WS_EX_NOACTIVATE:
        _set_ex(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE)


def _key_events(text, press_enter):
    events = []

    def add(vk=0, scan=0, flags=0):
        events.append(INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(vk, scan, flags, 0, 0))))

    for ch in text:
        if ch == "\n":
            add(vk=VK_RETURN)
            add(vk=VK_RETURN, flags=KEYEVENTF_KEYUP)
            continue
        data = ch.encode("utf-16-le")             # 이모지처럼 큰 글자는 2칸(서로게이트)으로 나눠서 보냄
        for i in range(0, len(data), 2):
            unit = int.from_bytes(data[i:i + 2], "little")
            add(scan=unit, flags=KEYEVENTF_UNICODE)
            add(scan=unit, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
    if press_enter:
        add(vk=VK_RETURN)
        add(vk=VK_RETURN, flags=KEYEVENTF_KEYUP)
    return events


VK_BROWSER_BACK = 0xA6   # 키보드·마우스의 '뒤로' 버튼과 같은 키 (브라우저·파일 탐색기 등에서 뒤로가기)


def send_back():
    """지금 앞에 있는 프로그램에 '뒤로가기' 키를 보냄. 성공하면 True."""
    if sys.platform != "win32":
        return False
    events = [INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(VK_BROWSER_BACK, 0, flags, 0, 0)))
              for flags in (0, KEYEVENTF_KEYUP)]
    arr = (INPUT * 2)(*events)
    return _user32.SendInput(2, arr, ctypes.sizeof(INPUT)) == 2


def send_text(text, press_enter=False):
    """text를 지금 포커스된 프로그램에 입력. press_enter=True면 끝에 엔터도 누름.
    성공하면 True, 윈도우가 아니거나 막혔으면 False."""
    if sys.platform != "win32" or (not text and not press_enter):
        return False
    events = _key_events(text, press_enter)
    arr = (INPUT * len(events))(*events)
    sent = _user32.SendInput(len(events), arr, ctypes.sizeof(INPUT))
    return sent == len(events)
