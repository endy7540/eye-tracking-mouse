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
    - 첫 화면: 메뉴창 아래까지 세로로 긴 카드 6개 (각 카드 아래쪽에 지금 상태 표시)
        1. 커서 투명도 (-/+ 누를 때마다 10%씩, 높을수록 투명)
        2. 일시정지    (커서만 숨김, 자물쇠 3초 응시로 다시 활성화)
        3. 키보드      (화상 키보드 열기/닫기)
        4. 시선 잔상   (ON/OFF)
        5. 설정        → 설정 화면으로
        6. 종료 (빨강) — 실수로 꺼지지 않게 두 번 눌러야 함 (첫 번째 → "한 번 더 윙크하면 종료", 3초 안에 한 번 더)
    - 설정 화면: 뒤로 · 캘리브레이션 다시 하기 · 윙크 클릭(아무 쪽 → 왼눈 → 오른눈 → 끔) · 응시 클릭(ON/OFF)
                · 게임 1 · 게임 2 (설정 화면에서 별도 미니게임 파일 실행 — 아래 GAME1_FILE / GAME2_FILE 참고)
                · 상태 확인 + 아래 줄에 테마 고르기 (무광 바둑알 8개: 하늘·민트·라벤더·노을·체리·슬레이트·화이트·다크)
    - 카드마다 아래쪽에 그림자 (화이트 테마는 흰 바탕끼리 구별되게 진하게)
    - 크기: 1920×1080 화면 기준 1620×750. 화면이 작으면 비율대로 줄어들고, 오른쪽 스크롤 토글과 겹치지 않게 맞춤 (_relayout)

테마는 메뉴창·메뉴 아이콘·스크롤 토글·커서·화상 키보드에 적용됩니다 (theme.current()의 카드·글자·강조색).
상태 확인 창이 쓰는 paint_panel_background()와 GazeButton 기본 모양은 예전 갈색 그대로 둡니다.

이 파일의 위젯들은 "버튼이 눌렸다"는 신호만 내보내고, 실제로 무엇을 할지는 main.py가 정합니다.

[제출 전] 상태 확인은 개발할 때만 쓰는 것이라 SHOW_STATUS_BUTTON = False로 바꾸면 설정 화면에서 사라집니다.
"""
import math
import os
import subprocess
import sys
import time
from pathlib import Path

from PyQt5 import QtWidgets, QtCore, QtGui

from . import theme
from .gaze_widgets import GazeButton, setup_floating_window, DWELL_CLICK_SEC
from .seal_cursor import MIN_OPACITY, MAX_OPACITY, SWATCH_GLOSS, paint_stone

SHOW_STATUS_BUTTON = True # [개발할 때만] 상태 확인 버튼 보이기 — 제출할 때 False로

# ── 미니게임 버튼 (설정 화면) ───────────────────────────────────────────
# ★ "게임파일" 자리에 실제 파일 이름만 쓰세요 (확장자 .py / .exe 는 빼고).
#    예) game.py 가 있으면  GAME1_FILE = "game"
#    개발 중에는 .py, 설치(배포) 후에는 .exe 를 자동으로 찾아서 실행합니다.
#    게임 파일은 main.py와 같은 폴더에 두세요. 다른 폴더에 두고 싶으면 GAME_DIR = Path("...")로 바꾸면 됩니다.
GAME1_FILE = "minigames"       # 첫 번째 게임 파일 이름
GAME2_FILE = "mole_game"       # 두 번째 게임 파일 이름
GAME1_TITLE = "미니게임"        # 카드에 보이는 이름 (원하는 대로 바꿔도 됨)
GAME2_TITLE = "두더지잡기"


def _app_dir():
    """게임 파일을 찾을 폴더 = 메인 프로그램이 있는 폴더.
    (설치 후 .exe 로 실행 중이면 그 .exe 가 있는 폴더, 개발 중이면 ui 폴더의 바로 위 폴더)"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


GAME_DIR = _app_dir()
# 다운로드 폴더 같은 다른 곳에 두고 싶으면 위 줄 대신 아래처럼 쓰세요:
# GAME_DIR = Path.home() / "Downloads"


