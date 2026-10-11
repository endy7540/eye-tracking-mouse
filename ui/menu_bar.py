# -*- coding: utf-8 -*-
"""
menu_bar.py — 화면 오른쪽 아래 메뉴 아이콘 + 화면 가운데 반투명 메뉴창 (테마색)

MenuDock  (평소에 떠 있는 메뉴 아이콘)
    - 오른쪽 아래 테마색 둥근 아이콘(지름 ICON_PX): 누르면(클릭 또는 1.2초 응시) 메뉴창이 열림
    - 평소엔 완전히 투명해서 안 보이고, 커서(시선)가 가까이 오면 서서히 나타남 (NEAR_PX 안 = 완전히 보임)
      처음 나타날 때는 어디 있는지 알 수 있게 INTRO_SEC 동안 보여줬다가 사라짐
    - 아이콘 왼쪽 상태 글자: 지금 켜져 있는 모드를 짧게 표시 (아이콘과 같이 나타남)
    - 일시정지 중에는 자물쇠로 바뀌고 항상 보임 (커서가 숨겨져서 다가가는 걸 알 수 없으므로).
      자물쇠를 3초 바라보면 다시 활성화
    - 화면 전체 확대 중에는 보이는 영역의 오른쪽 아래에 붙고, 확대돼도 원래 크기로 보이게 작게 그림 (set_view)
    - 아이콘 바로 왼쪽: 스크롤 모드 ON/OFF 토글 (ScrollToggle). 아이콘과 달리 항상 보임 (메뉴창을 열어도).
      누르면(클릭 또는 1.2초 응시) scroll_toggle_requested 신호 → main.py가 켜고 끈 뒤 set_scroll()로 표시를 맞춤.
      (스크롤 영역은 화면 위·아래 15%이고, 메뉴 아이콘·토글이 있는 오른쪽 아래 칸은 스크롤 영역에서 빠져 있음)
    - 메뉴창이 열려 있는 동안(set_menu_open(True))은 아이콘·상태 글자만 숨기고 토글은 그대로 둠.
      메뉴창은 화면 아래쪽에 토글 자리(BOTTOM_RESERVE)를 비워 두고 크기를 정하므로 둘이 겹치지 않음.
    - 상태 글자는 아이콘 바로 위에 나타남 (아이콘 왼쪽은 토글 자리)

MenuPanel (메뉴창 — 화면 가운데에 크게, 테마색 반투명)
    - 오른쪽 위 X 버튼(크롬 창처럼): 메뉴창 닫기
    - 세로로 긴 큰 카드 8개 (각 카드 아래쪽에 지금 상태 표시)
        1. 확대/축소   (-/+ 누를 때마다 0.25배씩, 화면 전체 확대. 누르면 메뉴창이 닫히고 바로 확대됨)
        2. 커서 투명도 (-/+ 누를 때마다 10%씩, 높을수록 투명)
        3. 일시정지    (커서만 숨김, 자물쇠 3초 응시로 다시 활성화)
        4. 키보드      (화상 키보드 열기/닫기)
        5. 시선 잔상   (ON/OFF)
        6. 캘리브레이션 다시 하기
        7. 윙크 클릭   (아무 쪽 → 왼눈 → 오른눈 → 끔 순서로 바뀜. 두 눈을 같이 감는 깜빡임은 항상 무시)
        8. 응시 클릭   (ON/OFF — 한곳을 바라보면 다른 프로그램도 클릭)
    - 아래 줄: 테마 고르기(동그라미 6개) · [개발용] 상태 확인 · 오른쪽 아래 종료
    - 크기: 1920×1080 화면 기준 1760×750이고, 화면이 작으면 비율대로 줄어듦 (_relayout)

테마는 메뉴창·메뉴 아이콘·커서에만 적용됩니다 (theme.current()). 화상 키보드·상태 확인 창이 쓰는
paint_panel_background()와 GazeButton은 예전 갈색 모양 그대로 둡니다.

이 파일의 위젯들은 "버튼이 눌렸다"는 신호만 내보내고, 실제로 무엇을 할지는 main.py가 정합니다.

[제출 전] 상태 확인 버튼은 개발할 때만 쓰는 것이라 SHOW_STATUS_BUTTON = False로 바꾸면 메뉴창에서 사라집니다.
"""
import math
import time

from PyQt5 import QtWidgets, QtCore, QtGui

from . import theme
from .gaze_widgets import GazeButton, setup_floating_window, DWELL_CLICK_SEC
from .seal_cursor import MIN_OPACITY, MAX_OPACITY
from .magnifier import zoom_text

SHOW_STATUS_BUTTON = True # [개발용] 상태 확인 버튼 보이기 — 제출할 때 False로

EDGE_MARGIN = 24          # 화면 가장자리와의 간격
UNLOCK_DWELL_SEC = 3.0    # 자물쇠를 이만큼 바라보면 일시정지 해제 (요구사항: 3초)
QUIT_DWELL_SEC = 2.5      # 실수로 종료되지 않도록 종료 버튼은 조금 더 오래 봐야 함

ICON_PX = 110             # 메뉴 아이콘 지름 (예전 76px보다 크게)
NEAR_PX = 170             # 커서가 아이콘 중심에서 이 거리 안이면 완전히 보임
FAR_PX = 380              # 이 거리 밖이면 완전히 투명 (사이에서는 서서히)
INTRO_SEC = 3.0           # 아이콘이 처음 나타날 때 이 시간 동안은 보여줌 (어디 있는지 알 수 있게)
SCROLL_W, SCROLL_H = 210, 64   # 스크롤 ON/OFF 토글 크기 (메뉴 아이콘 왼쪽)
SCROLL_GAP = 14           # 토글과 메뉴 아이콘 사이 간격
# 메뉴창이 화면 아래쪽에 비워 둘 높이 = 토글 윗부분까지 + 여유 (메뉴창과 토글이 겹치지 않게)
BOTTOM_RESERVE = EDGE_MARGIN + ICON_PX / 2 + SCROLL_H / 2 + 12

PANEL_BG_ALPHA = 0.30     # 메뉴창 배경 진하기 (많이 투명하게 — 뒤 화면이 비쳐 보임)
CARD_BG = QtGui.QColor(255, 255, 255, 205)   # 카드 바탕 (뒤가 비쳐도 글씨가 읽히게 흰색 반투명)
BASE_W, BASE_H = 1760, 750                   # 메뉴창 기준 크기 (1920×1080 화면)
QUIT_RED = QtGui.QColor(222, 70, 70)
OFF_GRAY = QtGui.QColor(160, 166, 176)


