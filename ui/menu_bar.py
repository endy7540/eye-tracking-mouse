# -*- coding: utf-8 -*-
"""
menu_bar.py — 화면 오른쪽 아래 메뉴 아이콘 + 세로 스크롤 토글 + 화면 가운데 반투명 메뉴창 (테마색)

MenuDock  (평소에 떠 있는 부분 — 화면 오른쪽 끝 세로줄)
    - 맨 아래: 테마색 둥근 메뉴 아이콘(지름 ICON_PX). 누르면(클릭 또는 1.2초 응시) 메뉴창이 열림
      평소엔 완전히 투명해서 안 보이고, 커서(시선)가 가까이 오면 서서히 나타남 (NEAR_PX 안 = 완전히 보임)
      처음 나타날 때는 어디 있는지 알 수 있게 INTRO_SEC 동안 보여줬다가 사라짐
    - 아이콘 바로 위: 세로형 스크롤 ON/OFF 토글 (ScrollToggle, SCROLL_W×SCROLL_H). 아이콘과 달리 항상 보임.
      누르면(클릭 또는 1.2초 응시) scroll_toggle_requested 신호 → main.py가 켜고 끈 뒤 set_scroll()로 표시를 맞춤.
      ★ 위치를 화면 오른쪽 끝 세로줄(가로 90% 바깥)에 둔 이유: 팀원분 그림의 스크롤 영역(위·아래 15%, 가로 10~90%),
        브라우저 툴바, 작업표시줄, 메뉴창 어느 것과도 겹치지 않는 자리라서.
    - 토글 왼쪽: 지금 켜져 있는 모드를 짧게 표시하는 상태 글자 (아이콘과 같이 나타남)
    - 일시정지 중에는 아이콘이 자물쇠로 바뀌고 "일시정지 중" 문구가 뜸. 일시정지 직후 INTRO_SEC 동안 보여준 뒤에는
      평소처럼 시선이 멀어지면 투명해지고 가까이 오면 나타남. 스크롤 토글은 일시정지 중 숨김.
      자물쇠를 3초 바라보면 다시 활성화
    - 메뉴창이 열려 있는 동안(set_menu_open(True))은 아이콘·상태 글자만 숨기고 스크롤 토글은 그대로 둠

MenuPanel (메뉴창 — 화면 가운데에 크게, 테마색 반투명)
    ★ 메뉴창 안의 버튼은 전부 "윙크로만" 눌림 (wink_only). 바라보면 하이라이트 + 위에 "윙크하면 선택" 표시가 뜨고,
      응시 게이지는 차지 않음. 윙크 설정이 "끔"이어도 메뉴창 안에서는 윙크가 항상 됨 (main.py가 처리).
      마우스 클릭은 그대로 됨.
    - 오른쪽 위 X 버튼(크롬 창처럼): 메뉴창 닫기
    - 첫 화면: 세로로 긴 큰 카드 5개 (각 카드 아래쪽에 지금 상태 표시)
        1. 커서 투명도 (-/+ 누를 때마다 10%씩, 높을수록 투명)
        2. 일시정지    (커서만 숨김, 자물쇠 3초 응시로 다시 활성화)
        3. 키보드      (화상 키보드 열기/닫기)
        4. 시선 잔상   (ON/OFF)
        5. 설정        → 설정 화면으로
    - 설정 화면: 뒤로 · 캘리브레이션 다시 하기 · 윙크 클릭(아무 쪽 → 왼눈 → 오른눈 → 끔) · 응시 클릭(ON/OFF)
    - 아래 줄: 테마 고르기(무광 바둑알 6개) · 상태 확인 · 오른쪽 아래 종료
      종료는 실수로 꺼지지 않게 두 번 눌러야 함 (첫 번째 → "한 번 더 윙크하면 종료", 3초 안에 한 번 더)
    - 크기: 1920×1080 화면 기준 1620×750. 화면이 작으면 비율대로 줄어들고, 오른쪽 스크롤 토글과 겹치지 않게 맞춤 (_relayout)

테마는 메뉴창·메뉴 아이콘·스크롤 토글·커서·화상 키보드에 적용됩니다 (theme.current()).
상태 확인 창이 쓰는 paint_panel_background()와 GazeButton 기본 모양은 예전 갈색 그대로 둡니다.

이 파일의 위젯들은 "버튼이 눌렸다"는 신호만 내보내고, 실제로 무엇을 할지는 main.py가 정합니다.

[제출 전] 상태 확인 버튼은 개발할 때만 쓰는 것이라 SHOW_STATUS_BUTTON = False로 바꾸면 메뉴창에서 사라집니다.
"""
import math
import time

from PyQt5 import QtWidgets, QtCore, QtGui

from . import theme
from .gaze_widgets import GazeButton, setup_floating_window, DWELL_CLICK_SEC
from .seal_cursor import MIN_OPACITY, MAX_OPACITY, SWATCH_GLOSS, paint_stone