def _find_game(name):
    """GAME_DIR 에서 name(.py 또는 .exe)을 찾아 경로를 돌려줌. 없으면 None."""
    name = (name or "").strip()
    if not name:
        return None
    if Path(name).suffix.lower() in (".py", ".exe"):          # 확장자까지 적었어도 동작
        candidates = [name]
    elif getattr(sys, "frozen", False):                       # 설치본: .exe 만 (파이썬이 없으므로)
        candidates = [name + ".exe"]
    else:                                                     # 개발 중: .py 먼저, 없으면 .exe
        candidates = [name + ".py", name + ".exe"]
    for c in candidates:
        p = GAME_DIR / c
        if p.is_file():
            return p
    return None


def launch_game(name):
    """게임 파일을 메인 프로그램과 따로 실행. 실행했으면 True, 파일이 없거나 실패하면 False."""
    path = _find_game(name)
    if path is None:
        return False
    try:
        if path.suffix.lower() == ".py":
            cmd = [sys.executable, str(path)]
        else:
            cmd = [str(path)]
        subprocess.Popen(cmd, cwd=str(path.parent))
        return True
    except Exception as e:
        print("[게임 실행 실패]", path, e)
        return False

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

SHADOW_PAD = 20           # 카드 아래쪽 그림자 자리 (카드 위젯이 이만큼 아래로 더 큼)
BASE_W, BASE_H = 1620, 750                   # 메뉴창 기준 크기 (1920×1080 화면)
CARD_H = 400              # 설정 화면 카드 높이 (기준 크기). 첫 화면 카드는 메뉴창 아래까지 길게
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
    p.setPen(QtGui.QPen(th["edge"], width))
    p.setBrush(th["panel"])
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
    elif kind == "game":                                 # 게임 패드
        p.setPen(_pen(color, 6 * u))
        p.drawRoundedRect(QtCore.QRectF(x - 34 * u, y - 19 * u, 68 * u, 38 * u), 16 * u, 16 * u)
        p.drawLine(P(-24, 0), P(-10, 0))                 # 십자키
        p.drawLine(P(-17, -7), P(-17, 7))
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(P(10, -5), 4.5 * u, 4.5 * u)       # 버튼 두 개
        p.drawEllipse(P(22, 5), 4.5 * u, 4.5 * u)
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


def paint_soft_shadow(p, r, radius, th, s):
    """카드 아래 부드러운 그림자 (투명한 둥근 사각형을 겹쳐 그림). 세기는 테마의 shadow (화이트가 가장 진함)."""
    k = th["shadow"]
    if k <= 0:
        return
    p.save()
    p.setPen(QtCore.Qt.NoPen)
    for i in range(6):
        g = (i + 1) * 2 * s
        p.setBrush(QtGui.QColor(15, 22, 40, int(24 * k * (1 - i / 6))))
        p.drawRoundedRect(r.adjusted(-g * 0.5, -g * 0.2 + 4 * s, g * 0.5, g + 4 * s), radius + g * 0.5, radius + g * 0.5)
    p.restore()


def paint_card(p, r, th, highlighted, s, radius=32, red=False):
    """카드 바탕: 테마 카드색 + 테마 테두리 + 그림자. 시선(또는 마우스)이 올라가면 굵은 강조 테두리 + 둘레 빛.
    red = True면 종료 카드 (빨간 테두리)."""
    paint_soft_shadow(p, r, radius * s, th, s)
    if highlighted:
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(theme.with_alpha(th["accent"], 0.32))
        p.drawRoundedRect(r.adjusted(-5 * s, -5 * s, 5 * s, 5 * s), (radius + 5) * s, (radius + 5) * s)
        p.setPen(QtGui.QPen(QUIT_RED if red else th["ring"], 7 * s))
    else:
        p.setPen(QtGui.QPen(QUIT_RED, 3 * s) if red else QtGui.QPen(th["border"], 2 * s))
    p.setBrush(th["card"])
    p.drawRoundedRect(r, radius * s, radius * s)