# ── 창 위치 ─────────────────────────────────────────────────────────────
def anchor_bottom_right(widget):
    """창을 화면(작업표시줄 제외) 오른쪽 아래에 붙임."""
    widget.adjustSize()
    area = QtWidgets.QApplication.primaryScreen().availableGeometry()
    widget.move(area.right() - widget.width() - EDGE_MARGIN + 1,
                area.bottom() - widget.height() - EDGE_MARGIN + 1)


def place_center(widget):
    """창을 화면(작업표시줄 제외) 가운데에 놓음."""
    area = QtWidgets.QApplication.primaryScreen().availableGeometry()
    widget.move(area.center().x() - widget.width() // 2, area.center().y() - widget.height() // 2)


def paint_panel_background(widget, radius=26):
    """화상 키보드·상태 확인 창 공통: 반투명 둥근 사각형 배경 (갈색 — 테마와 무관)."""
    p = QtGui.QPainter(widget)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setPen(QtGui.QPen(theme.PANEL_EDGE, 2))
    p.setBrush(theme.PANEL_BG)
    p.drawRoundedRect(QtCore.QRectF(widget.rect()).adjusted(1, 1, -1, -1), radius, radius)


# ── 그리기 도구 ─────────────────────────────────────────────────────────
def _pen(color, width):
    pen = QtGui.QPen(color, width)
    pen.setCapStyle(QtCore.Qt.RoundCap)
    pen.setJoinStyle(QtCore.Qt.RoundJoin)
    return pen


def draw_icon(p, kind, c, size, color):
    """아이콘 그리기. c = 가운데(QPointF), size = 아이콘 크기(px), color = 선/면 색.
    아래 숫자들은 크기 64짜리 기준이고, u 배율로 늘리거나 줄여서 그림."""
    u = size / 64.0
    x, y = c.x(), c.y()
    P = lambda dx, dy: QtCore.QPointF(x + dx * u, y + dy * u)
    p.save()
    p.setBrush(QtCore.Qt.NoBrush)
    if kind == "zoom":                                   # 돋보기 + 플러스
        p.setPen(_pen(color, 8 * u))
        p.drawEllipse(P(-7, -7), 25 * u, 25 * u)
        p.setPen(_pen(color, 11 * u))
        p.drawLine(P(12, 12), P(28, 28))
        p.setPen(_pen(color, 6 * u))
        p.drawLine(P(-19, -7), P(5, -7))
        p.drawLine(P(-7, -19), P(-7, 5))
    elif kind == "opacity":                              # 반쯤 채운 원 (투명도)
        p.setPen(_pen(color, 6 * u))
        p.drawEllipse(P(0, 0), 29 * u, 29 * u)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(color)
        p.drawPie(QtCore.QRectF(x - 26 * u, y - 26 * u, 52 * u, 52 * u), 90 * 16, 180 * 16)
    elif kind == "pause":                                # 일시정지 두 막대
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(QtCore.QRectF(x - 22 * u, y - 25 * u, 14 * u, 50 * u), 6 * u, 6 * u)
        p.drawRoundedRect(QtCore.QRectF(x + 8 * u, y - 25 * u, 14 * u, 50 * u), 6 * u, 6 * u)
    elif kind == "keyboard":                             # 키보드
        p.setPen(_pen(color, 6 * u))
        p.drawRoundedRect(QtCore.QRectF(x - 34 * u, y - 22 * u, 68 * u, 44 * u), 8 * u, 8 * u)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(color)
        for row in (-9, 2):
            for i in range(5):
                kx = -22 + i * 11
                p.drawRoundedRect(QtCore.QRectF(x + (kx - 3) * u, y + (row - 3) * u, 6 * u, 6 * u), 1.5 * u, 1.5 * u)
        p.drawRoundedRect(QtCore.QRectF(x - 16 * u, y + 11 * u, 32 * u, 4 * u), 2 * u, 2 * u)
    elif kind == "trail":                                # 지나온 자리 (점점 흐려지는 점 3개)
        p.setPen(QtCore.Qt.NoPen)
        for (dx, dy, r, a) in ((-18, 16, 7, 0.3), (-2, 1, 11, 0.6), (15, -15, 15, 1.0)):
            p.setBrush(theme.with_alpha(color, a))
            p.drawEllipse(P(dx, dy), r * u, r * u)
    elif kind == "calib":                                # 과녁
        p.setPen(_pen(color, 6 * u))
        p.drawEllipse(P(0, 0), 28 * u, 28 * u)
        p.drawEllipse(P(0, 0), 14 * u, 14 * u)
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            p.drawLine(P(dx * 34, dy * 34), P(dx * 42, dy * 42))
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(P(0, 0), 4.5 * u, 4.5 * u)
    elif kind == "wink":                                 # 한쪽 눈은 뜨고 한쪽 눈은 감은 얼굴
        p.setPen(_pen(color, 5 * u))
        p.drawEllipse(P(-15, 0), 13 * u, 9 * u)
        path = QtGui.QPainterPath(P(3, 1))
        path.quadTo(P(15, 11), P(27, 1))
        p.drawPath(path)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(P(-15, 0), 4.5 * u, 4.5 * u)
    elif kind == "dwell":                                # 가운데 점 + 차오르는 게이지 (바라보면 클릭)
        p.setPen(_pen(theme.with_alpha(color, 0.25), 6 * u))
        p.drawEllipse(P(0, 0), 24 * u, 24 * u)
        p.setPen(_pen(color, 6 * u))
        p.drawArc(QtCore.QRectF(x - 24 * u, y - 24 * u, 48 * u, 48 * u), 90 * 16, -270 * 16)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(P(0, 0), 8 * u, 8 * u)
    elif kind == "status":                               # 막대 그래프 (상태 확인)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(color)
        for i, h in enumerate((18, 30, 44)):
            p.drawRoundedRect(QtCore.QRectF(x + (-24 + i * 18) * u, y + (22 - h) * u, 12 * u, h * u), 3 * u, 3 * u)
    elif kind == "power":                                # 전원 (종료)
        p.setPen(_pen(color, 6 * u))
        p.drawArc(QtCore.QRectF(x - 20 * u, y - 20 * u, 40 * u, 40 * u), 120 * 16, 300 * 16)
        p.drawLine(P(0, -24), P(0, -4))
    elif kind == "menu":                                 # ≡
        p.setPen(_pen(color, 8 * u))
        for dy in (-14, 0, 14):
            p.drawLine(P(-22, dy), P(22, dy))
    elif kind == "lock":                                 # 자물쇠
        p.setPen(_pen(color, 6 * u))
        p.drawArc(QtCore.QRectF(x - 14 * u, y - 28 * u, 28 * u, 30 * u), 0, 180 * 16)
        p.drawLine(P(-14, -13), P(-14, -4))
        p.drawLine(P(14, -13), P(14, -4))
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(QtCore.QRectF(x - 21 * u, y - 4 * u, 42 * u, 30 * u), 6 * u, 6 * u)
    p.restore()


def paint_card(p, r, th, highlighted, s, radius=28):
    """카드 바탕: 흰색 반투명 + 테마색 테두리. 시선(또는 마우스)이 올라가면 굵은 진한 테두리 + 둘레 빛."""
    if highlighted:
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(theme.with_alpha(th["main"], 0.35))
        p.drawRoundedRect(r.adjusted(-4 * s, -4 * s, 4 * s, 4 * s), (radius + 4) * s, (radius + 4) * s)
        p.setPen(QtGui.QPen(th["deep"], 6 * s))
    else:
        p.setPen(QtGui.QPen(theme.with_alpha(th["main"], 0.45), 2 * s))
    p.setBrush(CARD_BG)
    p.drawRoundedRect(r, radius * s, radius * s)


def paint_chip(p, cx, cy, text, dot, th, s):
    """작은 상태 알약: 색 점 + 글자. 예) ● 실행 중"""
    f = theme.ui_font(17 * s)
    w = QtGui.QFontMetricsF(f).horizontalAdvance(text) + 48 * s
    h = 40 * s
    rect = QtCore.QRectF(cx - w / 2, cy - h / 2, w, h)
    p.setPen(QtGui.QPen(theme.with_alpha(th["main"], 0.5), 2 * s))
    p.setBrush(QtGui.QColor(255, 255, 255, 235))
    p.drawRoundedRect(rect, h / 2, h / 2)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(dot)
    p.drawEllipse(QtCore.QPointF(rect.left() + 19 * s, cy), 6 * s, 6 * s)
    p.setPen(th["deep"])
    p.setFont(f)
    p.drawText(rect.adjusted(32 * s, 0, -10 * s, 0), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, text)


def paint_toggle(p, cx, cy, on, th, s):
    """ON/OFF 스위치. 켜짐 = 테마색 + 오른쪽 동그라미, 꺼짐 = 회색 + 왼쪽 동그라미."""
    w, h = 104 * s, 50 * s
    rect = QtCore.QRectF(cx - w / 2, cy - h / 2, w, h)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(th["main"] if on else OFF_GRAY)
    p.drawRoundedRect(rect, h / 2, h / 2)
    knob_x = rect.right() - h / 2 if on else rect.left() + h / 2
    p.setBrush(QtGui.QColor(255, 255, 255))
    p.drawEllipse(QtCore.QPointF(knob_x, cy), h / 2 - 5 * s, h / 2 - 5 * s)
    p.setPen(QtGui.QColor(255, 255, 255))
    p.setFont(theme.ui_font(19 * s))
    label = QtCore.QRectF(rect.left() + 8 * s, rect.top(), w - h - 4 * s, h) if on else \
        QtCore.QRectF(rect.left() + h - 2 * s, rect.top(), w - h - 4 * s, h)
    p.drawText(label, QtCore.Qt.AlignCenter, "ON" if on else "OFF")


def paint_progress_bar(p, r, frac, th, s):
    """카드 맨 아래 응시 진행 막대 (바라보는 동안 차오름)."""
    if frac <= 0:
        return
    bar = QtCore.QRectF(r.left() + 20 * s, r.bottom() - 20 * s, (r.width() - 40 * s) * frac, 7 * s)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(th["main"])
    p.drawRoundedRect(bar, 3.5 * s, 3.5 * s)


# ── 메뉴창 부품 ─────────────────────────────────────────────────────────
class ActionCard(GazeButton):
    """누르면 바로 동작하는 세로 카드 (일시정지·키보드·잔상·캘리브레이션·윙크·응시 클릭).
    위에서부터: 아이콘 → 이름 → 설명 → 지금 상태(알약 또는 ON/OFF 스위치)."""

    def __init__(self, parent, kind, title, sub, dwell_sec=DWELL_CLICK_SEC):
        super().__init__("", parent, dwell_sec=dwell_sec)
        self.kind, self.title, self.sub = kind, title, sub
        self.footer = ("chip", "", OFF_GRAY)      # ("chip", 글자, 점 색) 또는 ("toggle", 켜짐 여부)
        self.s = 1.0

    def set_scale(self, s):
        self.s = s
        self.update()

    def set_chip(self, text, dot):
        self.footer = ("chip", text, dot)
        self.update()

    def set_toggle(self, on):
        self.footer = ("toggle", on)
        self.update()

    def paintEvent(self, event):
        th, s = theme.current(), self.s
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(5 * s, 5 * s, -5 * s, -5 * s)
        paint_card(p, r, th, self.is_highlighted(), s)
        _paint_card_head(p, r, th, s, self.kind, self.title)
        p.setPen(theme.with_alpha(th["deep"], 0.8))
        p.setFont(theme.ui_font(17 * s, bold=False))
        p.drawText(QtCore.QRectF(r.left() + 6 * s, r.top() + 204 * s, r.width() - 12 * s, 34 * s),
                   QtCore.Qt.AlignCenter, self.sub)
        fy = r.top() + 296 * s
        if self.footer[0] == "toggle":
            paint_toggle(p, r.center().x(), fy, self.footer[1], th, s)
        elif self.footer[1]:
            paint_chip(p, r.center().x(), fy, self.footer[1], self.footer[2], th, s)
        paint_progress_bar(p, r, self.progress, th, s)


def _paint_card_head(p, r, th, s, kind, title):
    """카드 위쪽 공통: 연한 동그라미 위 아이콘 + 이름."""
    ic = QtCore.QPointF(r.center().x(), r.top() + 92 * s)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(th["light"])
    p.drawEllipse(ic, 56 * s, 56 * s)
    draw_icon(p, kind, ic, 62 * s, th["deep"])
    p.setPen(th["deep"])
    p.setFont(theme.ui_font(26 * s))
    p.drawText(QtCore.QRectF(r.left(), r.top() + 160 * s, r.width(), 42 * s), QtCore.Qt.AlignCenter, title)


class StepButton(GazeButton):
    """카드 안의 둥근 -/+ 버튼 (확대/축소, 커서 투명도)."""

    def __init__(self, parent, sign):
        super().__init__("", parent)
        self.sign = sign              # "-" 또는 "+"
        self.s = 1.0

    def paintEvent(self, event):
        th, s = theme.current(), self.s
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.35)        # 더 못 늘리거나 줄일 때는 흐리게
        r = QtCore.QRectF(self.rect()).adjusted(4 * s, 4 * s, -4 * s, -4 * s)
        hl = self.is_highlighted() and self.isEnabled()
        p.setPen(QtGui.QPen(th["deep"] if hl else th["main"], (6 if hl else 3) * s))
        p.setBrush(th["light"])
        p.drawEllipse(r)
        c = r.center()
        d = r.width() * 0.2
        p.setPen(_pen(th["deep"], 6 * s))
        p.drawLine(QtCore.QPointF(c.x() - d, c.y()), QtCore.QPointF(c.x() + d, c.y()))
        if self.sign == "+":
            p.drawLine(QtCore.QPointF(c.x(), c.y() - d), QtCore.QPointF(c.x(), c.y() + d))
        if self.progress > 0:         # 바라보는 동안 둘레에 게이지
            p.setPen(_pen(th["deep"], 5 * s))
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawArc(r.adjusted(-1, -1, 1, 1), 90 * 16, int(-360 * 16 * self.progress))