SHOW_STATUS_BUTTON = True # [개발할 때만] 상태 확인 버튼 보이기 — 제출할 때 False로

EDGE_MARGIN = 24          # 화면 가장자리와의 간격
UNLOCK_DWELL_SEC = 3.0    # 자물쇠를 이만큼 바라보면 일시정지 해제 (요구사항: 3초)
QUIT_CONFIRM_SEC = 3.0    # 종료: 첫 번째 누른 뒤 이 시간 안에 한 번 더 누르면 종료

ICON_PX = 110             # 메뉴 아이콘 지름
NEAR_PX = 170             # 커서가 아이콘 중심에서 이 거리 안이면 완전히 보임
FAR_PX = 380              # 이 거리 밖이면 완전히 투명 (사이에서는 서서히)
INTRO_SEC = 3.0           # 아이콘이 처음 나타날 때 이 시간 동안은 보여줌 (어디 있는지 알 수 있게)
SCROLL_W, SCROLL_H = 110, 170   # 세로형 스크롤 ON/OFF 토글 크기 (메뉴 아이콘 바로 위, 아이콘과 같은 폭)
SCROLL_GAP = 14           # 토글과 메뉴 아이콘 사이 간격
PANEL_GAP = 16            # 메뉴창 오른쪽 끝과 스크롤 토글 사이 최소 간격

PANEL_BG_ALPHA = 0.30     # 메뉴창·키보드 배경 진하기 (많이 투명하게 — 뒤 화면이 비쳐 보임)
CARD_BG = QtGui.QColor(255, 255, 255, 205)   # 카드 바탕 (뒤가 비쳐도 글씨가 읽히게 흰색 반투명)
BASE_W, BASE_H = 1620, 750                   # 메뉴창 기준 크기 (1920×1080 화면)
CARD_H = 400              # 카드 높이 (기준 크기)
HINT_PAD = 26             # 카드 위쪽 "윙크하면 선택" 표시가 들어갈 여유 (카드 위젯이 이만큼 위로 더 큼)
QUIT_RED = QtGui.QColor(222, 70, 70)
OFF_GRAY = QtGui.QColor(160, 166, 176)
WINK_NAMES = {"both": "아무 쪽 눈", "left": "왼눈만", "right": "오른눈만", "off": "끔"}


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
    """상태 확인 창: 반투명 둥근 사각형 배경 (갈색 — 테마와 무관)."""
    p = QtGui.QPainter(widget)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setPen(QtGui.QPen(theme.PANEL_EDGE, 2))
    p.setBrush(theme.PANEL_BG)
    p.drawRoundedRect(QtCore.QRectF(widget.rect()).adjusted(1, 1, -1, -1), radius, radius)


def paint_theme_panel(widget, radius=26, width=3):
    """화상 키보드: 테마색 반투명 둥근 사각형 배경 (메뉴창과 같은 느낌)."""
    th = theme.current()
    p = QtGui.QPainter(widget)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setPen(QtGui.QPen(theme.with_alpha(th["main"], 0.95), width))
    p.setBrush(theme.with_alpha(th["main"], PANEL_BG_ALPHA))
    p.drawRoundedRect(QtCore.QRectF(widget.rect()).adjusted(1.5, 1.5, -1.5, -1.5), radius, radius)


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
    if kind == "opacity":                                # 반쯤 채운 원 (투명도)
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
    elif kind == "gear":                                 # 톱니바퀴 (설정) — 가운데 구멍은 뚫어서 그림
        path = QtGui.QPainterPath()
        teeth, pts = 8, []
        for i in range(teeth * 4):
            a = math.radians(i * 360 / (teeth * 4) - 90 + 360 / (teeth * 8))
            r = 30 if (i % 4) in (1, 2) else 22
            pts.append(P(r * math.cos(a), r * math.sin(a)))
        path.addPolygon(QtGui.QPolygonF(pts))
        path.closeSubpath()
        path.addEllipse(P(0, 0), 9 * u, 9 * u)
        path.setFillRule(QtCore.Qt.OddEvenFill)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(color)
        p.drawPath(path)
    elif kind == "back":                                 # 뒤로 (<)
        p.setPen(_pen(color, 8 * u))
        p.drawPolyline(QtGui.QPolygonF([P(10, -18), P(-10, 0), P(10, 18)]))
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


def paint_card(p, r, th, highlighted, s, radius=32):
    """카드 바탕: 흰색 반투명 + 테마색 테두리. 시선(또는 마우스)이 올라가면 굵은 진한 테두리 + 둘레 빛."""
    if highlighted:
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(theme.with_alpha(th["main"], 0.35))
        p.drawRoundedRect(r.adjusted(-5 * s, -5 * s, 5 * s, 5 * s), (radius + 5) * s, (radius + 5) * s)
        p.setPen(QtGui.QPen(th["deep"], 7 * s))
    else:
        p.setPen(QtGui.QPen(theme.with_alpha(th["main"], 0.45), 2 * s))
    p.setBrush(CARD_BG)
    p.drawRoundedRect(r, radius * s, radius * s)