def paint_chip(p, cx, cy, text, dot, th, s, px=22):
    """작은 상태 알약: 색 점 + 글자. 예) ● 실행 중"""
    f = theme.ui_font(px * s)
    w = QtGui.QFontMetricsF(f).horizontalAdvance(text) + 2.4 * px * s
    h = 1.9 * px * s
    rect = QtCore.QRectF(cx - w / 2, cy - h / 2, w, h)
    p.setPen(QtGui.QPen(th["border"], 2 * s))
    p.setBrush(th["chip"])
    p.drawRoundedRect(rect, h / 2, h / 2)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(dot)
    p.drawEllipse(QtCore.QPointF(rect.left() + 0.95 * px * s, cy), 0.3 * px * s, 0.3 * px * s)
    p.setPen(th["deep"])
    p.setFont(f)
    p.drawText(rect.adjusted(1.55 * px * s, 0, -0.45 * px * s, 0), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, text)


def paint_toggle(p, cx, cy, on, th, s, k=1.3):
    """ON/OFF 스위치. 켜짐 = 테마 강조색 + 오른쪽 동그라미, 꺼짐 = 회색 + 왼쪽 동그라미."""
    w, h = 104 * k * s, 50 * k * s
    rect = QtCore.QRectF(cx - w / 2, cy - h / 2, w, h)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(th["accent"] if on else th["off"])
    p.drawRoundedRect(rect, h / 2, h / 2)
    knob_x = rect.right() - h / 2 if on else rect.left() + h / 2
    p.setBrush(th["main"] if (on and th["dark"]) else QtGui.QColor(255, 255, 255))
    p.drawEllipse(QtCore.QPointF(knob_x, cy), h / 2 - 6 * s, h / 2 - 6 * s)
    p.setPen(th["on"] if on else QtGui.QColor(255, 255, 255))
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
    p.setBrush(theme.with_alpha(th["accent"], 0.96))
    p.drawRoundedRect(rect, h / 2, h / 2)
    fg = th["on"]
    ix = rect.left() + 26 * s
    p.setPen(_pen(fg, 2.5 * s))
    p.setBrush(QtCore.Qt.NoBrush)
    p.drawEllipse(QtCore.QPointF(ix, cy), 6 * s, 6 * s)
    path = QtGui.QPainterPath(QtCore.QPointF(ix + 10 * s, cy - 1 * s))
    path.quadTo(QtCore.QPointF(ix + 15 * s, cy + 5 * s), QtCore.QPointF(ix + 20 * s, cy - 1 * s))
    p.drawPath(path)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(fg)
    p.drawEllipse(QtCore.QPointF(ix, cy), 2.4 * s, 2.4 * s)
    p.setPen(fg)
    p.setFont(f)
    p.drawText(rect.adjusted(46 * s, 0, -14 * s, 0), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, text)


def _card_body(widget, s):
    """카드 위젯 안에서 실제 카드가 그려지는 사각형.
    위쪽 HINT_PAD = '윙크하면 선택' 표시 자리, 양옆·아래 여유 = 그림자 자리."""
    return QtCore.QRectF(widget.rect()).adjusted(8 * s, (HINT_PAD + 8) * s, -8 * s, -SHADOW_PAD * s)


def _fit_font(px, text, max_w, bold=True):
    """글자가 max_w 보다 넓으면 들어갈 때까지 글자 크기를 줄임 (카드가 좁아져도 안 잘리게)."""
    while px > 10:
        f = theme.ui_font(px, bold)
        if QtGui.QFontMetricsF(f).horizontalAdvance(text) <= max_w:
            return f
        px -= 1
    return theme.ui_font(px, bold)


def _paint_card_head(p, r, th, s, kind, title, tall, red=False):
    """카드 위쪽 공통: 연한 동그라미 위 아이콘 + 이름. tall = 첫 화면의 긴 카드."""
    ic = QtCore.QPointF(r.center().x(), r.top() + (130 if tall else 104) * s)
    rad = (80 if tall else 74) * s
    if red:
        circ = QtGui.QColor(90, 50, 54) if th["dark"] else QtGui.QColor(255, 232, 232)
    else:
        circ = th["light"]
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(circ)
    p.drawEllipse(ic, rad, rad)
    draw_icon(p, kind, ic, (96 if tall else 90) * s, QUIT_RED if red else th["deep"])
    p.setPen(QUIT_RED if red else th["deep"])
    p.setFont(_fit_font(34 * s, title, r.width() - 12 * s))
    ty = r.top() + (238 if tall else 190) * s
    p.drawText(QtCore.QRectF(r.left(), ty, r.width(), 48 * s), QtCore.Qt.AlignCenter, title)
    return ty + 48 * s