class StepperCard(QtWidgets.QWidget):
    """-/+ 버튼으로 값을 바꾸는 세로 카드 (확대/축소, 커서 투명도). 카드 자체는 눌리지 않고 버튼만 눌림."""

    def __init__(self, parent, kind, title):
        super().__init__(parent)
        self.kind, self.title = kind, title
        self.value, self.hint = "", ""
        self.s = 1.0
        self.minus = StepButton(self, "-")
        self.plus = StepButton(self, "+")

    def set_scale(self, s):
        self.s = s
        self.minus.s = self.plus.s = s
        self._place_buttons()
        self.update()

    def set_value(self, value, hint):
        self.value, self.hint = value, hint
        self.update()

    def resizeEvent(self, event):
        self._place_buttons()
        super().resizeEvent(event)

    def _place_buttons(self):
        s = self.s
        size = int(66 * s)
        cx, cy = self.width() / 2, 5 * s + 316 * s
        self.minus.setFixedSize(size, size)
        self.plus.setFixedSize(size, size)
        self.minus.move(int(cx - 46 * s - size / 2), int(cy - size / 2))
        self.plus.move(int(cx + 46 * s - size / 2), int(cy - size / 2))

    def paintEvent(self, event):
        th, s = theme.current(), self.s
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(5 * s, 5 * s, -5 * s, -5 * s)
        hl = (self.minus.is_highlighted() and self.minus.isEnabled()) or \
             (self.plus.is_highlighted() and self.plus.isEnabled())
        paint_card(p, r, th, hl, s)
        _paint_card_head(p, r, th, s, self.kind, self.title)
        p.setPen(th["deep"])
        p.setFont(theme.title_font(32 * s))
        p.drawText(QtCore.QRectF(r.left(), r.top() + 200 * s, r.width(), 40 * s), QtCore.Qt.AlignCenter, self.value)
        p.setPen(theme.with_alpha(th["deep"], 0.75))
        p.setFont(theme.ui_font(15 * s, bold=False))
        p.drawText(QtCore.QRectF(r.left(), r.top() + 238 * s, r.width(), 28 * s), QtCore.Qt.AlignCenter, self.hint)


