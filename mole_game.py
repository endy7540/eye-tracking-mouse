# -*- coding: utf-8 -*-
"""
mole_game.py — 눈동자 마우스 시연용 "두더지 잡기" 게임 (단독 실행 파일)

이 파일 하나로 돌아갑니다. 프로젝트의 다른 .py 파일을 불러오지 않아요.
(그림·글꼴은 프로젝트의 ui/assets, ui/fonts 폴더에 있으면 그걸 쓰고, 없으면 직접 그린 그림·기본 글꼴로 대신합니다)

실행
    python mole_game.py                 전체화면 (ESC 로 종료)
    python mole_game.py --windowed      창 모드 (테스트용)
    python mole_game.py --hover 0.8     마우스/시선을 두더지 위에 0.8초 두면 잡힘 (기본은 꺼짐: 클릭으로만 잡음)
    python mole_game.py --hide-cursor   윈도우 마우스 커서를 숨김 (시선 커서만 보이게)

눈동자 마우스(main.py)와 같이 쓰는 법
    1) start.bat 으로 시선 마우스를 켠다 (캘리브레이션이 끝나면 시선 커서가 뜸).
    2) 다른 터미널에서 python mole_game.py 를 실행한다.
    3) 두더지를 바라보고 윙크 클릭(또는 메뉴에서 "응시 클릭"을 켜고 1.2초 응시)하면 두더지가 잡힙니다.
       시선 마우스의 클릭은 실제 마우스 클릭이라서, 이 게임은 그냥 "마우스 클릭"을 받으면 됩니다.

게임 규칙
    - 구멍 9개에서 두더지가 하나씩(12초 뒤부터는 두 마리까지) 튀어나옵니다. 45초 동안 최대한 많이 잡으세요.
    - 두더지는 처음 2.6초 동안 머물다가 갈수록 짧아집니다 (응시 클릭 1.2초가 충분히 통하도록 느긋하게 시작).
    - 잡을 때마다 10점, 연속으로 잡으면 콤보 보너스(+5점씩, 최대 +25). 놓치면 콤보가 끊깁니다.
    - 눈동자는 정확도가 높지 않아서 두더지 얼굴 주변 넉넉한 원 안이면 잡힌 걸로 칩니다. 빈 곳을 눌러도 감점은 없어요.

나중에 시선 좌표를 직접 넘기고 싶으면
    window.feed_gaze(화면x, 화면y)   — 실행 중인 GameWindow 에 시선 위치(화면 전체 좌표)를 알려줌 (--hover 와 함께 사용)

구성: 위쪽은 화면과 상관없는 게임 규칙(Game, Qt 없이 테스트 가능), 아래쪽이 PyQt5 화면(GameWindow)입니다.
"""
import argparse
import math
import random
import sys
import time
from pathlib import Path

# ════════════════════════════════════════════════════════════════
#  1. 게임 설정 (숫자를 바꾸면 난이도가 바뀝니다)
# ════════════════════════════════════════════════════════════════
ROUND_SEC = 45.0                 # 한 판 시간
COL_X = (1 / 6, 3 / 6, 5 / 6)    # 구멍 3열의 가로 위치 (화면 너비 비율)
ROW_Y = (0.30, 0.57, 0.84)       # 구멍 3줄의 세로 위치 (화면 높이 비율) — 두더지 코가 오는 높이
MENU_HOLE = 4                    # 시작/다시하기 두더지가 나오는 구멍 (가운데)

STAY_START, STAY_END = 2.6, 1.7  # 두더지가 머무는 시간(초): 판이 시작할 때 → 끝날 때 (선형으로 줄어듦)
GAP_START, GAP_END = 1.0, 0.55   # 다음 두더지가 나오기까지의 간격(초): 시작 → 끝
SECOND_MOLE_AFTER = 12.0         # 이 시간이 지나면 두더지가 동시에 두 마리까지 나옴
POP_SEC = 0.25                   # 구멍에서 올라오는 시간
SINK_SEC = 0.25                  # 놓쳐서 다시 들어가는 시간
HIT_SEC = 0.65                   # 뿅망치로 맞는 애니메이션 길이
HIT_AT = 0.45                    # 애니메이션 중 망치가 닿는 시점 (비율)
START_DELAY = 1.2                # 시작 두더지를 잡은 뒤 "준비" 시간