def paint_chip(p, cx, cy, text, dot, th, s, px=22):
    """작은 상태 알약: 색 점 + 글자. 예) ● 실행 중"""
    f = theme.ui_font(px * s)
    w = QtGui.QFontMetricsF(f).horizontalAdvance(text) + 2.4 * px * s
    h = 1.9 * px * s
    rect = QtCore.QRectF(cx - w / 2, cy - h / 2, w, h)
    p.setPen(QtGui.QPen(theme.with_alpha(th["main"], 0.5), 2 * s))
    p.setBrush(QtGui.QColor(255, 255, 255, 235))
    p.drawRoundedRect(rect, h / 2, h / 2)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(dot)
    p.drawEllipse(QtCore.QPointF(rect.left() + 0.95 * px * s, cy), 0.3 * px * s, 0.3 * px * s)
    p.setPen(th["deep"])
    p.setFont(f)
    p.drawText(rect.adjusted(1.55 * px * s, 0, -0.45 * px * s, 0), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, text)


def paint_toggle(p, cx, cy, on, th, s, k=1.3):
    """ON/OFF 스위치. 켜짐 = 테마색 + 오른쪽 동그라미, 꺼짐 = 회색 + 왼쪽 동그라미."""
    w, h = 104 * k * s, 50 * k * s
    rect = QtCore.QRectF(cx - w / 2, cy - h / 2, w, h)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(th["main"] if on else OFF_GRAY)
    p.drawRoundedRect(rect, h / 2, h / 2)
    knob_x = rect.right() - h / 2 if on else rect.left() + h / 2
    p.setBrush(QtGui.QColor(255, 255, 255))
    p.drawEllipse(QtCore.QPointF(knob_x, cy), h / 2 - 6 * s, h / 2 - 6 * s)
    p.setPen(QtGui.QColor(255, 255, 255))
    p.setFont(theme.ui_font(19 * k * s))
    label = QtCore.QRectF(rect.left() + 8 * s, rect.top(), w - h - 4 * s, h) if on else \
        QtCore.QRectF(rect.left() + h - 2 * s, rect.top(), w - h - 4 * s, h)
    p.drawText(label, QtCore.Qt.AlignCenter, "ON" if on else "OFF")


def paint_wink_hint(p, cx, cy, th, s):
    """하이라이트된 카드 위에 뜨는 "윙크하면 선택" 알약 (메뉴창 안에서는 윙크로만 눌리므로)."""
    f = theme.ui_font(19 * s)
    text = "윙크하면 선택"
    w = QtGui.QFontMetricsF(f).horizontalAdvance(text) + 74 * s
    h = 46 * s
    rect = QtCore.QRectF(cx - w / 2, cy - h / 2, w, h)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(theme.with_alpha(th["deep"], 0.94))
    p.drawRoundedRect(rect, h / 2, h / 2)
    white = QtGui.QColor(255, 255, 255)
    ix = rect.left() + 26 * s
    p.setPen(_pen(white, 2.5 * s))
    p.setBrush(QtCore.Qt.NoBrush)
    p.drawEllipse(QtCore.QPointF(ix, cy), 6 * s, 6 * s)
    path = QtGui.QPainterPath(QtCore.QPointF(ix + 10 * s, cy - 1 * s))
    path.quadTo(QtCore.QPointF(ix + 15 * s, cy + 5 * s), QtCore.QPointF(ix + 20 * s, cy - 1 * s))
    p.drawPath(path)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(white)
    p.drawEllipse(QtCore.QPointF(ix, cy), 2.4 * s, 2.4 * s)
    p.setPen(white)
    p.setFont(f)
    p.drawText(rect.adjusted(46 * s, 0, -14 * s, 0), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, text)


def _card_body(widget, s):
    """카드 위젯 안에서 실제 카드가 그려지는 사각형 (위쪽 HINT_PAD는 '윙크하면 선택' 표시 자리)."""
    return QtCore.QRectF(widget.rect()).adjusted(5 * s, (HINT_PAD + 5) * s, -5 * s, -5 * s)


def _paint_card_head(p, r, th, s, kind, title):
    """카드 위쪽 공통: 연한 동그라미 위 아이콘 + 이름."""
    ic = QtCore.QPointF(r.center().x(), r.top() + 104 * s)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(th["light"])
    p.drawEllipse(ic, 74 * s, 74 * s)
    draw_icon(p, kind, ic, 90 * s, th["deep"])
    p.setPen(th["deep"])
    p.setFont(theme.ui_font(34 * s))
    p.drawText(QtCore.QRectF(r.left(), r.top() + 190 * s, r.width(), 48 * s), QtCore.Qt.AlignCenter, title)