class ThemeSwatch(GazeButton):
    """테마 고르는 동그라미. 고른 테마는 바깥 고리 + 체크 표시 (사진처럼)."""

    def __init__(self, parent, key):
        super().__init__("", parent)
        self.key = key
        self.selected = False
        self.s = 1.0

    def paintEvent(self, event):
        s = self.s
        th = theme.current()                         # 글자색은 지금 테마를 따름
        own = theme.theme_colors(self.key)           # 동그라미 색은 이 버튼의 테마
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        c = QtCore.QPointF(self.width() / 2, self.height() * 0.36)
        R = 32 * s
        if self.is_highlighted():
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(theme.with_alpha(own["main"], 0.25))
            p.drawEllipse(c, R + 16 * s, R + 16 * s)
        if self.selected:
            p.setPen(QtGui.QPen(own["main"], 5 * s))
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawEllipse(c, R + 9 * s, R + 9 * s)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(own["main"])
        p.drawEllipse(c, R, R)
        if self.selected:
            p.setPen(_pen(QtGui.QColor(255, 255, 255), 6 * s))
            p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(c.x() - 13 * s, c.y()),
                                            QtCore.QPointF(c.x() - 3 * s, c.y() + 10 * s),
                                            QtCore.QPointF(c.x() + 15 * s, c.y() - 10 * s)]))
        if self.progress > 0:
            p.setPen(_pen(own["deep"], 5 * s))
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawArc(QtCore.QRectF(c.x() - R - 9 * s, c.y() - R - 9 * s, 2 * (R + 9 * s), 2 * (R + 9 * s)),
                      90 * 16, int(-360 * 16 * self.progress))
        p.setPen(th["deep"] if self.selected else theme.with_alpha(th["deep"], 0.7))
        p.setFont(theme.ui_font(18 * s, bold=self.selected))
        p.drawText(QtCore.QRectF(0, self.height() * 0.80 - 16 * s, self.width(), 32 * s),
                   QtCore.Qt.AlignCenter, own["name"])


class PanelCloseButton(GazeButton):
    """메뉴창 오른쪽 위 X (크롬 창처럼): 평소엔 흰 동그라미 위 X, 시선/마우스가 올라가면 빨간 배경 + 흰 X."""

    def __init__(self, parent):
        super().__init__("", parent)
        self.s = 1.0
        self.setToolTip("닫기")

    def paintEvent(self, event):
        th, s = theme.current(), self.s
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(3 * s, 3 * s, -3 * s, -3 * s)
        hl = self.is_highlighted()
        p.setPen(QtGui.QPen(theme.with_alpha(th["main"], 0.6), 2 * s) if not hl else QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(232, 17, 35) if hl else QtGui.QColor(255, 255, 255, 235))
        p.drawEllipse(r)
        if self.progress > 0:
            p.setPen(_pen(QtGui.QColor(255, 255, 255) if hl else th["main"], 4 * s))
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawArc(r.adjusted(4 * s, 4 * s, -4 * s, -4 * s), 90 * 16, int(-360 * 16 * self.progress))
        p.setPen(_pen(QtGui.QColor(255, 255, 255) if hl else th["deep"], 5 * s))
        c, d = r.center(), r.width() * 0.19
        p.drawLine(QtCore.QPointF(c.x() - d, c.y() - d), QtCore.QPointF(c.x() + d, c.y() + d))
        p.drawLine(QtCore.QPointF(c.x() - d, c.y() + d), QtCore.QPointF(c.x() + d, c.y() - d))