HIT_RADIUS_RATIO = 0.62          # 맞았다고 보는 반경 (두더지 크기 대비) — 눈동자 오차를 감안해 넉넉하게
POINTS_BASE = 10                 # 한 마리 기본 점수
POINTS_STEP = 5                  # 콤보 1단계마다 추가 점수
POINTS_MAX_STEPS = 5             # 보너스 단계 상한 (+25점까지)
EFFECT_LIFE = 1.2                # 물결/점수 글자가 화면에 남는 시간

# 두더지 그림(800x800) 안의 위치 비율 (프로젝트의 mole.png 기준)
MOLE_NOSE_Y = 0.52               # 코 — 이 지점이 목표 위치
MOLE_BOTTOM_Y = 0.92             # 구멍 아래쪽 (기울임/찌그러짐 기준점)
HOLE_MID_Y = 0.79                # 구멍 입구 가운데
RISE_DEPTH = 0.72                # 완전히 숨었을 때 아래로 내리는 거리
HAMMER_PIVOT_Y = 0.922           # 뿅망치 그림에서 손잡이 끝 위치


def lerp(a, b, k):
    return a + (b - a) * max(0.0, min(1.0, k))


# ════════════════════════════════════════════════════════════════
#  2. 게임 규칙 (화면과 무관 — Qt 없이 시간·좌표만 받아서 계산)
# ════════════════════════════════════════════════════════════════
class Mole:
    """구멍에 나와 있는 두더지 하나. state: up(나와 있음) / hit(맞는 중) / sink(놓쳐서 들어가는 중)"""
    __slots__ = ("hole", "t0", "stay", "state", "t_state", "menu")

    def __init__(self, hole, t0, stay, menu=False):
        self.hole, self.t0, self.stay = hole, t0, stay
        self.state, self.t_state, self.menu = "up", t0, menu