# ── 메뉴창 부품 (전부 윙크로만 눌림) ──────────────────────────────────────
class ActionCard(GazeButton):
    """누르면 바로 동작하는 세로 카드. 위에서부터: 아이콘 → 이름 → 설명 → 지금 상태(알약 또는 ON/OFF 스위치).
    tall = True면 첫 화면의 더 긴 카드 (상태 표시가 카드 아래쪽에 붙음)."""

    def __init__(self, parent, kind, title, sub, tall=False):
        super().__init__("", parent)
        self.wink_only = True
        self.kind, self.title, self.sub, self.tall = kind, title, sub, tall
        self.footer = ("chip", "", OFF_GRAY)      # ("chip", 글자, 점 색) / ("toggle", 켜짐 여부) / ("none",)
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

    def _paint_footer(self, p, r, th, s):
        fy = r.bottom() - (88 if self.tall else 60) * s
        if self.footer[0] == "toggle":
            paint_toggle(p, r.center().x(), fy, self.footer[1], th, s)
        elif self.footer[0] == "chip" and self.footer[1]:
            paint_chip(p, r.center().x(), fy, self.footer[1], self.footer[2], th, s)

    def paintEvent(self, event):
        th, s = theme.current(), self.s
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = _card_body(self, s)
        hl = self.is_highlighted()
        paint_card(p, r, th, hl, s)
        y = _paint_card_head(p, r, th, s, self.kind, self.title, self.tall)
        p.setPen(theme.with_alpha(th["deep"], 0.8))
        p.setFont(_fit_font(20 * s, self.sub, r.width() - 12 * s, bold=False))
        p.drawText(QtCore.QRectF(r.left() + 6 * s, y + 4 * s, r.width() - 12 * s, 36 * s), QtCore.Qt.AlignCenter, self.sub)
        self._paint_footer(p, r, th, s)
        if hl:
            paint_wink_hint(p, r.center().x(), r.top() - 2 * s, th, s)


class QuitCard(ActionCard):
    """첫 화면 맨 오른쪽 종료 카드 (빨강). 실수로 꺼지지 않게 두 번 눌러야 종료:
    첫 번째 → 카드가 빨갛게 바뀌며 "한 번 더 윙크하면 종료", QUIT_CONFIRM_SEC 안에 한 번 더 누르면 종료."""

    def __init__(self, parent):
        super().__init__(parent, "power", "종료", "두 번 윙크하면 꺼져요", tall=True)
        self.footer = ("none",)
        self.armed = False

    def paintEvent(self, event):
        th, s = theme.current(), self.s
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = _card_body(self, s)
        hl = self.is_highlighted()
        if self.armed:                                        # 한 번 눌린 상태: 빨간 카드
            paint_soft_shadow(p, r, 32 * s, th, s)
            p.setPen(QtGui.QPen(QUIT_RED.darker(130), (7 if hl else 3) * s))
            p.setBrush(QUIT_RED)
            p.drawRoundedRect(r, 32 * s, 32 * s)
            p.setPen(QtGui.QColor(255, 255, 255))
            p.setFont(theme.ui_font(26 * s))
            p.drawText(r.adjusted(12 * s, 0, -12 * s, 0), QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap,
                       "한 번 더\n윙크하면\n종료")
        else:
            paint_card(p, r, th, hl, s, red=True)
            y = _paint_card_head(p, r, th, s, self.kind, self.title, True, red=True)
            p.setPen(theme.with_alpha(QUIT_RED, 0.9))
            p.setFont(theme.ui_font(19 * s, bold=False))
            p.drawText(QtCore.QRectF(r.left() + 6 * s, y + 4 * s, r.width() - 12 * s, 36 * s), QtCore.Qt.AlignCenter,
                       self.sub)
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
        p.setPen(QtGui.QPen(th["ring"] if hl else th["accent"], (6 if hl else 3) * s))
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
        r = _card_body(self, s)
        cx, cy = r.center().x(), r.bottom() - 88 * s
        self.minus.setFixedSize(size, size)
        self.plus.setFixedSize(size, size)
        self.minus.move(int(cx - 58 * s - size / 2), int(cy - size / 2))
        self.plus.move(int(cx + 58 * s - size / 2), int(cy - size / 2))

    def _highlighted(self):
        return any(b.is_highlighted() and b.isEnabled() for b in (self.minus, self.plus))

    def paintEvent(self, event):
        th, s = theme.current(), self.s
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = _card_body(self, s)
        hl = self._highlighted()
        paint_card(p, r, th, hl, s)
        y = _paint_card_head(p, r, th, s, self.kind, self.title, True)
        p.setPen(th["deep"])
        p.setFont(theme.title_font(46 * s))
        p.drawText(QtCore.QRectF(r.left(), y + 18 * s, r.width(), 56 * s), QtCore.Qt.AlignCenter, self.value)
        p.setPen(theme.with_alpha(th["deep"], 0.75))
        p.setFont(theme.ui_font(18 * s, bold=False))
        p.drawText(QtCore.QRectF(r.left(), y + 72 * s, r.width(), 28 * s), QtCore.Qt.AlignCenter, self.hint)
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
        th = theme.current()                         # 고리·글자색은 지금 테마를 따름
        own = theme.theme_colors(self.key)           # 바둑알 색은 이 버튼의 테마
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        c = QtCore.QPointF(self.width() / 2, self.height() * 0.38)
        R = 32 * s
        if self.is_highlighted():
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(theme.with_alpha(th["accent"], 0.22))
            p.drawEllipse(c, R + 16 * s, R + 16 * s)
        if self.selected:
            p.setPen(QtGui.QPen(th["accent"], 5 * s))
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawEllipse(c, R + 10 * s, R + 10 * s)
        paint_stone(p, c.x(), c.y(), R, own, 0.97, SWATCH_GLOSS, rim=own["dark"])
        if self.selected:
            ck = QtGui.QColor(40, 44, 54) if own["key"] == "white" else QtGui.QColor(255, 255, 255)
            p.setPen(_pen(ck, 6 * s))
            p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(c.x() - 13 * s, c.y()),
                                            QtCore.QPointF(c.x() - 3 * s, c.y() + 10 * s),
                                            QtCore.QPointF(c.x() + 15 * s, c.y() - 10 * s)]))
        p.setPen(th["deep"] if self.selected else theme.with_alpha(th["deep"], 0.7))
        p.setFont(theme.ui_font(18 * s, bold=self.selected))
        p.drawText(QtCore.QRectF(0, self.height() * 0.84 - 16 * s, self.width(), 32 * s),
                   QtCore.Qt.AlignCenter, own["name"])