class BottomButton(GazeButton):
    """아래 줄의 큰 버튼: 종료(빨강) / 상태 확인(개발용, 점선 테두리)."""

    def __init__(self, parent, kind, label, dwell_sec=DWELL_CLICK_SEC):
        super().__init__("", parent, dwell_sec=dwell_sec)
        self.kind, self.label = kind, label
        self.s = 1.0

    def paintEvent(self, event):
        th, s = theme.current(), self.s
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(5 * s, 5 * s, -5 * s, -5 * s)
        hl = self.is_highlighted()
        if self.kind == "power":                                   # 종료
            color = QUIT_RED
            p.setPen(QtGui.QPen(color, (6 if hl else 3) * s))
            p.setBrush(QtGui.QColor(255, 236, 236, 235) if hl else CARD_BG)
            p.drawRoundedRect(r, 28 * s, 28 * s)
        else:                                                      # 상태 확인 (개발용)
            color = th["deep"]
            pen = QtGui.QPen(th["deep"] if hl else theme.with_alpha(th["main"], 0.7), (5 if hl else 2.5) * s)
            pen.setStyle(QtCore.Qt.DashLine)
            p.setPen(pen)
            p.setBrush(QtGui.QColor(th["light"]) if self.on else CARD_BG)
            p.drawRoundedRect(r, 28 * s, 28 * s)
            tag = QtCore.QRectF(r.center().x() - 38 * s, r.top() + 12 * s, 76 * s, 26 * s)   # "개발용" 꼬리표
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(theme.HIGHLIGHT)
            p.drawRoundedRect(tag, 13 * s, 13 * s)
            p.setPen(QtGui.QColor(255, 255, 255))
            p.setFont(theme.ui_font(14 * s))
            p.drawText(tag, QtCore.Qt.AlignCenter, "개발용")
        draw_icon(p, self.kind, QtCore.QPointF(r.center().x(), r.top() + r.height() * 0.45), 50 * s, color)
        p.setPen(color)
        p.setFont(theme.title_font(28 * s) if self.kind == "power" else theme.ui_font(20 * s))
        p.drawText(QtCore.QRectF(r.left(), r.top() + r.height() * 0.68, r.width(), r.height() * 0.26),
                   QtCore.Qt.AlignCenter, self.label)
        paint_progress_bar(p, r, self.progress, th, s)