# ── 메뉴창 부품 (전부 윙크로만 눌림) ──────────────────────────────────────
class ActionCard(GazeButton):
    """누르면 바로 동작하는 세로 카드. 위에서부터: 아이콘 → 이름 → 설명 → 지금 상태(알약 또는 ON/OFF 스위치)."""

    def __init__(self, parent, kind, title, sub):
        super().__init__("", parent)
        self.wink_only = True
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
        r = _card_body(self, s)
        hl = self.is_highlighted()
        paint_card(p, r, th, hl, s)
        _paint_card_head(p, r, th, s, self.kind, self.title)
        p.setPen(theme.with_alpha(th["deep"], 0.8))
        p.setFont(theme.ui_font(21 * s, bold=False))
        p.drawText(QtCore.QRectF(r.left() + 8 * s, r.top() + 240 * s, r.width() - 16 * s, 40 * s),
                   QtCore.Qt.AlignCenter, self.sub)
        fy = r.top() + 330 * s
        if self.footer[0] == "toggle":
            paint_toggle(p, r.center().x(), fy, self.footer[1], th, s)
        elif self.footer[1]:
            paint_chip(p, r.center().x(), fy, self.footer[1], self.footer[2], th, s)
        if hl:
            paint_wink_hint(p, r.center().x(), r.top() - 2 * s, th, s)


class StepButton(GazeButton):
    """카드 안의 둥근 -/+ 버튼 (커서 투명도)."""

    def __init__(self, parent, sign):
        super().__init__("", parent)
        self.wink_only = True
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
        p.setPen(_pen(th["deep"], 7 * s))
        p.drawLine(QtCore.QPointF(c.x() - d, c.y()), QtCore.QPointF(c.x() + d, c.y()))
        if self.sign == "+":
            p.drawLine(QtCore.QPointF(c.x(), c.y() - d), QtCore.QPointF(c.x(), c.y() + d))


class StepperCard(QtWidgets.QWidget):
    """-/+ 버튼으로 값을 바꾸는 세로 카드 (커서 투명도). 카드 자체는 눌리지 않고 버튼만 눌림."""

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
        size = int(76 * s)
        cx, cy = self.width() / 2, (HINT_PAD + 5 + 346) * s
        self.minus.setFixedSize(size, size)
        self.plus.setFixedSize(size, size)
        self.minus.move(int(cx - 62 * s - size / 2), int(cy - size / 2))
        self.plus.move(int(cx + 62 * s - size / 2), int(cy - size / 2))

    def _highlighted(self):
        return any(b.is_highlighted() and b.isEnabled() for b in (self.minus, self.plus))

    def paintEvent(self, event):
        th, s = theme.current(), self.s
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = _card_body(self, s)
        hl = self._highlighted()
        paint_card(p, r, th, hl, s)
        _paint_card_head(p, r, th, s, self.kind, self.title)
        p.setPen(th["deep"])
        p.setFont(theme.title_font(42 * s))
        p.drawText(QtCore.QRectF(r.left(), r.top() + 236 * s, r.width(), 50 * s), QtCore.Qt.AlignCenter, self.value)
        p.setPen(theme.with_alpha(th["deep"], 0.75))
        p.setFont(theme.ui_font(18 * s, bold=False))
        p.drawText(QtCore.QRectF(r.left(), r.top() + 282 * s, r.width(), 28 * s), QtCore.Qt.AlignCenter, self.hint)
        if hl:
            paint_wink_hint(p, r.center().x(), r.top() - 2 * s, th, s)


class ThemeSwatch(GazeButton):
    """테마 고르는 동그라미 = 무광 바둑알. 고른 테마는 바깥 고리 + 체크 표시."""

    def __init__(self, parent, key):
        super().__init__("", parent)
        self.wink_only = True
        self.key = key
        self.selected = False
        self.s = 1.0

    def paintEvent(self, event):
        s = self.s
        th = theme.current()                         # 글자색은 지금 테마를 따름
        own = theme.theme_colors(self.key)           # 바둑알 색은 이 버튼의 테마
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
            p.drawEllipse(c, R + 10 * s, R + 10 * s)
        paint_stone(p, c.x(), c.y(), R, own, 0.95, SWATCH_GLOSS)
        if self.selected:
            p.setPen(_pen(QtGui.QColor(255, 255, 255), 6 * s))
            p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(c.x() - 13 * s, c.y()),
                                            QtCore.QPointF(c.x() - 3 * s, c.y() + 10 * s),
                                            QtCore.QPointF(c.x() + 15 * s, c.y() - 10 * s)]))
        p.setPen(th["deep"] if self.selected else theme.with_alpha(th["deep"], 0.7))
        p.setFont(theme.ui_font(18 * s, bold=self.selected))
        p.drawText(QtCore.QRectF(0, self.height() * 0.82 - 16 * s, self.width(), 32 * s),
                   QtCore.Qt.AlignCenter, own["name"])


