# -*- coding: utf-8 -*-
"""
menu_bar.py — 화면 오른쪽 아래 메뉴 아이콘 + 반투명 메뉴판

MenuDock  (평소에 떠 있는 작은 창)
    - 오른쪽 아래 둥근 메뉴 아이콘: 누르면(클릭 또는 1.2초 응시) 메뉴판이 열림
    - 아이콘 옆 상태 표시: 지금 켜져 있는 모드를 짧게 표시 (예: "배율 ×2 · 잔상 ON")
    - 일시정지 중에는 아이콘이 자물쇠로 바뀌고, 자물쇠를 3초 바라보면 다시 활성화

MenuPanel (메뉴판, 반투명)
    - 오른쪽 위 X 버튼(크롬 창처럼): 메뉴판 닫기
    - 상태 칩: 지금 실행 중인 모드 (활성/일시정지, 배율, 잔상, 키보드)
    - 1. 확대/축소  (-/+ 누를 때마다 2배씩)
    - 2. 일시정지 (커서만 숨김, 자물쇠 3초 응시로 다시 활성화)
    - 3. 키보드 열기/닫기 (화상 키보드 + 자동완성)
    - 4. 시선 잔상 ON/OFF
    - 5. 캘리브레이션 다시 하기

이 파일의 위젯들은 "버튼이 눌렸다"는 신호만 내보내고, 실제로 무엇을 할지는 main.py가 정합니다.
"""
from PyQt5 import QtWidgets, QtCore, QtGui

import theme
from gaze_widgets import GazeButton, CloseButton, setup_floating_window, DWELL_CLICK_SEC

EDGE_MARGIN = 24          # 화면 가장자리와의 간격
UNLOCK_DWELL_SEC = 3.0    # 자물쇠를 이만큼 바라보면 일시정지 해제 (요구사항: 3초)
QUIT_DWELL_SEC = 2.5      # 실수로 종료되지 않도록 종료 버튼은 조금 더 오래 봐야 함


def anchor_bottom_right(widget):
    """창을 화면(작업표시줄 제외) 오른쪽 아래에 붙임."""
    widget.adjustSize()
    area = QtWidgets.QApplication.primaryScreen().availableGeometry()
    widget.move(area.right() - widget.width() - EDGE_MARGIN + 1,
                area.bottom() - widget.height() - EDGE_MARGIN + 1)


def paint_panel_background(widget, radius=26):
    """메뉴판·키보드 공통: 반투명 둥근 사각형 배경."""
    p = QtGui.QPainter(widget)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setPen(QtGui.QPen(theme.PANEL_EDGE, 2))
    p.setBrush(theme.PANEL_BG)
    p.drawRoundedRect(QtCore.QRectF(widget.rect()).adjusted(1, 1, -1, -1), radius, radius)


class MenuIconButton(GazeButton):
    """둥근 메뉴 아이콘. 평소엔 ≡ 모양, 일시정지 중엔 자물쇠 모양 (+ 바라보는 동안 둘레 게이지)."""

    def __init__(self, parent=None, size=76):
        super().__init__("", parent)
        self.setFixedSize(size, size)
        self.locked = False

    def set_locked(self, locked):
        self.locked = locked
        self.dwell_sec = UNLOCK_DWELL_SEC if locked else DWELL_CLICK_SEC
        self.active_when_paused = locked         # 일시정지 중에도 시선으로 누를 수 있는 유일한 버튼
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(5, 5, -5, -5)
        hl = self.is_highlighted()
        p.setPen(QtGui.QPen(theme.HIGHLIGHT if hl else theme.PANEL_EDGE, 5 if hl else 2))
        p.setBrush(QtGui.QColor(255, 249, 240, 225 if hl else 190))   # 반투명 아이콘
        p.drawEllipse(r)

        c = r.center()
        ink = QtGui.QPen(theme.INK, 4.5)
        ink.setCapStyle(QtCore.Qt.RoundCap)
        if self.locked:                                   # 자물쇠
            body = QtCore.QRectF(c.x() - 15, c.y() - 3, 30, 22)
            p.setPen(ink)
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawArc(QtCore.QRectF(c.x() - 10, c.y() - 20, 20, 30), 0, 180 * 16)
            p.drawLine(QtCore.QPointF(c.x() - 10, c.y() - 5), QtCore.QPointF(c.x() - 10, c.y() - 3))
            p.drawLine(QtCore.QPointF(c.x() + 10, c.y() - 5), QtCore.QPointF(c.x() + 10, c.y() - 3))
            p.setBrush(theme.INK)
            p.drawRoundedRect(body, 5, 5)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(255, 249, 240))
            p.drawEllipse(QtCore.QPointF(c.x(), c.y() + 7), 3.5, 3.5)
        else:                                             # ≡ 메뉴
            p.setPen(ink)
            for dy in (-10, 0, 10):
                p.drawLine(QtCore.QPointF(c.x() - 14, c.y() + dy), QtCore.QPointF(c.x() + 14, c.y() + dy))

        if self.progress > 0:                             # 바라보는 동안 둘레 게이지 (자물쇠일 땐 커서가 숨겨져 있어서 여기서 보여줌)
            pen = QtGui.QPen(theme.GAUGE, 6)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawArc(r.adjusted(-1, -1, 1, 1), 90 * 16, int(-360 * 16 * self.progress))