class MenuPanel(QtWidgets.QWidget):
    close_requested = QtCore.pyqtSignal()
    zoom_in_requested = QtCore.pyqtSignal()
    zoom_out_requested = QtCore.pyqtSignal()
    transparency_up_requested = QtCore.pyqtSignal()     # 커서 투명도 + (더 투명하게)
    transparency_down_requested = QtCore.pyqtSignal()   # 커서 투명도 - (더 진하게)
    pause_requested = QtCore.pyqtSignal()
    keyboard_toggle_requested = QtCore.pyqtSignal()
    trail_toggle_requested = QtCore.pyqtSignal()
    recalibrate_requested = QtCore.pyqtSignal()
    wink_toggle_requested = QtCore.pyqtSignal()
    dwell_toggle_requested = QtCore.pyqtSignal()
    status_requested = QtCore.pyqtSignal()
    theme_selected = QtCore.pyqtSignal(str)             # 고른 테마 key (예: "mint")
    quit_requested = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        setup_floating_window(self)
        self.s = 1.0
        self.header_rect = QtCore.QRectF()
        self.theme_rect = QtCore.QRectF()

        self.close_btn = PanelCloseButton(self)
        self.close_btn.clicked.connect(lambda: self.close_requested.emit())

        # 세로 카드 8개 (왼쪽부터 순서대로)
        self.zoom_card = StepperCard(self, "zoom", "확대 / 축소")
        self.opacity_card = StepperCard(self, "opacity", "커서 투명도")
        self.pause_card = ActionCard(self, "pause", "일시정지", "커서 숨기기")
        self.keyboard_card = ActionCard(self, "keyboard", "키보드", "화상 키보드")
        self.trail_card = ActionCard(self, "trail", "시선 잔상", "지나간 길 표시")
        self.calib_card = ActionCard(self, "calib", "캘리브레이션", "다시 맞추기")
        self.wink_card = ActionCard(self, "wink", "윙크 클릭", "누르면 바뀌어요")
        self.dwell_card = ActionCard(self, "dwell", "응시 클릭", "한곳을 보면 클릭")
        self.cards = [self.zoom_card, self.opacity_card, self.pause_card, self.keyboard_card,
                      self.trail_card, self.calib_card, self.wink_card, self.dwell_card]
        self.calib_card.set_chip("두더지 잡기", theme.YELLOW)

        self.zoom_card.minus.clicked.connect(lambda: self.zoom_out_requested.emit())
        self.zoom_card.plus.clicked.connect(lambda: self.zoom_in_requested.emit())
        self.opacity_card.minus.clicked.connect(lambda: self.transparency_down_requested.emit())
        self.opacity_card.plus.clicked.connect(lambda: self.transparency_up_requested.emit())
        for card, sig in ((self.pause_card, self.pause_requested),
                          (self.keyboard_card, self.keyboard_toggle_requested),
                          (self.trail_card, self.trail_toggle_requested),
                          (self.calib_card, self.recalibrate_requested),
                          (self.wink_card, self.wink_toggle_requested),
                          (self.dwell_card, self.dwell_toggle_requested)):
            card.clicked.connect(lambda _=False, sg=sig: sg.emit())

        # 아래 줄: 테마 동그라미 6개 · 상태 확인(개발용) · 종료
        self.swatches = []
        for t in theme.THEMES:
            sw = ThemeSwatch(self, t["key"])
            sw.clicked.connect(lambda _=False, k=t["key"]: self.theme_selected.emit(k))
            self.swatches.append(sw)
        self.status_btn = BottomButton(self, "status", "상태 확인")
        self.status_btn.clicked.connect(lambda: self.status_requested.emit())
        self.status_btn.setVisible(SHOW_STATUS_BUTTON)
        self.quit_btn = BottomButton(self, "power", "종료", dwell_sec=QUIT_DWELL_SEC)
        self.quit_btn.clicked.connect(lambda: self.quit_requested.emit())

        self._relayout()

    # ── 배치 ─────────────────────────────────────────────────────
    def _relayout(self):
        """화면 크기에 맞춰 메뉴창 크기(s 배율)와 안쪽 부품 위치를 정함. 1920×1080에서 s = 1."""
        area = QtWidgets.QApplication.primaryScreen().availableGeometry()
        s = min(area.width() * 0.94 / BASE_W, area.height() * 0.92 / BASE_H,
                (area.height() - 2 * BOTTOM_RESERVE) / BASE_H, 1.0)    # 아래쪽 스크롤 토글과 겹치지 않게
        s = max(s, 0.45)
        self.s = s
        W, H = int(BASE_W * s), int(BASE_H * s)
        self.setFixedSize(W, H)
        pad, gap = 40 * s, 18 * s

        # 머리줄 + 오른쪽 위 X
        cb = int(64 * s)
        self.header_rect = QtCore.QRectF(pad, pad, W - 2 * pad - cb - 16 * s, 76 * s)
        self.close_btn.s = s
        self.close_btn.setFixedSize(cb, cb)
        self.close_btn.move(int(W - pad - cb), int(pad + 6 * s))

        # 세로 카드 8개
        top, ch = pad + 76 * s + 22 * s, 400 * s
        cw = (W - 2 * pad - 7 * gap) / 8
        for i, card in enumerate(self.cards):
            card.setGeometry(int(pad + i * (cw + gap)), int(top), int(cw), int(ch))
            card.set_scale(s)

        # 아래 줄 (오른쪽부터: 종료 → 상태 확인 → 남은 자리에 테마)
        by, bh, bw = top + ch + 22 * s, 150 * s, 190 * s
        right = W - pad
        for btn, show in ((self.quit_btn, True), (self.status_btn, SHOW_STATUS_BUTTON)):
            if show:
                btn.s = s
                btn.setGeometry(int(right - bw), int(by), int(bw), int(bh))
                right -= bw + gap
        self.theme_rect = QtCore.QRectF(pad, by, right - pad, bh)
        sw_x = pad + 230 * s
        sw_w = (self.theme_rect.right() - 16 * s - sw_x) / len(self.swatches)
        for i, sw in enumerate(self.swatches):
            sw.s = s
            sw.setGeometry(int(sw_x + i * sw_w), int(by + 6 * s), int(sw_w), int(bh - 12 * s))
        self.update()

    def place(self):
        """화면 크기에 맞게 다시 배치하고 화면 가운데에 놓음 (main.py가 메뉴창을 열 때 호출)."""
        self._relayout()
        place_center(self)

    def refresh_theme(self):
        """테마가 바뀌면 메뉴창 전체를 다시 그림."""
        self.update()
        for w in self.cards + self.swatches + [self.close_btn, self.status_btn, self.quit_btn]:
            w.update()
        for card in (self.zoom_card, self.opacity_card):
            card.minus.update()
            card.plus.update()

    # ── 상태 표시 ────────────────────────────────────────────────
    def update_state(self, st):
        """main.py가 모드가 바뀔 때마다 호출.
        st = {"paused", "zoom", "trail", "keyboard", "wink", "dwell", "status",
              (있으면) "opacity", "theme", "zoom_kind"("screen" 화면 전체 / "lens" 원형 돋보기), "zoom_max"}"""
        zoom, zmax = st["zoom"], st.get("zoom_max", 8)
        self.zoom_card.set_value(zoom_text(zoom),
                                 "0.25배씩 확대" if st.get("zoom_kind", "screen") == "screen" else "돋보기로 확대")
        self.zoom_card.minus.setEnabled(zoom > 1 + 1e-6)
        self.zoom_card.plus.setEnabled(zoom < zmax - 1e-6)

        op = st.get("opacity", 0.6)
        self.opacity_card.set_value(f"{round((1 - op) * 100)}%", "높을수록 투명")
        self.opacity_card.plus.setEnabled(op > MIN_OPACITY + 1e-6)     # 투명도 + = 진하기 -
        self.opacity_card.minus.setEnabled(op < MAX_OPACITY - 1e-6)

        if st["paused"]:
            self.pause_card.set_chip("일시정지 중", theme.RED)
        else:
            self.pause_card.set_chip("실행 중", theme.GREEN)
        self.keyboard_card.set_chip("열림" if st["keyboard"] else "닫힘",
                                    theme.GREEN if st["keyboard"] else OFF_GRAY)
        self.trail_card.set_toggle(st["trail"])
        wink_name = {"both": "아무 쪽 눈", "left": "왼눈만", "right": "오른눈만", "off": "끔"}[st["wink"]]
        self.wink_card.set_chip(wink_name, theme.GREEN if st["wink"] != "off" else OFF_GRAY)
        self.dwell_card.set_toggle(st["dwell"])
        self.status_btn.set_on(st.get("status", False))

        key = st.get("theme", theme.current_key())
        for sw in self.swatches:
            sw.selected = sw.key == key
            sw.update()
        self.update()
        if self.isVisible():
            self.place()

    # ── 그리기 ───────────────────────────────────────────────────
    def paintEvent(self, event):
        th, s = theme.current(), self.s
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        # 배경: 테마색, 많이 투명하게
        p.setPen(QtGui.QPen(theme.with_alpha(th["main"], 0.95), 4 * s))
        p.setBrush(theme.with_alpha(th["main"], PANEL_BG_ALPHA))
        p.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(2 * s, 2 * s, -2 * s, -2 * s), 44 * s, 44 * s)

        # 머리줄 (뒤 화면 글씨와 겹쳐도 읽히도록 흰색 반투명 바탕)
        hr = self.header_rect
        p.setPen(QtGui.QPen(theme.with_alpha(th["main"], 0.4), 2 * s))
        p.setBrush(QtGui.QColor(255, 255, 255, 190))
        p.drawRoundedRect(hr, hr.height() / 2, hr.height() / 2)
        p.setPen(th["deep"])
        p.setFont(theme.title_font(46 * s))
        p.drawText(QtCore.QRectF(hr.left() + 32 * s, hr.top(), 140 * s, hr.height()),
                   QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, "메뉴")
        p.setPen(theme.with_alpha(th["deep"], 0.85))
        p.setFont(theme.ui_font(22 * s))
        p.drawText(QtCore.QRectF(hr.left() + 160 * s, hr.top(), hr.width() - 180 * s, hr.height()),
                   QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, "버튼을 1.2초 바라보면 선택돼요")

        # 테마 칸 바탕 + 제목 (동그라미들은 ThemeSwatch가 따로 그림)
        tr = self.theme_rect
        p.setPen(QtGui.QPen(theme.with_alpha(th["main"], 0.45), 2 * s))
        p.setBrush(CARD_BG)
        p.drawRoundedRect(tr, 28 * s, 28 * s)
        p.setPen(th["deep"])
        p.setFont(theme.title_font(34 * s))
        p.drawText(QtCore.QRectF(tr.left() + 32 * s, tr.top() + 20 * s, 190 * s, 50 * s),
                   QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, "테마")
        p.setPen(theme.with_alpha(th["deep"], 0.8))
        p.setFont(theme.ui_font(16 * s, bold=False))
        p.drawText(QtCore.QRectF(tr.left() + 32 * s, tr.top() + 74 * s, 190 * s, 60 * s),
                   QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft, "메뉴·아이콘·커서\n색이 함께 바뀌어요")