class PanelCloseButton(GazeButton):
    """메뉴창 오른쪽 위 X (크롬 창처럼): 평소엔 흰 동그라미 위 X, 시선/마우스가 올라가면 빨간 배경 + 흰 X."""

    def __init__(self, parent):
        super().__init__("", parent)
        self.wink_only = True
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
        p.setPen(_pen(QtGui.QColor(255, 255, 255) if hl else th["deep"], 5 * s))
        c, d = r.center(), r.width() * 0.19
        p.drawLine(QtCore.QPointF(c.x() - d, c.y() - d), QtCore.QPointF(c.x() + d, c.y() + d))
        p.drawLine(QtCore.QPointF(c.x() - d, c.y() + d), QtCore.QPointF(c.x() + d, c.y() - d))


class BottomButton(GazeButton):
    """아래 줄의 큰 버튼: 종료(빨강, 두 번 눌러야 종료) / 상태 확인."""

    def __init__(self, parent, kind, label):
        super().__init__("", parent)
        self.wink_only = True
        self.kind, self.label = kind, label
        self.armed = False            # [종료] 한 번 눌러서 "한 번 더 누르면 종료" 상태
        self.s = 1.0

    def paintEvent(self, event):
        th, s = theme.current(), self.s
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(5 * s, 5 * s, -5 * s, -5 * s)
        hl = self.is_highlighted()
        if self.kind == "power":                                   # 종료
            color = QtGui.QColor(255, 255, 255) if self.armed else QUIT_RED
            p.setPen(QtGui.QPen(QUIT_RED, (6 if hl else 3) * s))
            p.setBrush(QUIT_RED if self.armed else (QtGui.QColor(255, 236, 236, 235) if hl else CARD_BG))
            p.drawRoundedRect(r, 28 * s, 28 * s)
        else:                                                      # 상태 확인
            color = th["deep"]
            p.setPen(QtGui.QPen(th["deep"] if hl else theme.with_alpha(th["main"], 0.6), (6 if hl else 2) * s))
            p.setBrush(QtGui.QColor(th["light"]) if self.on else CARD_BG)
            p.drawRoundedRect(r, 28 * s, 28 * s)
        if self.kind == "power" and self.armed:
            p.setPen(color)
            p.setFont(theme.ui_font(19 * s))
            p.drawText(r.adjusted(10 * s, 0, -10 * s, 0), QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap,
                       "한 번 더\n윙크하면 종료")
            return
        draw_icon(p, self.kind, QtCore.QPointF(r.center().x(), r.top() + r.height() * 0.42), 54 * s, color)
        p.setPen(color)
        p.setFont(theme.title_font(28 * s) if self.kind == "power" else theme.ui_font(21 * s))
        p.drawText(QtCore.QRectF(r.left(), r.top() + r.height() * 0.66, r.width(), r.height() * 0.28),
                   QtCore.Qt.AlignCenter, self.label)