class Game:
    """
    상태 흐름:  title ─(시작 두더지 잡기)→ starting ─(1.2초)→ playing ─(45초)→ result ─(다시 하기)→ starting …
    사용법:  game.update(now) 를 계속 부르고, 입력이 오면 game.click(x, y, now) (또는 game.hover(...)).
    """

    def __init__(self, w, h, rng=None, hover_sec=0.0):
        self.rng = rng or random.Random()
        self.hover_sec = hover_sec
        self.best = 0
        self.set_size(w, h)
        self.to_title()

    # ── 화면 크기에 따른 배치 ──
    def set_size(self, w, h):
        self.w, self.h = w, h
        # 두더지 크기: 줄 간격에 맞추되 너무 크거나 작지 않게
        self.S = max(120.0, min(h * (ROW_Y[1] - ROW_Y[0]), w * 0.2, 340.0))
        self.holes = [(cx * w, ry * h) for ry in ROW_Y for cx in COL_X]   # 두더지 코가 오는 점

    def hole_xy(self, i):
        return self.holes[i]

    @property
    def hit_radius(self):
        return HIT_RADIUS_RATIO * self.S

    # ── 상태 초기화 ──
    def to_title(self):
        self.state = "title"
        self.moles = []
        self.effects = []
        self.menu = Mole(MENU_HOLE, 0.0, 0.0, menu=True)
        self.t_state = 0.0
        self._clear_stats()
        self._reset_hover()

    def _clear_stats(self):
        self.score = self.combo = self.max_combo = 0
        self.hits = self.misses = self.spawned = 0
        self.t_play0 = 0.0
        self.next_spawn = 0.0
        self.last_hole = None
        self.new_best = False

    def _reset_hover(self):
        self.hover_target = None
        self.hover_since = 0.0
        self.hover_progress = 0.0

    # ── 진행 정도 ──
    def elapsed(self, now):
        return max(0.0, now - self.t_play0) if self.state == "playing" else 0.0

    def time_left(self, now):
        return max(0.0, ROUND_SEC - self.elapsed(now)) if self.state == "playing" else 0.0

    def _progress(self, now):
        return max(0.0, min(1.0, (now - self.t_play0) / ROUND_SEC))

    def current_stay(self, now):
        return lerp(STAY_START, STAY_END, self._progress(now))

    def current_gap(self, now):
        return lerp(GAP_START, GAP_END, self._progress(now))

    def max_up(self, now):
        return 1 if self.elapsed(now) < SECOND_MOLE_AFTER else 2

    @property
    def accuracy(self):
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    # ── 매 프레임 ──
    def update(self, now):
        self.effects = [e for e in self.effects if now - e["t"] < EFFECT_LIFE]

        if self.state == "starting":
            if now - self.t_state >= START_DELAY:
                self._begin_play(now)
            return
        if self.state != "playing":
            return

        if now - self.t_play0 >= ROUND_SEC:
            self._end_round(now)
            return

        for m in self.moles:                                       # 시간 초과 → 놓침
            if m.state == "up" and now - m.t0 >= m.stay:
                m.state, m.t_state = "sink", now
                self.misses += 1
                self.combo = 0
        self.moles = [m for m in self.moles
                      if not (m.state == "sink" and now - m.t_state >= SINK_SEC)
                      and not (m.state == "hit" and now - m.t_state >= HIT_SEC)]

        up = sum(1 for m in self.moles if m.state == "up")        # 새 두더지 등장
        if now >= self.next_spawn and up < self.max_up(now):
            hole = self._pick_hole()
            if hole is not None:
                self.moles.append(Mole(hole, now, self.current_stay(now)))
                self.spawned += 1
                self.last_hole = hole
                self.next_spawn = now + self.current_gap(now) + self.rng.uniform(0.0, 0.3)

    def _pick_hole(self):
        busy = {m.hole for m in self.moles}
        free = [i for i in range(len(self.holes)) if i not in busy]
        if not free:
            return None
        pool = [i for i in free if i != self.last_hole] or free   # 같은 구멍에서 연속으로 안 나오게
        return self.rng.choice(pool)

    def _begin_play(self, now):
        self._clear_stats()
        self.state = "playing"
        self.t_play0 = now
        self.next_spawn = now + 0.4
        self.moles = []
        self.menu.state = "up"
        self._reset_hover()

    def _end_round(self, now):
        self.state = "result"
        self.t_state = now
        self.moles = []
        self.new_best = self.score > self.best
        self.best = max(self.best, self.score)
        self.menu = Mole(MENU_HOLE, now, 0.0, menu=True)
        self._reset_hover()

    # ── 입력: 클릭 (윙크/응시 클릭도 실제 마우스 클릭이라 여기로 들어옴) ──
    def click(self, x, y, now):
        """반환: 'hit'(두더지 잡음) / 'miss'(빗나감) / 'menu'(시작·다시하기 두더지 잡음) / 'ignored'"""
        if self.state in ("title", "result"):
            if self._dist(self.menu, x, y) <= self.hit_radius:
                self._grab_menu(x, y, now)
                return "menu"
            self._ripple(x, y, now, False)
            return "miss"
        if self.state != "playing":
            return "ignored"

        best, best_d = None, None
        for m in self.moles:
            if m.state != "up":
                continue
            d = self._dist(m, x, y)
            if d <= self.hit_radius and (best_d is None or d < best_d):
                best, best_d = m, d
        if best is None:
            self._ripple(x, y, now, False)                        # 빈 곳: 감점 없음
            return "miss"

        best.state, best.t_state = "hit", now
        self.hits += 1
        self.combo += 1
        self.max_combo = max(self.max_combo, self.combo)
        gained = POINTS_BASE + POINTS_STEP * min(self.combo - 1, POINTS_MAX_STEPS)
        self.score += gained
        self._ripple(x, y, now, True)
        hx, hy = self.hole_xy(best.hole)
        self.effects.append({"kind": "popup", "x": hx, "y": hy - 0.55 * self.S, "t": now, "text": f"+{gained}"})
        return "hit"

    def _grab_menu(self, x, y, now):
        self.menu.state, self.menu.t_state = "hit", now
        self.state, self.t_state = "starting", now
        self.moles = []
        self._ripple(x, y, now, True)
        self._reset_hover()

    def _ripple(self, x, y, now, hit):
        self.effects.append({"kind": "ripple", "x": x, "y": y, "t": now, "hit": hit})

    def _dist(self, m, x, y):
        cx, cy = self.hole_xy(m.hole)
        return math.hypot(cx - x, cy - y)

    # ── 입력: 가만히 바라보기 (--hover 용, 마우스 위치나 feed_gaze 로 받은 시선) ──
    def hover(self, x, y, now):
        """hover_sec 초 동안 같은 두더지 위에 머물면 click 으로 처리. 진행률은 hover_progress(0~1)."""
        if self.hover_sec <= 0 or x is None:
            self._reset_hover()
            return None
        target = self._hover_candidate(x, y)
        if target is None:
            self._reset_hover()
            return None
        if target is not self.hover_target:
            self.hover_target, self.hover_since = target, now
        self.hover_progress = min((now - self.hover_since) / self.hover_sec, 1.0)
        if self.hover_progress >= 1.0:
            cx, cy = self.hole_xy(target.hole)
            self._reset_hover()
            return self.click(cx, cy, now)
        return None

    def _hover_candidate(self, x, y):
        if self.state in ("title", "result"):
            return self.menu if self._dist(self.menu, x, y) <= self.hit_radius else None
        if self.state != "playing":
            return None
        cands = [m for m in self.moles if m.state == "up" and self._dist(m, x, y) <= self.hit_radius]
        return min(cands, key=lambda m: self._dist(m, x, y)) if cands else None