# ── 메뉴 아이콘 (오른쪽 아래) ─────────────────────────────────────────────
class ScrollToggle(GazeButton):
    """메뉴 아이콘 위 스크롤 모드 ON/OFF 토글 (항상 보임).
    [↕ 스크롤  (스위치)] 모양. 켜짐 = 테마색 바탕 + 흰 글자 + 스위치 동그라미 오른쪽,
    꺼짐 = 흰색 반투명 바탕 + 진한 글자 + 회색 스위치 동그라미 왼쪽."""

    def __init__(self, parent):
        super().__init__("", parent)
        self.setFixedSize(SCROLL_W, SCROLL_H)
        self.setToolTip("스크롤 모드 켜기/끄기")

    def paintEvent(self, event):
        th = theme.current()
        s = self.width() / SCROLL_W              # 화면 전체 확대 중에는 작게 그려짐
        on = self.on
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(3 * s, 3 * s, -3 * s, -3 * s)
        h, cy = r.height(), r.center().y()
        hl = self.is_highlighted()
        p.setPen(QtGui.QPen(th["deep"] if hl else theme.with_alpha(th["main"], 0.8), (5 if hl else 2.5) * s))
        p.setBrush(theme.with_alpha(th["main"], 0.92) if on else QtGui.QColor(255, 255, 255, 230))
        p.drawRoundedRect(r, h / 2, h / 2)
        ink = QtGui.QColor(255, 255, 255) if on else th["deep"]

        # 위아래 화살표 (↕)
        ax = r.left() + 28 * s
        p.setPen(_pen(ink, 3.5 * s))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(ax - 7 * s, cy - 5 * s), QtCore.QPointF(ax, cy - 12 * s),
                                        QtCore.QPointF(ax + 7 * s, cy - 5 * s)]))
        p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(ax - 7 * s, cy + 5 * s), QtCore.QPointF(ax, cy + 12 * s),
                                        QtCore.QPointF(ax + 7 * s, cy + 5 * s)]))
        # 글자
        p.setPen(ink)
        p.setFont(theme.ui_font(20 * s))
        p.drawText(QtCore.QRectF(r.left() + 44 * s, r.top(), 76 * s, h),
                   QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, "스크롤")
        # 스위치 (안에 ON/OFF 글자)
        sw = QtCore.QRectF(r.right() - 10 * s - 74 * s, cy - 19 * s, 74 * s, 38 * s)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(th["deep"] if on else OFF_GRAY)
        p.drawRoundedRect(sw, 19 * s, 19 * s)
        p.setBrush(QtGui.QColor(255, 255, 255))
        p.drawEllipse(QtCore.QPointF(sw.right() - 19 * s if on else sw.left() + 19 * s, cy), 15 * s, 15 * s)
        p.setPen(QtGui.QColor(255, 255, 255))
        p.setFont(theme.ui_font(14 * s))
        label = QtCore.QRectF(sw.left() + 4 * s, sw.top(), 34 * s, sw.height()) if on else \
            QtCore.QRectF(sw.left() + 34 * s, sw.top(), 38 * s, sw.height())
        p.drawText(label, QtCore.Qt.AlignCenter, "ON" if on else "OFF")
        # 바라보는 동안 아래쪽에 진행 선
        if self.progress > 0:
            p.setPen(_pen(QtGui.QColor(255, 255, 255) if on else th["deep"], 4 * s))
            x0 = r.left() + h / 2
            p.drawLine(QtCore.QPointF(x0, r.bottom() - 6 * s),
                       QtCore.QPointF(x0 + (r.width() - h) * self.progress, r.bottom() - 6 * s))


class MenuIconButton(GazeButton):
    """테마색 둥근 메뉴 아이콘. 평소엔 ≡ 모양, 일시정지 중엔 자물쇠 모양 (+ 바라보는 동안 둘레 게이지).
    alpha(0~1)는 MenuDock이 커서와의 거리로 정해줌 (0 = 완전히 투명)."""

    def __init__(self, parent=None, size=ICON_PX):
        super().__init__("", parent)
        self.setFixedSize(size, size)
        self.locked = False
        self.alpha = 1.0

    def set_locked(self, locked):
        self.locked = locked
        self.dwell_sec = UNLOCK_DWELL_SEC if locked else DWELL_CLICK_SEC
        self.active_when_paused = locked         # 일시정지 중에도 시선으로 누를 수 있는 유일한 버튼
        self.update()

    def paintEvent(self, event):
        a = self.alpha
        if a <= 0.01:
            return                               # 완전히 투명할 때는 아무것도 안 그림
        th = theme.current()
        s = self.width() / ICON_PX               # 확대 중에는 아이콘이 작아지므로 선 굵기도 같이 줄임
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(7 * s, 7 * s, -7 * s, -7 * s)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, int(45 * a)))               # 살짝 그림자
        p.drawEllipse(r.translated(0, 3 * s))
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, int(240 * a)), 4 * s))
        p.setBrush(theme.with_alpha(th["main"], 0.85 * a))
        p.drawEllipse(r)
        if self.is_highlighted():                                      # 하이라이트: 진한 테마색 굵은 테두리
            p.setPen(QtGui.QPen(theme.with_alpha(th["deep"], a), 6 * s))
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawEllipse(r.adjusted(-2 * s, -2 * s, 2 * s, 2 * s))
        draw_icon(p, "lock" if self.locked else "menu", r.center(), 52 * s,
                  QtGui.QColor(255, 255, 255, int(255 * a)))
        if self.progress > 0:                    # 바라보는 동안 둘레 게이지 (자물쇠일 땐 커서가 숨겨져 있어서 여기서 보여줌)
            p.setPen(_pen(theme.with_alpha(th["deep"], a), 6 * s))
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawArc(r.adjusted(-3 * s, -3 * s, 3 * s, 3 * s), 90 * 16, int(-360 * 16 * self.progress))