class MenuPanel(QtWidgets.QWidget):
    close_requested = QtCore.pyqtSignal()
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
        self.page = "main"            # "main" = 첫 화면 / "settings" = 설정 화면
        self.header_rect = QtCore.QRectF()
        self.theme_rect = QtCore.QRectF()

        self.close_btn = PanelCloseButton(self)
        self.close_btn.clicked.connect(lambda: self.close_requested.emit())

        # 첫 화면: 세로 카드 5개
        self.opacity_card = StepperCard(self, "opacity", "커서 투명도")
        self.pause_card = ActionCard(self, "pause", "일시정지", "커서 숨기기")
        self.keyboard_card = ActionCard(self, "keyboard", "키보드", "화상 키보드")
        self.trail_card = ActionCard(self, "trail", "시선 잔상", "지나간 길 표시")
        self.settings_card = ActionCard(self, "gear", "설정", "캘리브레이션 · 윙크 · 응시")
        self.main_cards = [self.opacity_card, self.pause_card, self.keyboard_card,
                           self.trail_card, self.settings_card]
        self.opacity_card.minus.clicked.connect(lambda: self.transparency_down_requested.emit())
        self.opacity_card.plus.clicked.connect(lambda: self.transparency_up_requested.emit())
        self.pause_card.clicked.connect(lambda: self.pause_requested.emit())
        self.keyboard_card.clicked.connect(lambda: self.keyboard_toggle_requested.emit())
        self.trail_card.clicked.connect(lambda: self.trail_toggle_requested.emit())
        self.settings_card.clicked.connect(lambda: self.show_page("settings"))

        # 설정 화면: 뒤로 + 카드 3개
        self.back_card = ActionCard(self, "back", "뒤로", "메뉴로 돌아가기")
        self.calib_card = ActionCard(self, "calib", "캘리브레이션", "다시 맞추기")
        self.wink_card = ActionCard(self, "wink", "윙크 클릭", "누르면 바뀌어요")
        self.dwell_card = ActionCard(self, "dwell", "응시 클릭", "메뉴 밖에서 보면 클릭")
        self.settings_cards = [self.back_card, self.calib_card, self.wink_card, self.dwell_card]
        self.calib_card.set_chip("두더지 잡기", theme.YELLOW)
        self.back_card.clicked.connect(lambda: self.show_page("main"))
        self.calib_card.clicked.connect(lambda: self.recalibrate_requested.emit())
        self.wink_card.clicked.connect(lambda: self.wink_toggle_requested.emit())
        self.dwell_card.clicked.connect(lambda: self.dwell_toggle_requested.emit())

        # 아래 줄: 테마 바둑알 6개 · 상태 확인 · 종료
        self.swatches = []
        for t in theme.THEMES:
            sw = ThemeSwatch(self, t["key"])
            sw.clicked.connect(lambda _=False, k=t["key"]: self.theme_selected.emit(k))
            self.swatches.append(sw)
        self.status_btn = BottomButton(self, "status", "상태 확인")
        self.status_btn.clicked.connect(lambda: self.status_requested.emit())
        self.status_btn.setVisible(SHOW_STATUS_BUTTON)
        self.quit_btn = BottomButton(self, "power", "종료")
        self.quit_btn.clicked.connect(self._on_quit)
        self.quit_timer = QtCore.QTimer(self)
        self.quit_timer.setSingleShot(True)
        self.quit_timer.timeout.connect(self._disarm_quit)

        self._relayout()
        self.show_page("main")

    # ── 화면 전환 ────────────────────────────────────────────────
    def show_page(self, page):
        """"main"(첫 화면) / "settings"(설정 화면) 전환."""
        self.page = page
        for c in self.main_cards:
            c.setVisible(page == "main")
        for c in self.settings_cards:
            c.setVisible(page == "settings")
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.show_page("main")                  # 메뉴창을 열 때는 항상 첫 화면부터
        self._disarm_quit()

    # ── 종료 (두 번 눌러야 종료) ──────────────────────────────────
    def _on_quit(self):
        if self.quit_btn.armed:
            self.quit_requested.emit()
        else:
            self.quit_btn.armed = True          # 첫 번째: "한 번 더 윙크하면 종료"
            self.quit_btn.update()
            self.quit_timer.start(int(QUIT_CONFIRM_SEC * 1000))

    def _disarm_quit(self):
        self.quit_btn.armed = False
        self.quit_btn.update()

    # ── 배치 ─────────────────────────────────────────────────────
    def _relayout(self):
        """화면 크기에 맞춰 메뉴창 크기(s 배율)와 안쪽 부품 위치를 정함. 1920×1080에서 s = 1.
        메뉴창이 화면 오른쪽 끝의 스크롤 토글과 겹치지 않도록 가로 크기도 제한함."""
        area = QtWidgets.QApplication.primaryScreen().availableGeometry()
        toggle_left = area.right() + 1 - EDGE_MARGIN - ICON_PX
        max_w = 2 * (toggle_left - PANEL_GAP - area.center().x())        # 가운데 정렬이라 양쪽으로 같은 만큼
        s = min(area.width() * 0.94 / BASE_W, area.height() * 0.92 / BASE_H, max_w / BASE_W, 1.0)
        s = max(s, 0.4)
        self.s = s
        W, H = int(BASE_W * s), int(BASE_H * s)
        self.setFixedSize(W, H)
        pad, gap = 40 * s, 24 * s

        # 머리줄 + 오른쪽 위 X
        cb = int(64 * s)
        self.header_rect = QtCore.QRectF(pad, pad, W - 2 * pad - cb - 16 * s, 76 * s)
        self.close_btn.s = s
        self.close_btn.setFixedSize(cb, cb)
        self.close_btn.move(int(W - pad - cb), int(pad + 6 * s))

        # 카드 줄 (카드 위젯은 '윙크하면 선택' 표시 자리만큼 위로 더 큼)
        top = pad + 76 * s + 22 * s - HINT_PAD * s
        ch = (CARD_H + HINT_PAD) * s
        cw = (W - 2 * pad - 4 * gap) / 5
        for i, card in enumerate(self.main_cards):
            card.setGeometry(int(pad + i * (cw + gap)), int(top), int(cw), int(ch))
            card.set_scale(s)
        total = 4 * cw + 3 * gap
        x0 = pad + (W - 2 * pad - total) / 2
        for i, card in enumerate(self.settings_cards):
            card.setGeometry(int(x0 + i * (cw + gap)), int(top), int(cw), int(ch))
            card.set_scale(s)

        # 아래 줄 (오른쪽부터: 종료 → 상태 확인 → 남은 자리에 테마)
        by, bh, bw = pad + 76 * s + 22 * s + CARD_H * s + 22 * s, 150 * s, 190 * s
        right = W - pad
        for btn, show in ((self.quit_btn, True), (self.status_btn, SHOW_STATUS_BUTTON)):
            if show:
                btn.s = s
                btn.setGeometry(int(right - bw), int(by), int(bw), int(bh))
                right -= bw + 18 * s
        self.theme_rect = QtCore.QRectF(pad, by, right - pad, bh)
        sw_x = pad + 250 * s
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
        for w in self.main_cards + self.settings_cards + self.swatches + [self.close_btn, self.status_btn,
                                                                           self.quit_btn]:
            w.update()
        self.opacity_card.minus.update()
        self.opacity_card.plus.update()

    # ── 상태 표시 ────────────────────────────────────────────────
    def update_state(self, st):
        """main.py가 모드가 바뀔 때마다 호출.
        st = {"paused", "trail", "keyboard", "wink", "dwell", "status", "opacity", "theme"}"""
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
        self.settings_card.set_chip("들어가기 ›", theme.current()["main"])
        self.back_card.set_chip("메뉴", theme.current()["main"])
        self.wink_card.set_chip(WINK_NAMES.get(st["wink"], "아무 쪽 눈"),
                                theme.GREEN if st["wink"] != "off" else OFF_GRAY)
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
        title = "메뉴 › 설정" if self.page == "settings" else "메뉴"
        hint = "보고 윙크하면 선택돼요  (메뉴 안에서는 응시 클릭 꺼짐)"
        tf = theme.title_font(44 * s)
        tw = QtGui.QFontMetricsF(tf).horizontalAdvance(title)
        p.setPen(th["deep"])
        p.setFont(tf)
        p.drawText(QtCore.QRectF(hr.left() + 32 * s, hr.top(), tw + 10 * s, hr.height()),
                   QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, title)
        p.setPen(theme.with_alpha(th["deep"], 0.85))
        p.setFont(theme.ui_font(22 * s))
        p.drawText(QtCore.QRectF(hr.left() + 60 * s + tw, hr.top(), hr.width() - 80 * s - tw, hr.height()),
                   QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, hint)

        # 테마 칸 바탕 + 제목 (바둑알들은 ThemeSwatch가 따로 그림)
        tr = self.theme_rect
        p.setPen(QtGui.QPen(theme.with_alpha(th["main"], 0.45), 2 * s))
        p.setBrush(CARD_BG)
        p.drawRoundedRect(tr, 28 * s, 28 * s)
        p.setPen(th["deep"])
        p.setFont(theme.title_font(34 * s))
        p.drawText(QtCore.QRectF(tr.left() + 32 * s, tr.top() + 20 * s, 200 * s, 50 * s),
                   QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, "테마")
        p.setPen(theme.with_alpha(th["deep"], 0.8))
        p.setFont(theme.ui_font(16 * s, bold=False))
        p.drawText(QtCore.QRectF(tr.left() + 32 * s, tr.top() + 74 * s, 210 * s, 60 * s),
                   QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft, "메뉴·아이콘·커서\n키보드 색이 함께 바뀌어요")