# ════════════════════════════════════════════════════════════════
#  3. PyQt5 화면
# ════════════════════════════════════════════════════════════════
from PyQt5 import QtWidgets, QtCore, QtGui   # noqa: E402  (위의 게임 규칙은 Qt 없이도 불러올 수 있게 아래에 둠)

HERE = Path(__file__).resolve().parent
ASSET_DIRS = [HERE / "ui" / "assets", HERE / "assets"]
FONT_FILES = [HERE / "ui" / "fonts" / "ttf" / "BMJUA_ttf.ttf", HERE / "fonts" / "BMJUA_ttf.ttf"]
FALLBACK_FONT = "Malgun Gothic"

SAND = QtGui.QColor(238, 226, 200)
SAND_MARK = QtGui.QColor(221, 205, 172)
DIRT = QtGui.QColor(160, 110, 72)
HOLE_DARK = QtGui.QColor(66, 42, 34)
HOLE_RIM = QtGui.QColor(122, 84, 62)
HOLE_EDGE = QtGui.QColor(70, 45, 35)
INK = QtGui.QColor(74, 52, 40)
INK_SOFT = QtGui.QColor(120, 95, 78)
WHITE = QtGui.QColor(255, 255, 255)
GREEN = QtGui.QColor(70, 180, 110)
YELLOW = QtGui.QColor(248, 196, 60)
RED = QtGui.QColor(224, 88, 80)
ORANGE = QtGui.QColor(242, 130, 40)


def _load_pixmap(name):
    for d in ASSET_DIRS:
        path = d / name
        if path.exists():
            pm = QtGui.QPixmap(str(path))
            if not pm.isNull():
                return pm
    return None


def _vector_mole(S, hit):
    """mole.png 가 없을 때 대신 쓰는 직접 그린 두더지 (같은 비율: 코 0.52, 구멍 아래 0.92)."""
    S = int(S)
    pm = QtGui.QPixmap(S, S)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    line = QtGui.QPen(QtGui.QColor(75, 50, 38), max(2.0, S * 0.012))
    p.setPen(line)
    p.setBrush(QtGui.QColor(150, 100, 70))
    p.drawEllipse(QtCore.QRectF(S * 0.20, S * 0.18, S * 0.60, S * 0.74))          # 몸통
    p.setBrush(QtGui.QColor(196, 148, 104))
    p.drawEllipse(QtCore.QRectF(S * 0.32, S * 0.50, S * 0.36, S * 0.34))          # 배
    p.setBrush(QtGui.QColor(236, 150, 160))
    p.drawEllipse(QtCore.QPointF(S * 0.5, S * 0.52), S * 0.06, S * 0.045)         # 코
    p.setBrush(WHITE)
    for ex in (0.38, 0.62):
        p.drawEllipse(QtCore.QPointF(S * ex, S * 0.38), S * 0.05, S * 0.055)      # 눈
    p.setBrush(INK)
    for ex in (0.38, 0.62):
        p.drawEllipse(QtCore.QPointF(S * ex, S * 0.39), S * 0.022, S * 0.026)
    if hit:                                                                          # 맞았을 때: 눈을 X로
        p.setPen(QtGui.QPen(INK, max(3.0, S * 0.015)))
        for ex in (0.38, 0.62):
            cx, cy, r = S * ex, S * 0.385, S * 0.05
            p.drawLine(QtCore.QPointF(cx - r, cy - r), QtCore.QPointF(cx + r, cy + r))
            p.drawLine(QtCore.QPointF(cx - r, cy + r), QtCore.QPointF(cx + r, cy - r))
    p.end()
    return pm


