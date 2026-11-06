# -*- coding: utf-8 -*-
"""
hotkey.py — 키보드 Ctrl + Alt + - 로 메뉴창 열고 닫기 (진행자용 단축키)

어느 프로그램을 보고 있든(우리 창에 포커스가 없어도) Ctrl + Alt + - 를 누르면 pressed 신호를 보냅니다.
main.py가 이 신호를 받아 메뉴창을 열거나 닫습니다 (toggle_panel).

    - "-"는 키보드 위쪽 "-" 키와 숫자패드 "-" 키 둘 다 됩니다.
    - Ctrl과 Alt를 둘 다 누르고 있을 때만 동작합니다. 평소에 "-"만 칠 때는 아무 일도 없어요.
    - Shift나 Win을 같이 누르면 무시합니다 (다른 단축키와 겹치지 않게).
    - 화상 키보드로 보내는 글자는 실제 키 누름이 아니라서 메뉴창을 건드리지 않습니다.

방식: 0.03초마다 윈도우에 "지금 이 키들이 눌려 있나?"를 물어보고(GetAsyncKeyState),
      Ctrl·Alt를 누른 채로 "-"가 눌린 순간에만 한 번 신호를 보냅니다 (꾹 누르고 있어도 한 번만).
      키를 가로채지 않으므로 이 조합이 다른 프로그램에도 전달되지만, Ctrl + Alt + - 를 쓰는 프로그램은 거의 없습니다.
윈도우에서만 동작합니다 (다른 운영체제에서는 아무 일도 안 함).
"""
import sys

from PyQt5 import QtCore

VK_MINUS = (0xBD, 0x6D)          # VK_OEM_MINUS(키보드 위쪽 -), VK_SUBTRACT(숫자패드 -)
VK_CTRL, VK_ALT = 0x11, 0x12
VK_BLOCK = (0x10, 0x5B, 0x5C)    # 같이 누르면 무시: Shift, 왼쪽·오른쪽 Win
POLL_MS = 30                     # 키 확인 간격 (0.03초)


class MenuHotkey(QtCore.QObject):
    pressed = QtCore.pyqtSignal()             # Ctrl + Alt + - 를 누른 순간 한 번

    def __init__(self, parent=None):
        super().__init__(parent)
        self._was_down = False
        self._user32 = None
        if sys.platform != "win32":
            return
        import ctypes
        self._user32 = ctypes.windll.user32
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(POLL_MS)

    def _is_down(self, vk):
        return bool(self._user32.GetAsyncKeyState(vk) & 0x8000)

    def _poll(self):
        down = any(self._is_down(vk) for vk in VK_MINUS)
        if (down and not self._was_down
                and self._is_down(VK_CTRL) and self._is_down(VK_ALT)
                and not any(self._is_down(vk) for vk in VK_BLOCK)):
            self.pressed.emit()
        self._was_down = down