class MenuDock(QtWidgets.QWidget):
    open_requested = QtCore.pyqtSignal()
    unlock_requested = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        setup_floating_window(self)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self.pill = QtWidgets.QLabel("")
        self.pill.setFont(theme.ui_font(17))
        self.pill.setStyleSheet("QLabel { background-color: rgba(255, 249, 240, 200);"
                                " border: 2px solid rgba(150, 115, 85, 170); border-radius: 17px;"
                                " padding: 6px 14px; color: #4A3428; }")
        self.icon = MenuIconButton()
        self.icon.clicked.connect(self._on_icon)
        lay.addWidget(self.pill, 0, QtCore.Qt.AlignVCenter)
        lay.addWidget(self.icon, 0, QtCore.Qt.AlignVCenter)

    def _on_icon(self):
        if self.icon.locked:
            self.unlock_requested.emit()
        else:
            self.open_requested.emit()

    def set_locked(self, locked):
        self.icon.set_locked(locked)

    def set_status_text(self, text):
        self.pill.setText(text)
        anchor_bottom_right(self)


class StatusChips(QtWidgets.QWidget):
    """'지금 실행 중인 모드'를 작은 알약 모양으로 나열. 줄이 넘치면 다음 줄로."""

    def __init__(self, width):
        super().__init__()
        self.chips = []                    # (글자, 색)
        self.setFixedWidth(width)
        self.setFont(theme.ui_font(17))

    def set_chips(self, chips):
        self.chips = chips
        self.setFixedHeight(self._layout()[1])
        self.update()

    def _layout(self):
        fm = QtGui.QFontMetrics(self.font())
        x, y, h, gap = 0, 0, 34, 8
        rects = []
        for text, color in self.chips:
            w = fm.horizontalAdvance(text) + 36
            if x > 0 and x + w > self.width():
                x, y = 0, y + h + gap
            rects.append((QtCore.QRectF(x, y, w, h), text, color))
            x += w + gap
        return rects, (y + h if self.chips else 0)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setFont(self.font())
        for rect, text, color in self._layout()[0]:
            p.setPen(QtGui.QPen(color, 2))
            p.setBrush(QtGui.QColor(255, 255, 255, 210))
            p.drawRoundedRect(rect, 17, 17)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(QtCore.QPointF(rect.left() + 16, rect.center().y()), 5, 5)   # 상태 색 점
            p.setPen(theme.INK)
            p.drawText(rect.adjusted(26, 0, -8, 0), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, text)