class GameWindow(QtWidgets.QWidget):
    def __init__(self, windowed=False, hover_sec=0.0, hide_cursor=False):
        super().__init__()
        self.windowed = windowed
        screen_geo = QtWidgets.QApplication.primaryScreen().geometry()
        if windowed:
            self.setWindowTitle("두더지 잡기")
            self.resize(1280, 720)
        else:
            self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
            self.setGeometry(screen_geo)
        if hide_cursor:
            self.setCursor(QtCore.Qt.BlankCursor)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        self.game = Game(self.width(), self.height(), hover_sec=hover_sec)
        self._gaze = None                     # (x, y, 시각) — feed_gaze 로 받은 시선 (화면 전체 좌표)
        self._size_key = None
        self._bg = None
        self._pix = {}
        self.fonts_family = self._load_font()

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    # ── 시선 좌표를 직접 넘겨받고 싶을 때 ──
    def feed_gaze(self, x, y):
        self._gaze = (x, y, time.time())

    # ── 입력 ──
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.game.click(event.x(), event.y(), time.time())
            self.update()

    def keyPressEvent(self, event):
        key = event.key()
        if key == QtCore.Qt.Key_Escape:
            self.close()
        elif key in (QtCore.Qt.Key_Space, QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            g = self.game
            if g.state in ("title", "result"):                   # 발표자가 키보드로 바로 시작
                cx, cy = g.hole_xy(g.menu.hole)
                g.click(cx, cy, time.time())

    def showEvent(self, event):
        super().showEvent(event)
        self.activateWindow()
        self.setFocus()

    def _tick(self):
        now = time.time()
        g = self.game
        g.set_size(self.width(), self.height())
        g.update(now)
        if g.hover_sec > 0:
            pos = self._pointer_pos(now)
            if pos is None:
                g.hover(None, None, now)
            else:
                g.hover(pos[0], pos[1], now)
        self.update()

    def _pointer_pos(self, now):
        """--hover 용 위치: 최근에 feed_gaze 로 받은 시선이 있으면 그것, 없으면 마우스 커서."""
        if self._gaze is not None and now - self._gaze[2] < 0.5:
            local = self.mapFromGlobal(QtCore.QPoint(int(self._gaze[0]), int(self._gaze[1])))
        else:
            local = self.mapFromGlobal(QtGui.QCursor.pos())
        return local.x(), local.y()

    # ── 글꼴 / 그림 준비 ──
    def _load_font(self):
        for f in FONT_FILES:
            if f.exists():
                fid = QtGui.QFontDatabase.addApplicationFont(str(f))
                fams = QtGui.QFontDatabase.applicationFontFamilies(fid) if fid != -1 else []
                if fams:
                    return fams[0]
        return FALLBACK_FONT

    def _font(self, px, bold=True):
        f = QtGui.QFont(self.fonts_family)
        f.setPixelSize(max(8, int(px)))
        f.setBold(bold)
        return f

    def _pixmaps(self):
        """두더지 크기(S)가 바뀔 때만 그림을 다시 만들어 둠."""
        S = int(self.game.S)
        if self._pix.get("S") == S:
            return self._pix
        smooth, keep = QtCore.Qt.SmoothTransformation, QtCore.Qt.KeepAspectRatio
        mole, hit, hammer = _load_pixmap("mole.png"), _load_pixmap("mole_hit.png"), _load_pixmap("hammer.png")
        self._pix = {
            "S": S,
            "mole": mole.scaled(S, S, keep, smooth) if mole else _vector_mole(S, False),
            "hit": hit.scaled(S, S, keep, smooth) if hit else _vector_mole(S, True),
            "hammer": hammer.scaledToHeight(int(S * 1.1), smooth) if hammer else None,
        }
        return self._pix

    def _background(self):
        """모래색 땅 + 흙 자국 + 구멍 9개를 한 장으로 미리 그려 둠."""
        key = (self.width(), self.height(), int(self.game.S))
        if self._bg is not None and self._size_key == key:
            return self._bg
        w, h = self.width(), self.height()
        pix = QtGui.QPixmap(w, h)
        pix.fill(SAND)
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        rng = random.Random(7)
        pen = QtGui.QPen(SAND_MARK, 3.5)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen)
        for _ in range(int(w * h / 9000)):
            x, y = rng.uniform(0, w), rng.uniform(0, h)
            length = rng.uniform(10, 34)
            ang = math.radians(rng.uniform(-14, 14))
            dx, dy = math.cos(ang) * length / 2, math.sin(ang) * length / 2
            p.drawLine(QtCore.QPointF(x - dx, y - dy), QtCore.QPointF(x + dx, y + dy))
        S = self.game.S
        for cx, cy in self.game.holes:
            p.save()
            p.translate(cx, cy - MOLE_NOSE_Y * S + MOLE_BOTTOM_Y * S)
            self._draw_hole(p, S)
            p.restore()
        p.end()
        self._bg, self._size_key = pix, key
        return pix

    def _draw_hole(self, p, S):
        y = (HOLE_MID_Y + 0.02 - MOLE_BOTTOM_Y) * S
        p.setPen(QtGui.QPen(HOLE_EDGE, 3))
        p.setBrush(HOLE_RIM)
        p.drawEllipse(QtCore.QPointF(0, y), 0.39 * S, 0.105 * S)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(HOLE_DARK)
        p.drawEllipse(QtCore.QPointF(0, y + 0.004 * S), 0.33 * S, 0.075 * S)

    # ── 그리기 ──
    def paintEvent(self, event):
        now = time.time()
        g = self.game
        g.set_size(self.width(), self.height())
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        p.drawPixmap(0, 0, self._background())

        pix = self._pixmaps()
        if g.state in ("title", "starting", "result"):
            self._draw_mole(p, g.menu, now, pix, bob=(g.state != "starting"))
        for m in g.moles:
            self._draw_mole(p, m, now, pix)

        self._draw_hover_ring(p, now)
        for e in g.effects:
            self._draw_effect(p, e, now)
        self._draw_texts(p, now)

    def _draw_mole(self, p, m, now, pix, bob=False):
        g, S = self.game, self.game.S
        cx, cy = g.hole_xy(m.hole)
        tilt, squash, rise, img = 0.0, 1.0, 1.0, pix["mole"]
        t = after = 0.0
        hitting = m.state == "hit"
        impact = False
        if m.state == "up":
            k = min((now - m.t0) / POP_SEC, 1.0)
            rise = 1 - (1 - k) ** 3
            if bob and k >= 1.0:
                tilt = 4 * math.sin(now * 2.6)                    # 시작/다시하기 두더지는 살짝 흔들려서 눈에 띄게
        elif m.state == "sink":
            rise = 1 - min((now - m.t_state) / SINK_SEC, 1.0)
        elif hitting:
            t = (now - m.t_state) / HIT_SEC
            impact = t >= HIT_AT
            after = min((t - HIT_AT) / (1 - HIT_AT), 1.0) if impact else 0.0
            squash = 1.0 - 0.22 * math.sin(after * math.pi) if impact else 1.0
            img = pix["hit"] if impact else pix["mole"]
        if rise <= 0.02:
            return

        top = cy - MOLE_NOSE_Y * S
        p.save()
        p.translate(cx, top + MOLE_BOTTOM_Y * S)                      # 구멍 아래쪽 기준
        if rise < 1.0:
            self._draw_hole(p, S)
            clip_bottom = (HOLE_MID_Y + (1.0 - HOLE_MID_Y) * rise ** 2 - MOLE_BOTTOM_Y) * S
            p.setClipRect(QtCore.QRectF(-S, -2 * S, 2 * S, 2 * S + clip_bottom))
            p.translate(0, (1.0 - rise) * RISE_DEPTH * S)
        p.rotate(tilt)
        p.scale(1.0, squash)
        p.drawPixmap(QtCore.QPointF(-S / 2, -MOLE_BOTTOM_Y * S), img)
        p.restore()

        if hitting:
            self._draw_hammer(p, cx, cy, t, pix)
            if impact:
                self._draw_star(p, cx - 0.28 * S, cy - 0.45 * S, after)

    def _draw_hammer(self, p, cx, cy, t, pix):
        hammer = pix["hammer"]
        if hammer is None:
            return
        if t < HIT_AT:
            s = t / HIT_AT
            angle = 28 - 78 * s * s
        else:
            angle = -50 + 8 * math.sin(min((t - HIT_AT) / (1 - HIT_AT), 1.0) * math.pi)
        pw, ph = hammer.width(), hammer.height()
        S = self.game.S
        p.save()
        p.translate(cx + 0.60 * S, cy + 0.16 * S)
        p.rotate(angle)
        p.drawPixmap(QtCore.QPointF(-pw / 2, -HAMMER_PIVOT_Y * ph), hammer)
        p.restore()

    def _draw_star(self, p, x, y, frac):
        scale = math.sin(min(frac, 1.0) * math.pi) * 1.15
        if scale <= 0.01:
            return
        S = self.game.S
        r_out, r_in = 0.14 * S, 0.06 * S
        pts = []
        for i in range(16):
            ang = math.radians(i * 22.5 - 90)
            r = r_out if i % 2 == 0 else r_in
            pts.append(QtCore.QPointF(r * math.cos(ang), r * math.sin(ang)))
        p.save()
        p.translate(x, y)
        p.scale(scale, scale)
        p.setPen(QtGui.QPen(INK, 3))
        p.setBrush(QtGui.QColor(255, 205, 60))
        p.drawPolygon(QtGui.QPolygonF(pts))
        p.restore()

    def _draw_hover_ring(self, p, now):
        g = self.game
        if g.hover_target is None or g.hover_progress <= 0:
            return
        cx, cy = g.hole_xy(g.hover_target.hole)
        R = 0.5 * g.S
        ring = QtCore.QRectF(cx - R, cy + 0.05 * g.S - R, 2 * R, 2 * R)
        p.setBrush(QtCore.Qt.NoBrush)
        p.setPen(QtGui.QPen(WHITE, 12))
        p.drawEllipse(ring)
        pen = QtGui.QPen(GREEN, 8)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(ring, 90 * 16, int(-360 * 16 * g.hover_progress))

    def _draw_effect(self, p, e, now):
        age = now - e["t"]
        if e["kind"] == "ripple":                                  # 클릭한 자리에 퍼지는 물결 (어디를 눌렀는지 보여줌)
            k = min(age / 0.45, 1.0)
            if k >= 1.0:
                return
            color = QtGui.QColor(GREEN if e["hit"] else INK_SOFT)
            color.setAlphaF(1.0 - k)
            p.setBrush(QtCore.Qt.NoBrush)
            p.setPen(QtGui.QPen(color, 6))
            r = 18 + 70 * k
            p.drawEllipse(QtCore.QPointF(e["x"], e["y"]), r, r)
        elif e["kind"] == "popup":                                 # +10 점수 글자가 위로 떠오름
            k = min(age / 0.9, 1.0)
            if k >= 1.0:
                return
            size = self.game.S * 0.26
            self._outlined_text(p, e["x"], e["y"] - 60 * k, e["text"], self._font(size),
                                YELLOW, INK, 7, alpha=1.0 - k * k)

    def _outlined_text(self, p, cx, cy, text, font, fill, outline, width, alpha=1.0):
        """(cx, cy)를 가운데로 하는 테두리 글씨 — 어떤 배경에서도 잘 보임."""
        fm = QtGui.QFontMetricsF(font)
        path = QtGui.QPainterPath()
        path.addText(cx - fm.horizontalAdvance(text) / 2, cy + (fm.ascent() - fm.descent()) / 2, font, text)
        out_c, fill_c = QtGui.QColor(outline), QtGui.QColor(fill)
        out_c.setAlphaF(alpha)
        fill_c.setAlphaF(alpha)
        pen = QtGui.QPen(out_c, width)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawPath(path)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(fill_c)
        p.drawPath(path)

    def _draw_texts(self, p, now):
        g, w, h = self.game, self.width(), self.height()
        big, mid, small = h * 0.075, h * 0.036, h * 0.028
        cx = w / 2
        mx, my = g.hole_xy(g.menu.hole)

        if g.state == "title":
            self._outlined_text(p, cx, h * 0.085, "두더지 잡기!", self._font(big), WHITE, INK, 9)
            self._outlined_text(p, cx, h * 0.165, "두더지를 바라보고 윙크하면 잡혀요", self._font(mid), WHITE, INK, 6)
            self._outlined_text(p, mx, my + 0.62 * g.S, "이 두더지를 잡으면 시작!", self._font(mid), YELLOW, INK, 6)
        elif g.state == "starting":
            self._outlined_text(p, cx, h * 0.10, "준비~!", self._font(big * 1.2), YELLOW, INK, 9)
        elif g.state == "playing":
            self._draw_hud(p, now)
        else:                                                         # result
            self._outlined_text(p, cx, h * 0.075, "게임 끝!", self._font(big), WHITE, INK, 9)
            self._outlined_text(p, cx, h * 0.150, f"점수 {g.score}점", self._font(big * 0.9), YELLOW, INK, 8)
            stat = f"잡은 두더지 {g.hits}마리 · 놓친 두더지 {g.misses}마리 · 최대 콤보 {g.max_combo}"
            self._outlined_text(p, cx, h * 0.218, stat, self._font(small), WHITE, INK, 5)
            best = f"최고 점수 {g.best}점" + ("  — 새 기록!" if g.new_best else "")
            self._outlined_text(p, cx, h * 0.265, best, self._font(small), ORANGE if g.new_best else WHITE, INK, 5)
            self._outlined_text(p, mx, my + 0.62 * g.S, "이 두더지를 잡으면 다시 하기!", self._font(mid), YELLOW, INK, 6)

        p.setPen(INK_SOFT)
        p.setFont(self._font(h * 0.02, bold=False))
        p.drawText(QtCore.QRectF(0, 0, w - 24, h - 14), QtCore.Qt.AlignRight | QtCore.Qt.AlignBottom,
                   "ESC: 종료   SPACE: 시작 / 다시 하기")

    def _draw_hud(self, p, now):
        g, w, h = self.game, self.width(), self.height()
        size = h * 0.062
        self._outlined_text(p, w * 0.12, h * 0.06, f"점수 {g.score}", self._font(size), WHITE, INK, 7)
        if g.combo >= 2:
            self._outlined_text(p, w * 0.88, h * 0.06, f"콤보 x{g.combo}!", self._font(size), YELLOW, INK, 7)

        bar_w, bar_h = w * 0.34, h * 0.03                             # 남은 시간 막대 (가운데 위)
        x0, y0 = (w - bar_w) / 2, h * 0.045
        frac = g.time_left(now) / ROUND_SEC
        p.setPen(QtGui.QPen(INK, 4))
        p.setBrush(QtGui.QColor(255, 255, 255, 200))
        p.drawRoundedRect(QtCore.QRectF(x0, y0, bar_w, bar_h), bar_h / 2, bar_h / 2)
        if frac > 0:
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(RED if frac < 0.2 else GREEN)
            p.drawRoundedRect(QtCore.QRectF(x0 + 3, y0 + 3, max(bar_h - 6, (bar_w - 6) * frac), bar_h - 6),
                              (bar_h - 6) / 2, (bar_h - 6) / 2)
        self._outlined_text(p, w / 2, y0 + bar_h + h * 0.03, f"{math.ceil(g.time_left(now))}초",
                            self._font(h * 0.03), WHITE, INK, 5)


def main():
    ap = argparse.ArgumentParser(description="눈동자 마우스 시연용 두더지 잡기")
    ap.add_argument("--windowed", action="store_true", help="전체화면 대신 창으로 실행 (테스트용)")
    ap.add_argument("--hover", type=float, default=0.0, metavar="SEC",
                    help="두더지 위에 이 시간(초) 머물면 잡힘 (기본 0 = 클릭으로만)")
    ap.add_argument("--hide-cursor", action="store_true", help="윈도우 마우스 커서 숨기기")
    args = ap.parse_args()

    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    app = QtWidgets.QApplication(sys.argv)
    win = GameWindow(windowed=args.windowed, hover_sec=args.hover, hide_cursor=args.hide_cursor)
    if args.windowed:
        win.show()
    else:
        win.showFullScreen()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