class MenuDock(QtWidgets.QWidget):
    open_requested = QtCore.pyqtSignal()
    unlock_requested = QtCore.pyqtSignal()
    scroll_toggle_requested = QtCore.pyqtSignal()      # 아이콘 위 스크롤 ON/OFF 토글을 누름

    def __init__(self):
        super().__init__()
        setup_floating_window(self)
        self.icon = MenuIconButton(self)
        self.icon.clicked.connect(self._on_icon)
        self.scroll = ScrollToggle(self)
        self.scroll.clicked.connect(lambda: self.scroll_toggle_requested.emit())
        self.text = ""
        self.alpha = 1.0                  # 지금 보이는 정도 (0 = 완전히 투명)
        self.gaze = None                  # 마지막 커서 위치 (실제 좌표)
        self.view = None                  # 화면 전체 확대 중일 때 보이는 영역 (None = 확대 안 함)
        self.level = 1
        self.hold_until = 0.0             # 이 시각까지는 커서와 상관없이 보여줌
        self.menu_open = False            # 메뉴창이 열려 있으면 아이콘·상태 글자를 숨기고 토글만 남김
        self.fade_timer = QtCore.QTimer(self)
        self.fade_timer.timeout.connect(self._step)
        self.fade_timer.start(30)
        self._relayout()

    def showEvent(self, event):
        super().showEvent(event)
        self.hold_until = time.time() + INTRO_SEC   # 나타날 때마다 잠깐 보여줘서 위치를 알려줌

    def _on_icon(self):
        if self.icon.locked:
            self.unlock_requested.emit()
        else:
            self.open_requested.emit()

    # ── main.py에서 호출 ─────────────────────────────────────────
    def set_locked(self, locked):
        self.icon.set_locked(locked)
        self._relayout()

    def set_status_text(self, text):
        self.text = text
        self._relayout()

    def set_scroll(self, on):
        """스크롤 모드 표시 맞추기 (main.py가 켜고 끈 뒤 호출)."""
        self.scroll.set_on(on)

    def set_menu_open(self, menu_open):
        """메뉴창이 열려 있는 동안은 아이콘·상태 글자만 숨기고 스크롤 토글은 그대로 보여줌 (main.py의 _apply_state가 호출)."""
        if menu_open == self.menu_open:
            return
        self.menu_open = menu_open
        self.icon.setVisible(not menu_open)
        if not menu_open:
            self.hold_until = time.time() + INTRO_SEC    # 메뉴창을 닫으면 아이콘 위치를 잠깐 다시 보여줌
        self.update()

    def update_gaze(self, x, y):
        """커서 위치(실제 좌표). 가까울수록 아이콘이 진해짐."""
        self.gaze = (x, y)

    def set_view(self, rect, level):
        """화면 전체 확대 중이면 보이는 영역(rect)과 배율, 아니면 rect = None."""
        zoomed = rect is not None and level > 1
        new_view = QtCore.QRectF(rect) if zoomed else None
        if new_view == self.view and level == self.level:
            return
        self.view, self.level = new_view, (level if zoomed else 1)
        self._relayout()

    def home_center(self):
        """확대 안 했을 때 아이콘 중심의 화면 좌표 (화면 이동을 막을 지점으로도 씀)."""
        area = QtWidgets.QApplication.primaryScreen().availableGeometry()
        return (area.right() + 1 - EDGE_MARGIN - ICON_PX / 2, area.bottom() + 1 - EDGE_MARGIN - ICON_PX / 2)

    def refresh_theme(self):
        self.update()
        self.icon.update()
        self.scroll.update()

    # ── 배치 ─────────────────────────────────────────────────────
    def _pill_size(self):
        if not self.text:
            return 0, 0
        fm = QtGui.QFontMetricsF(theme.ui_font(17))
        return int(fm.horizontalAdvance(self.text) + 34), 42

    def _relayout(self):
        if self.view is not None:                    # 확대 중: [토글][아이콘], 1/배율 크기로, 보이는 영역 오른쪽 아래
            k = 1.0 / self.level
            size = max(28, int(ICON_PX * k))
            tw, tth, tg = max(50, int(SCROLL_W * k)), max(16, int(SCROLL_H * k)), int(SCROLL_GAP * k)
            self.icon.setFixedSize(size, size)
            self.scroll.setFixedSize(tw, tth)
            w, h = tw + tg + size, size
            self.setFixedSize(w, h)
            self.icon.move(w - size, 0)
            self.scroll.move(0, (size - tth) // 2)
            hx, hy = self.home_center()
            geo = QtWidgets.QApplication.primaryScreen().geometry()
            cx = self.view.x() + (hx - geo.x()) / self.level     # 아이콘 중심이 와야 할 곳
            cy = self.view.y() + (hy - geo.y()) / self.level
            self.move(int(cx + size / 2 - w), int(cy + size / 2 - h))
        else:                                        # 평소: 위 [상태 글자] / 아래 [스크롤 토글][아이콘], 오른쪽 아래
            self.icon.setFixedSize(ICON_PX, ICON_PX)
            self.scroll.setFixedSize(SCROLL_W, SCROLL_H)
            pw, ph = self._pill_size()
            top = ph + 8 if pw else 0                # 상태 글자가 있으면 그 높이만큼 아래 줄을 내림
            w = max(SCROLL_W + SCROLL_GAP + ICON_PX, pw)
            h = top + ICON_PX
            self.setFixedSize(w, h)
            self.icon.move(w - ICON_PX, top)
            self.scroll.move(w - ICON_PX - SCROLL_GAP - SCROLL_W, top + (ICON_PX - SCROLL_H) // 2)
            area = QtWidgets.QApplication.primaryScreen().availableGeometry()
            self.move(area.right() + 1 - EDGE_MARGIN - w, area.bottom() + 1 - EDGE_MARGIN - h)
        self.update()

    # ── 나타나기/사라지기 ────────────────────────────────────────
    def _target_alpha(self):
        if self.icon.locked or time.time() < self.hold_until:
            return 1.0
        if self.gaze is None:
            return 0.0
        c = self.icon.mapToGlobal(QtCore.QPoint(self.icon.width() // 2, self.icon.height() // 2))
        d = math.hypot(self.gaze[0] - c.x(), self.gaze[1] - c.y())
        k = 1.0 / self.level                          # 확대 중에는 거리도 배율만큼 줄여서 계산
        near, far = NEAR_PX * k, FAR_PX * k
        return max(0.0, min(1.0, (far - d) / (far - near)))

    def _step(self):
        target = self._target_alpha()
        new = target if abs(target - self.alpha) < 0.02 else self.alpha + (target - self.alpha) * 0.25
        if new != self.alpha:
            self.alpha = new
            self.icon.alpha = new
            self.icon.update()
            self.update()

    def paintEvent(self, event):
        pw, ph = self._pill_size()
        a = self.alpha
        if self.view is not None or self.menu_open or not pw or a <= 0.01:
            return
        th = theme.current()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = QtCore.QRectF(self.width() - pw + 1, 1, pw - 2, ph)   # 아이콘 바로 위, 오른쪽 끝 맞춤
        p.setPen(QtGui.QPen(theme.with_alpha(th["main"], 0.7 * a), 2))
        p.setBrush(QtGui.QColor(255, 255, 255, int(220 * a)))
        p.drawRoundedRect(rect, ph / 2, ph / 2)
        p.setPen(theme.with_alpha(th["deep"], a))
        p.setFont(theme.ui_font(17))
        p.drawText(rect, QtCore.Qt.AlignCenter, self.text)