class MenuPanel(QtWidgets.QWidget):
    close_requested = QtCore.pyqtSignal()
    zoom_in_requested = QtCore.pyqtSignal()
    zoom_out_requested = QtCore.pyqtSignal()
    pause_requested = QtCore.pyqtSignal()
    keyboard_toggle_requested = QtCore.pyqtSignal()
    trail_toggle_requested = QtCore.pyqtSignal()
    recalibrate_requested = QtCore.pyqtSignal()
    quit_requested = QtCore.pyqtSignal()

    PANEL_W = 460

    def __init__(self):
        super().__init__()
        setup_floating_window(self)
        self.setFixedWidth(self.PANEL_W)
        inner_w = self.PANEL_W - 24 - 24

        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(24, 16, 16, 22)
        v.setSpacing(12)

        # 머리줄: 제목 + 오른쪽 위 X (크롬 창처럼)
        head = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("메뉴")
        title.setFont(theme.title_font(38))
        title.setStyleSheet("color: #4A3428; background: transparent;")
        self.close_btn = CloseButton()
        self.close_btn.clicked.connect(lambda: self.close_requested.emit())
        head.addWidget(title, 0, QtCore.Qt.AlignVCenter)
        head.addStretch(1)
        head.addWidget(self.close_btn, 0, QtCore.Qt.AlignTop)
        v.addLayout(head)

        # 지금 실행 중인 모드
        self.chips = StatusChips(inner_w - 8)
        v.addWidget(self.chips)
        v.addSpacing(4)

        # 1. 확대/축소
        v.addWidget(self._section("1. 확대 / 축소  (2배씩)"))
        zoom = QtWidgets.QHBoxLayout()
        zoom.setSpacing(10)
        self.zoom_out_btn = GazeButton("-  축소", font_px=24)
        self.zoom_label = QtWidgets.QLabel("×1")
        self.zoom_label.setAlignment(QtCore.Qt.AlignCenter)
        self.zoom_label.setFont(theme.title_font(36))
        self.zoom_label.setStyleSheet("color: #4A3428; background: transparent;")
        self.zoom_label.setFixedWidth(84)
        self.zoom_in_btn = GazeButton("+  확대", font_px=24)
        for b in (self.zoom_out_btn, self.zoom_in_btn):
            b.setFixedHeight(64)
        self.zoom_out_btn.clicked.connect(lambda: self.zoom_out_requested.emit())
        self.zoom_in_btn.clicked.connect(lambda: self.zoom_in_requested.emit())
        zoom.addWidget(self.zoom_out_btn, 1)
        zoom.addWidget(self.zoom_label)
        zoom.addWidget(self.zoom_in_btn, 1)
        v.addLayout(zoom)

        # 2~5. 나머지 모드
        self.pause_btn = self._item("2. 일시정지  (커서 숨기기)", self.pause_requested)
        self.keyboard_btn = self._item("3. 키보드 열기", self.keyboard_toggle_requested)
        self.trail_btn = self._item("4. 시선 잔상  ON", self.trail_toggle_requested)
        self.calib_btn = self._item("5. 캘리브레이션 다시 하기", self.recalibrate_requested)
        for b in (self.pause_btn, self.keyboard_btn, self.trail_btn, self.calib_btn):
            v.addWidget(b)

        # 안내 + 오른쪽 아래 종료 버튼
        foot = QtWidgets.QHBoxLayout()
        hint = QtWidgets.QLabel("버튼을 1.2초 바라보면 눌려요")
        hint.setFont(theme.ui_font(15, bold=False))
        hint.setStyleSheet("color: #78604E; background: transparent;")
        self.quit_btn = GazeButton("종료", font_px=20, dwell_sec=QUIT_DWELL_SEC, radius=14)
        self.quit_btn.setFixedSize(120, 52)
        self.quit_btn.clicked.connect(lambda: self.quit_requested.emit())
        foot.addWidget(hint, 1, QtCore.Qt.AlignVCenter)
        foot.addWidget(self.quit_btn, 0, QtCore.Qt.AlignRight | QtCore.Qt.AlignBottom)
        v.addSpacing(2)
        v.addLayout(foot)

    def _section(self, text):
        lab = QtWidgets.QLabel(text)
        lab.setFont(theme.ui_font(19))
        lab.setStyleSheet("color: #78604E; background: transparent;")
        return lab

    def _item(self, text, signal):
        b = GazeButton(text, font_px=23)
        b.setFixedHeight(66)
        b.clicked.connect(lambda _=False, s=signal: s.emit())
        return b

    def update_state(self, st):
        """main.py가 모드가 바뀔 때마다 호출. st = {"paused", "zoom", "trail", "keyboard"}"""
        self.zoom_label.setText(f"×{st['zoom']}")
        self.zoom_out_btn.setEnabled(st["zoom"] > 1)
        self.zoom_in_btn.setEnabled(st["zoom"] < 8)
        self.keyboard_btn.setText("3. 키보드 닫기" if st["keyboard"] else "3. 키보드 열기")
        self.keyboard_btn.set_on(st["keyboard"])
        self.trail_btn.setText("4. 시선 잔상  ON" if st["trail"] else "4. 시선 잔상  OFF")
        self.trail_btn.set_on(st["trail"])
        self.chips.set_chips([
            ("일시정지" if st["paused"] else "활성", theme.RED if st["paused"] else theme.GREEN),
            (f"배율 ×{st['zoom']}", theme.GAUGE if st["zoom"] > 1 else theme.INK_SOFT),
            ("잔상 ON" if st["trail"] else "잔상 OFF", theme.GAUGE if st["trail"] else theme.INK_SOFT),
            ("키보드 열림" if st["keyboard"] else "키보드 닫힘", theme.GAUGE if st["keyboard"] else theme.INK_SOFT),
        ])
        if self.isVisible():
            anchor_bottom_right(self)

    def paintEvent(self, event):
        paint_panel_background(self)