# ── 메뉴 아이콘·스크롤 토글 (화면 오른쪽 끝 세로줄) ───────────────────────────
class ScrollToggle(GazeButton):
    """메뉴 아이콘 위 세로형 스크롤 모드 ON/OFF 토글 (항상 보임). 메뉴창 밖이라 1.2초 응시로도 눌림.
    위에서부터: 위아래 화살표(↕) → "스크롤" → 스위치(ON/OFF).
    켜짐 = 테마색 바탕 + 흰 글자 + 스위치 동그라미 오른쪽, 꺼짐 = 흰색 바탕 + 진한 글자 + 회색 스위치."""

    def __init__(self, parent):
        super().__init__("", parent)
        self.setFixedSize(SCROLL_W, SCROLL_H)
        self.setToolTip("스크롤 모드 켜기/끄기")

    def paintEvent(self, event):
        th = theme.current()
        s = self.width() / SCROLL_W
        on = self.on
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(3 * s, 3 * s, -3 * s, -3 * s)
        hl = self.is_highlighted()
        p.setPen(QtGui.QPen(th["deep"] if hl else theme.with_alpha(th["main"], 0.8), (5 if hl else 2.5) * s))
        p.setBrush(theme.with_alpha(th["main"], 0.92) if on else QtGui.QColor(255, 255, 255, 232))
        p.drawRoundedRect(r, 30 * s, 30 * s)
        ink = QtGui.QColor(255, 255, 255) if on else th["deep"]
        cx, top = r.center().x(), r.top()

        # 위아래 화살표 (↕)
        p.setPen(_pen(ink, 4.5 * s))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(cx - 11 * s, top + 34 * s), QtCore.QPointF(cx, top + 23 * s),
                                        QtCore.QPointF(cx + 11 * s, top + 34 * s)]))
        p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(cx - 11 * s, top + 48 * s), QtCore.QPointF(cx, top + 59 * s),
                                        QtCore.QPointF(cx + 11 * s, top + 48 * s)]))
        # 글자
        p.setPen(ink)
        p.setFont(theme.ui_font(21 * s))
        p.drawText(QtCore.QRectF(r.left(), top + 72 * s, r.width(), 36 * s), QtCore.Qt.AlignCenter, "스크롤")
        # 스위치 (안에 ON/OFF 글자)
        sw = QtCore.QRectF(cx - 37 * s, top + 116 * s, 74 * s, 36 * s)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(th["deep"] if on else OFF_GRAY)
        p.drawRoundedRect(sw, 18 * s, 18 * s)
        p.setBrush(QtGui.QColor(255, 255, 255))
        p.drawEllipse(QtCore.QPointF(sw.right() - 18 * s if on else sw.left() + 18 * s, sw.center().y()), 14 * s, 14 * s)
        p.setPen(QtGui.QColor(255, 255, 255))
        p.setFont(theme.ui_font(13 * s))
        label = QtCore.QRectF(sw.left() + 4 * s, sw.top(), 34 * s, sw.height()) if on else \
            QtCore.QRectF(sw.left() + 36 * s, sw.top(), 36 * s, sw.height())
        p.drawText(label, QtCore.Qt.AlignCenter, "ON" if on else "OFF")
        # 바라보는 동안 아래쪽에 진행 선
        if self.progress > 0:
            p.setPen(_pen(QtGui.QColor(255, 255, 255) if on else th["deep"], 4 * s))
            x0 = r.left() + 18 * s
            p.drawLine(QtCore.QPointF(x0, r.bottom() - 8 * s),
                       QtCore.QPointF(x0 + (r.width() - 36 * s) * self.progress, r.bottom() - 8 * s))


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
        s = self.width() / ICON_PX
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
        self.alpha = 1.0                  # 아이콘·상태 글자가 지금 보이는 정도 (0 = 완전히 투명)
        self.gaze = None                  # 마지막 커서 위치 (화면 좌표)
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
        was = self.icon.locked
        self.icon.set_locked(locked)
        self.scroll.setVisible(not locked)            # 일시정지 중에는 스크롤 토글도 안 보이게
        if locked and not was:
            self.hold_until = time.time() + INTRO_SEC  # 일시정지 직후엔 자물쇠 위치를 잠깐 보여줌 → 이후 멀어지면 투명
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
        """커서 위치(화면 좌표). 가까울수록 아이콘이 진해짐."""
        self.gaze = (x, y)

    def home_center(self):
        """메뉴 아이콘 중심의 화면 좌표."""
        area = QtWidgets.QApplication.primaryScreen().availableGeometry()
        return (area.right() + 1 - EDGE_MARGIN - ICON_PX / 2, area.bottom() + 1 - EDGE_MARGIN - ICON_PX / 2)

    def refresh_theme(self):
        self.update()
        self.icon.update()
        self.scroll.update()

    # ── 배치: 오른쪽 끝 세로줄 = 위 [스크롤 토글] / 아래 [메뉴 아이콘], 토글 왼쪽에 [상태 글자] ──
    def _pill_size(self):
        if not self.text:
            return 0, 0
        fm = QtGui.QFontMetricsF(theme.ui_font(17))
        return int(fm.horizontalAdvance(self.text) + 34), 42

    def _relayout(self):
        pw, _ = self._pill_size()
        left = pw + 12 if pw else 0
        w = left + ICON_PX
        top = 0 if self.icon.locked else SCROLL_H + SCROLL_GAP   # 일시정지 중엔 스크롤 토글이 없으니 자물쇠만 남김
        h = top + ICON_PX
        self.setFixedSize(w, h)
        self.scroll.move(w - SCROLL_W, 0)
        self.icon.move(w - ICON_PX, top)
        area = QtWidgets.QApplication.primaryScreen().availableGeometry()
        self.move(area.right() + 1 - EDGE_MARGIN - w, area.bottom() + 1 - EDGE_MARGIN - h)
        self.update()

    # ── 나타나기/사라지기 ────────────────────────────────────────
    def _target_alpha(self):
        if time.time() < self.hold_until:
            return 1.0
        if self.gaze is None:
            return 1.0 if self.icon.locked else 0.0   # 일시정지인데 시선을 아직 모르면 자물쇠를 보여줌 (못 찾는 일 없게)
        c = self.icon.mapToGlobal(QtCore.QPoint(self.icon.width() // 2, self.icon.height() // 2))
        d = math.hypot(self.gaze[0] - c.x(), self.gaze[1] - c.y())
        return max(0.0, min(1.0, (FAR_PX - d) / (FAR_PX - NEAR_PX)))

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
        if self.menu_open or not pw or a <= 0.01:
            return
        th = theme.current()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = QtCore.QRectF(1, self.icon.y() + ICON_PX - 7 - ph, pw - 2, ph)   # 메뉴 아이콘(자물쇠) 왼쪽, 원의 아래쪽 끝에 맞춤
        p.setPen(QtGui.QPen(theme.with_alpha(th["main"], 0.7 * a), 2))
        p.setBrush(QtGui.QColor(255, 255, 255, int(220 * a)))
        p.drawRoundedRect(rect, ph / 2, ph / 2)
        p.setPen(theme.with_alpha(th["deep"], a))
        p.setFont(theme.ui_font(17))
        p.drawText(rect, QtCore.Qt.AlignCenter, self.text)