class PanelCloseButton(GazeButton):
    """메뉴창 오른쪽 위 X (크롬 창처럼): 평소엔 카드색 동그라미 위 X, 시선/마우스가 올라가면 빨간 배경 + 흰 X."""

    def __init__(self, parent):
        super().__init__("", parent)
        self.wink_only = True
        self.s = 1.0
        self.setToolTip("닫기")

    def paintEvent(self, event):
        th, s = theme.current(), self.s
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(5 * s, 4 * s, -5 * s, -8 * s)
        hl = self.is_highlighted()
        if not hl:
            paint_soft_shadow(p, r, r.width() / 2, th, s * 0.6)
        p.setPen(QtGui.QPen(th["border"], 2 * s) if not hl else QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(232, 17, 35) if hl else th["chip"])
        p.drawEllipse(r)
        p.setPen(_pen(QtGui.QColor(255, 255, 255) if hl else th["deep"], 5 * s))
        c, d = r.center(), r.width() * 0.19
        p.drawLine(QtCore.QPointF(c.x() - d, c.y() - d), QtCore.QPointF(c.x() + d, c.y() + d))
        p.drawLine(QtCore.QPointF(c.x() - d, c.y() + d), QtCore.QPointF(c.x() + d, c.y() - d))


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

        # 첫 화면: 세로로 긴 카드 6개 (맨 오른쪽 = 종료)
        self.opacity_card = StepperCard(self, "opacity", "커서 투명도")
        self.pause_card = ActionCard(self, "pause", "일시정지", "커서 숨기기", tall=True)
        self.keyboard_card = ActionCard(self, "keyboard", "키보드", "화상 키보드", tall=True)
        self.trail_card = ActionCard(self, "trail", "시선 잔상", "지나간 길 표시", tall=True)
        self.settings_card = ActionCard(self, "gear", "설정", "테마 · 보정 · 클릭", tall=True)
        self.quit_card = QuitCard(self)
        self.main_cards = [self.opacity_card, self.pause_card, self.keyboard_card,
                           self.trail_card, self.settings_card, self.quit_card]
        self.opacity_card.minus.clicked.connect(lambda: self.transparency_down_requested.emit())
        self.opacity_card.plus.clicked.connect(lambda: self.transparency_up_requested.emit())
        self.pause_card.clicked.connect(lambda: self.pause_requested.emit())
        self.keyboard_card.clicked.connect(lambda: self.keyboard_toggle_requested.emit())
        self.trail_card.clicked.connect(lambda: self.trail_toggle_requested.emit())
        self.settings_card.clicked.connect(lambda: self.show_page("settings"))
        self.quit_card.clicked.connect(self._on_quit)
        self.quit_timer = QtCore.QTimer(self)
        self.quit_timer.setSingleShot(True)
        self.quit_timer.timeout.connect(self._disarm_quit)

        # 설정 화면: 뒤로 · 캘리브레이션 · 윙크 클릭 · 응시 클릭 · 상태 확인 + 아래 테마 바둑알 8개
        self.back_card = ActionCard(self, "back", "뒤로", "메뉴로 돌아가기")
        self.calib_card = ActionCard(self, "calib", "캘리브레이션", "다시 맞추기")
        self.wink_card = ActionCard(self, "wink", "윙크 클릭", "누르면 바뀌어요")
        self.dwell_card = ActionCard(self, "dwell", "응시 클릭", "메뉴 밖에서 보면 클릭")
        self.status_card = ActionCard(self, "status", "상태 확인", "카메라 · 눈 · 정확도")
        self.game1_card = ActionCard(self, "game", GAME1_TITLE, "미니게임 실행")
        self.game2_card = ActionCard(self, "game", GAME2_TITLE, "미니게임 실행")
        self.settings_cards = [self.back_card, self.calib_card, self.wink_card, self.dwell_card,
                               self.game1_card, self.game2_card]
        if SHOW_STATUS_BUTTON:
            self.settings_cards.append(self.status_card)
        self.calib_card.set_chip("두더지 잡기", theme.YELLOW)
        self.back_card.clicked.connect(lambda: self.show_page("main"))
        self.calib_card.clicked.connect(lambda: self.recalibrate_requested.emit())
        self.wink_card.clicked.connect(lambda: self.wink_toggle_requested.emit())
        self.dwell_card.clicked.connect(lambda: self.dwell_toggle_requested.emit())
        self.status_card.clicked.connect(lambda: self.status_requested.emit())
        self.game1_card.clicked.connect(lambda: self._on_game(self.game1_card, GAME1_FILE))
        self.game2_card.clicked.connect(lambda: self._on_game(self.game2_card, GAME2_FILE))
        self._game_timer = QtCore.QTimer(self)               # "파일 없음" 표시를 잠시 뒤 원래대로
        self._game_timer.setSingleShot(True)
        self._game_timer.timeout.connect(self._reset_game_chips)
        self._reset_game_chips()
        self.swatches = []
        for t in theme.THEMES:
            sw = ThemeSwatch(self, t["key"])
            sw.clicked.connect(lambda _=False, k=t["key"]: self.theme_selected.emit(k))
            self.swatches.append(sw)

        self._relayout()
        self.show_page("main")

    # ── 화면 전환 ────────────────────────────────────────────────
    def show_page(self, page):
        """"main"(첫 화면) / "settings"(설정 화면) 전환."""
        self.page = page
        for c in self.main_cards:
            c.setVisible(page == "main")
        for c in self.settings_cards + self.swatches:
            c.setVisible(page == "settings")
        self.status_card.setVisible(page == "settings" and SHOW_STATUS_BUTTON)
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.show_page("main")                  # 메뉴창을 열 때는 항상 첫 화면부터
        self._disarm_quit()

    # ── 미니게임 실행 ─────────────────────────────────────────────
    def _on_game(self, card, name):
        if launch_game(name):
            self.close_requested.emit()          # 게임이 뜨면 메뉴창은 닫음
        else:
            card.set_chip("파일 없음", theme.RED)   # 파일을 못 찾으면 카드에 잠깐 표시
            self._game_timer.start(2500)

    def _reset_game_chips(self):
        accent = theme.current()["accent"]
        for c in (self.game1_card, self.game2_card):
            c.set_chip("열기 ›", accent)

    # ── 종료 (두 번 눌러야 종료) ──────────────────────────────────
    def _on_quit(self):
        if self.quit_card.armed:
            self.quit_requested.emit()
        else:
            self.quit_card.armed = True         # 첫 번째: "한 번 더 윙크하면 종료"
            self.quit_card.update()
            self.quit_timer.start(int(QUIT_CONFIRM_SEC * 1000))

    def _disarm_quit(self):
        self.quit_card.armed = False
        self.quit_card.update()

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
        self.close_btn.setFixedSize(cb, int(cb + 4 * s))
        self.close_btn.move(int(W - pad - cb), int(pad + 4 * s))

        # 카드 위젯은 위로 '윙크하면 선택' 자리(HINT_PAD), 양옆·아래로 그림자 자리만큼 더 큼
        top = pad + 76 * s + 22 * s - (HINT_PAD + 8) * s
        ext_x, ext_b = 8 * s, SHADOW_PAD * s

        # 첫 화면: 긴 카드 6개 (머리줄 아래부터 메뉴창 아래 여백까지)
        tall_h = H - pad - (pad + 76 * s + 22 * s)
        cw = (W - 2 * pad - 5 * gap) / 6
        for i, card in enumerate(self.main_cards):
            card.setGeometry(int(pad + i * (cw + gap) - ext_x), int(top), int(cw + 2 * ext_x),
                             int(tall_h + (HINT_PAD + 8) * s + ext_b))
            card.set_scale(s)

        # 설정 화면: 카드 4~5개 + 아래 테마 줄
        n = len(self.settings_cards)
        slots = max(n, 5)                                  # 5개까지는 예전과 같은 폭, 넘으면 줄여서 한 줄에
        cw2 = (W - 2 * pad - (slots - 1) * gap) / slots
        total = n * cw2 + (n - 1) * gap
        x0 = pad + (W - 2 * pad - total) / 2
        for i, card in enumerate(self.settings_cards):
            card.setGeometry(int(x0 + i * (cw2 + gap) - ext_x), int(top), int(cw2 + 2 * ext_x),
                             int(CARD_H * s + (HINT_PAD + 8) * s + ext_b))
            card.set_scale(s)
        ty = pad + 76 * s + 22 * s + CARD_H * s + 24 * s
        self.theme_rect = QtCore.QRectF(pad, ty, W - 2 * pad, H - pad - ty)
        sw_x = pad + 270 * s
        sw_w = (self.theme_rect.right() - 20 * s - sw_x) / len(self.swatches)
        for i, sw in enumerate(self.swatches):
            sw.s = s
            sw.setGeometry(int(sw_x + i * sw_w), int(ty + 4 * s), int(sw_w), int(self.theme_rect.height() - 8 * s))
        self.update()

    def place(self):
        """화면 크기에 맞게 다시 배치하고 화면 가운데에 놓음 (main.py가 메뉴창을 열 때 호출)."""
        self._relayout()
        place_center(self)

    def refresh_theme(self):
        """테마가 바뀌면 메뉴창 전체를 다시 그림."""
        self.update()
        for w in self.main_cards + self.settings_cards + self.swatches + [self.close_btn, self.status_card]:
            w.update()
        self.opacity_card.minus.update()
        self.opacity_card.plus.update()

    # ── 상태 표시 ────────────────────────────────────────────────
    def update_state(self, st):
        """main.py가 모드가 바뀔 때마다 호출.
        st = {"paused", "trail", "keyboard", "wink", "dwell", "status", "opacity", "theme"}"""
        th = theme.current()
        op = st.get("opacity", 0.6)
        self.opacity_card.set_value(f"{round((1 - op) * 100)}%", "높을수록 투명")
        self.opacity_card.plus.setEnabled(op > MIN_OPACITY + 1e-6)     # 투명도 + = 진하기 -
        self.opacity_card.minus.setEnabled(op < MAX_OPACITY - 1e-6)

        if st["paused"]:
            self.pause_card.set_chip("일시정지 중", theme.RED)
        else:
            self.pause_card.set_chip("실행 중", theme.GREEN)
        self.keyboard_card.set_chip("열림" if st["keyboard"] else "닫힘",
                                    theme.GREEN if st["keyboard"] else th["off"])
        self.trail_card.set_toggle(st["trail"])
        self.settings_card.set_chip("들어가기 ›", th["accent"])
        self.back_card.set_chip("메뉴", th["accent"])
        self.wink_card.set_chip(WINK_NAMES.get(st["wink"], "아무 쪽 눈"),
                                theme.GREEN if st["wink"] != "off" else th["off"])
        self.dwell_card.set_toggle(st["dwell"])
        self._reset_game_chips()
        status_on = st.get("status", False)
        self.status_card.set_chip("열림" if status_on else "닫힘", theme.GREEN if status_on else th["off"])

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
        # 배경: 테마 메뉴창 색 (색깔 테마는 많이 투명하게, 화이트·다크는 조금 더 진하게)
        p.setPen(QtGui.QPen(th["edge"], (3 if th["key"] == "white" else 4) * s))
        p.setBrush(th["panel"])
        p.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(2 * s, 2 * s, -2 * s, -2 * s), 44 * s, 44 * s)

        # 머리줄 (뒤 화면 글씨와 겹쳐도 읽히도록 카드색 바탕)
        hr = self.header_rect
        paint_soft_shadow(p, hr, hr.height() / 2, th, s * 0.7)
        p.setPen(QtGui.QPen(th["border"], 2 * s))
        p.setBrush(th["card"])
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

        # 설정 화면: 테마 칸 바탕 + 제목 (바둑알들은 ThemeSwatch가 따로 그림)
        if self.page == "settings":
            tr = self.theme_rect
            paint_card(p, tr, th, False, s, radius=28)
            p.setPen(th["deep"])
            p.setFont(theme.title_font(36 * s))
            p.drawText(QtCore.QRectF(tr.left() + 34 * s, tr.top() + 22 * s, 220 * s, 52 * s),
                       QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, "테마")
            p.setPen(theme.with_alpha(th["deep"], 0.8))
            p.setFont(theme.ui_font(16 * s, bold=False))
            p.drawText(QtCore.QRectF(tr.left() + 34 * s, tr.top() + 78 * s, 230 * s, 60 * s),
                       QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft, "메뉴·아이콘·커서·키보드\n색이 함께 바뀌어요")


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
        paint_soft_shadow(p, r, 30 * s, th, s * 0.6)
        p.setPen(QtGui.QPen(th["ring"] if hl else th["border"], (5 if hl else 2.5) * s))
        p.setBrush(theme.with_alpha(th["accent"], 0.94) if on else th["chip"])
        p.drawRoundedRect(r, 30 * s, 30 * s)
        ink = th["on"] if on else th["deep"]
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
        p.setBrush((th["main"] if th["dark"] else th["deep"]) if on else th["off"])   # 켜짐: 바탕과 대비되는 색
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
            p.setPen(_pen(th["on"] if on else th["deep"], 4 * s))
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
        edge = theme.with_alpha(th["edge"], a) if th["key"] == "white" else QtGui.QColor(255, 255, 255, int(240 * a))
        p.setPen(QtGui.QPen(edge, 4 * s))
        p.setBrush(theme.with_alpha(th["main"], (0.95 if th["key"] in ("white", "black") else 0.85) * a))
        p.drawEllipse(r)
        if self.is_highlighted():                                      # 하이라이트: 테마 강조색 굵은 테두리
            p.setPen(QtGui.QPen(theme.with_alpha(th["ring"], a), 6 * s))
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawEllipse(r.adjusted(-2 * s, -2 * s, 2 * s, 2 * s))
        draw_icon(p, "lock" if self.locked else "menu", r.center(), 52 * s, theme.with_alpha(th["main_ink"], a))
        if self.progress > 0:                    # 바라보는 동안 둘레 게이지 (자물쇠일 땐 커서가 숨겨져 있어서 여기서 보여줌)
            p.setPen(_pen(theme.with_alpha(th["ring"], a), 6 * s))
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
        p.setPen(QtGui.QPen(theme.with_alpha(th["border"], a), 2))
        p.setBrush(theme.with_alpha(th["chip"], 0.92 * a))
        p.drawRoundedRect(rect, ph / 2, ph / 2)
        p.setPen(theme.with_alpha(th["deep"], a))
        p.setFont(theme.ui_font(17))
        p.drawText(rect, QtCore.Qt.AlignCenter, self.text)