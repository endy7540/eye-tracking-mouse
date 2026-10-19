# -*- coding: utf-8 -*-
"""
seal_cursor.py — 테마색 바둑알 커서 (화면 전체를 덮는 투명 창)

화면 전체 크기의 "투명하고 클릭이 그대로 통과되는" 창 위에 테마색 바둑알을 시선 위치에 그립니다.
클릭이 통과되기 때문에 커서가 버튼 위에 있어도 그 버튼은 정상적으로 눌립니다.
(예전엔 물개 얼굴이었어서 파일·클래스 이름이 seal_cursor / SealCursorOverlay입니다.
 main.py가 이 이름으로 불러 쓰고 있어서 이름은 그대로 두었습니다.)

그리는 것
    - 커서: 테마색 바둑알 (paint_stone). 왼쪽 위에서 빛을 받은 납작한 볼록 돌 + 아래쪽 두께 + 그림자.
      광택은 은은하게(CURSOR_GLOSS). 진하기는 메뉴창 "커서 투명도"로 조절 (set_opacity, 투명도 = 1 - 진하기)
    - 시선 잔상: 붓 자국처럼 커서 쪽은 굵고 꼬리 쪽은 가늘게 사라지는 부드러운 곡선 + 아래 그림자 (메뉴에서 ON/OFF)
      지나온 점들을 부드러운 곡선(캣멀-롬)으로 이은 뒤, 굵기가 변하는 띠 하나로 그립니다.
    - 하이라이트: 시선이 누를 수 있는 버튼 위에 있으면 커서 둘레에 굵은 테마색(진한 색) 테두리
    - 응시 게이지: 버튼을 바라보는 동안 커서 둘레에 원형 차트처럼 차오르는 호 (메뉴창 안에서는 윙크로만 눌러서 안 나옴)
    - 눈 인식 안 됨: 커서 오른쪽 위에 빨간 X
    - 클릭 체크: 시선으로 클릭(윙크·응시)될 때마다 커서 위에 초록 체크(✓)가 톡 튀어나왔다 사라짐
    - 뒤로가기 표시: 두 눈 3번 깜빡임으로 뒤로가기 할 때 같은 자리에 파란 동그라미 + 왼쪽 화살표(←)
    - 일시정지 중에는 아무것도 그리지 않음 (프로그램은 뒤에서 계속 실행)

paint_stone()은 메뉴창의 테마 동그라미(무광 바둑알)에서도 같이 씁니다.

성능: 화면 전체를 매번 다시 그리면 느려서, 커서와 잔상이 있는 영역만 골라 다시 그립니다(_schedule).
"""
import math
import time
from collections import deque

from PyQt5 import QtWidgets, QtCore, QtGui

from . import theme
from .gaze_widgets import setup_floating_window

CURSOR_R = 34              # 커서 반지름 (지름 68px — 기본 마우스 커서보다 크게)
CURSOR_GLOSS = 0.35        # 커서 광택 (0 = 무광 ~ 0.55 = 반짝임). 은은하게
SWATCH_GLOSS = 0.18        # 메뉴창 테마 동그라미 광택 (거의 무광)
DEFAULT_OPACITY = 0.6      # 처음 진하기 (= 투명도 40%)
MIN_OPACITY = 0.2          # 가장 투명할 때 (투명도 80%) — 이보다 흐리면 커서를 잃어버림
MAX_OPACITY = 1.0          # 가장 진할 때 (투명도 0%)
OPACITY_STEP = 0.1         # 메뉴에서 -/+ 한 번에 바뀌는 양 (10%)
TRAIL_SEC = 0.8            # 잔상이 남아 있는 시간
TRAIL_W = 18               # 잔상 굵기 (커서 쪽 가장 굵은 곳)
TRAIL_SUBDIV = 4           # 점 사이를 부드럽게 이을 때 나누는 수 (클수록 매끈, 대신 조금 무거움)
CHECK_SEC = 0.7            # 클릭 체크 표시가 보이는 시간
CHECK_R = 16               # 체크 동그라미 반지름
BADGE_COLOR = {"check": QtGui.QColor(70, 180, 110), "back": QtGui.QColor(70, 140, 230)}


def _mix(a, b, t):
    """색 a와 b를 t(0~1) 비율로 섞음."""
    return QtGui.QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                        int(a.blue() + (b.blue() - a.blue()) * t))


def paint_stone(p, cx, cy, r, th, opacity=1.0, gloss=CURSOR_GLOSS):
    """(cx, cy)에 반지름 r짜리 테마색 바둑알. th = theme.current() 같은 색 묶음, gloss = 광택 세기.
    아래부터 차례로: 그림자 → 돌의 두께(아래쪽 진한 테두리) → 볼록한 윗면(빛을 받은 쪽이 밝게) → 은은한 광택."""
    main, deep = th["main"], th["deep"]
    p.save()
    p.setPen(QtCore.Qt.NoPen)
    # 1) 그림자: 오른쪽 아래로 살짝 떨어진 흐린 타원
    sc = QtCore.QPointF(cx + r * 0.10, cy + r * 0.26)
    g = QtGui.QRadialGradient(sc, r * 1.15)
    g.setColorAt(0.0, QtGui.QColor(20, 25, 35, int(95 * opacity + 25)))
    g.setColorAt(0.7, QtGui.QColor(20, 25, 35, int(35 * opacity + 10)))
    g.setColorAt(1.0, QtGui.QColor(20, 25, 35, 0))
    p.setBrush(QtGui.QBrush(g))
    p.drawEllipse(sc, r * 1.15, r * 1.05)
    # 2) 돌의 두께: 윗면보다 조금 아래로 내려간 진한 원 (아래쪽에 테두리처럼 보임)
    p.setBrush(theme.with_alpha(_mix(deep, QtGui.QColor(0, 0, 0), 0.2), min(1.0, opacity + 0.15)))
    p.drawEllipse(QtCore.QPointF(cx, cy + r * 0.13), r, r)
    # 3) 윗면: 왼쪽 위가 밝고 가장자리로 갈수록 진해지는 볼록면
    light = _mix(main, QtGui.QColor(255, 255, 255), 0.25 + gloss * 0.5)
    edge = _mix(main, deep, 0.45)
    g = QtGui.QRadialGradient(QtCore.QPointF(cx - r * 0.35, cy - r * 0.40), r * 1.55)
    g.setColorAt(0.0, theme.with_alpha(light, opacity))
    g.setColorAt(0.45, theme.with_alpha(main, opacity))
    g.setColorAt(1.0, theme.with_alpha(edge, opacity))
    p.setBrush(QtGui.QBrush(g))
    p.drawEllipse(QtCore.QPointF(cx, cy), r, r)
    # 4) 광택: 왼쪽 위의 흐린 빛 (gloss가 작을수록 은은하게)
    hc = QtCore.QPointF(cx - r * 0.32, cy - r * 0.38)
    g = QtGui.QRadialGradient(hc, r * 0.55)
    g.setColorAt(0.0, QtGui.QColor(255, 255, 255, int(255 * gloss * 0.9)))
    g.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
    p.setBrush(QtGui.QBrush(g))
    p.drawEllipse(hc, r * 0.55, r * 0.42)
    p.restore()


def paint_badge(p, cx, cy, rr, kind):
    """(cx, cy)에 반지름 rr짜리 표시를 그림. kind: "check"(초록 ✓) / "back"(파랑 ←)."""
    p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 3))
    p.setBrush(BADGE_COLOR[kind])
    p.drawEllipse(QtCore.QPointF(cx, cy), rr, rr)
    pen = QtGui.QPen(QtGui.QColor(255, 255, 255), max(2.5, rr * 0.22))
    pen.setCapStyle(QtCore.Qt.RoundCap)
    pen.setJoinStyle(QtCore.Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(QtCore.Qt.NoBrush)
    if kind == "check":
        p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(cx - rr * 0.45, cy + rr * 0.02),
                                        QtCore.QPointF(cx - rr * 0.1, cy + rr * 0.38),
                                        QtCore.QPointF(cx + rr * 0.5, cy - rr * 0.35)]))
    else:                                         # 왼쪽 화살표: 가로줄 + 화살촉
        p.drawLine(QtCore.QPointF(cx + rr * 0.5, cy), QtCore.QPointF(cx - rr * 0.45, cy))
        p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(cx - rr * 0.05, cy - rr * 0.42),
                                        QtCore.QPointF(cx - rr * 0.47, cy),
                                        QtCore.QPointF(cx - rr * 0.05, cy + rr * 0.42)]))


def smooth_trail(points, subdiv=TRAIL_SUBDIV):
    """(시각, x, y) 점들을 캣멀-롬 곡선으로 부드럽게 이음. 시각도 같이 이어서 돌려줌."""
    if len(points) < 3:
        return list(points)
    P = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for j in range(subdiv):
            t = j / subdiv
            t2, t3 = t * t, t * t * t
            vals = []
            for k in range(3):
                vals.append(0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                                   + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3))
            out.append(tuple(vals))
    out.append(points[-1])
    return out


class SealCursorOverlay(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        setup_floating_window(self, click_through=True)
        self.setGeometry(QtWidgets.QApplication.primaryScreen().geometry())

        self.pos_ = None                 # 창 안의 좌표 (QPointF)
        self.trail = deque()             # (시각, QPointF)
        self.trail_on = True
        self.paused = False
        self.gauge = 0.0
        self.highlight = False
        self.eye_lost = False           # 눈 인식 안 됨 → 오른쪽 위 빨간 X
        self.check_t = None             # 표시(체크/뒤로가기)를 시작한 시각 (None = 표시 안 함)
        self.badge = "check"            # 지금 보여줄 표시 종류
        self.hidden = False             # 잠깐 커서를 숨겨야 할 때 (set_hidden)
        self.opacity = DEFAULT_OPACITY  # 커서 진하기 (메뉴 "커서 투명도"로 조절)
        self._dirty = QtCore.QRect()     # 지난번에 그린 영역 (다음에 지워야 할 곳)

        self.fade_timer = QtCore.QTimer(self)    # 시선이 멈춰 있어도 잔상이 서서히 사라지도록
        self.fade_timer.timeout.connect(self._fade)
        self.fade_timer.start(33)

    # ── main.py에서 호출 ─────────────────────────────────────────
    def move_to(self, gx, gy, now):
        """화면 좌표 (gx, gy)로 커서 이동."""
        self.pos_ = QtCore.QPointF(self.mapFromGlobal(QtCore.QPoint(int(gx), int(gy))))
        if self.trail_on:
            self.trail.append((now, QtCore.QPointF(self.pos_)))
        self._schedule()

    def set_trail(self, on):
        self.trail_on = on
        if not on:
            self.trail.clear()
        self._schedule()

    def set_paused(self, paused):
        self.paused = paused
        self.trail.clear()
        self.update()

    def set_gauge(self, frac):
        self.gauge = frac
        self._schedule()

    def set_highlight(self, on):
        self.highlight = on
        self._schedule()

    def set_hidden(self, hidden):
        """커서를 잠깐 숨김 (창은 그대로 두고 아무것도 그리지 않음)."""
        if self.hidden != hidden:
            self.hidden = hidden
            self.trail.clear()
            self.update()

    def set_opacity(self, opacity):
        """커서 진하기 (MIN_OPACITY ~ MAX_OPACITY). 메뉴의 "커서 투명도"는 1 - 진하기로 보여줌."""
        self.opacity = max(MIN_OPACITY, min(MAX_OPACITY, round(opacity, 2)))
        self._schedule()

    def refresh_theme(self):
        """테마가 바뀌었을 때 다시 그리기 (색은 그릴 때마다 theme.current()에서 읽음)."""
        self.update()

    def show_check(self):
        """클릭됐다는 표시: 커서 위에 초록 체크가 0.7초 동안 톡 튀어나왔다 사라짐."""
        self.show_badge("check")

    def show_badge(self, kind):
        """kind: "check"(클릭) / "back"(뒤로가기). 커서 위에 0.7초 동안 톡 튀어나왔다 사라짐."""
        self.badge = kind
        self.check_t = time.time()
        self._schedule()

    def set_eye_lost(self, lost):
        if self.eye_lost != lost:
            self.eye_lost = lost
            self._schedule()

    # ── 다시 그릴 영역 계산 ───────────────────────────────────────
    def _fade(self):
        now = time.time()
        popped = False
        while self.trail and now - self.trail[0][0] > TRAIL_SEC:
            self.trail.popleft()
            popped = True
        if self.check_t is not None and now - self.check_t > CHECK_SEC:
            self.check_t = None
            self._schedule()                     # 사라진 체크 자리를 지움
        elif popped or self.trail or self.check_t is not None:
            self._schedule()
        if popped and not self.trail:
            self.update()                        # 잔상이 마지막으로 다 사라진 순간: 화면 전체를 한 번 깨끗이 다시 그려 찌꺼기 제거

    def _bounds(self):
        rect = QtCore.QRect()
        if self.pos_ is not None:
            m = CURSOR_R + 26
            rect = QtCore.QRect(int(self.pos_.x()) - m, int(self.pos_.y()) - m, 2 * m, 2 * m)
            if self.check_t is not None:          # 체크는 커서 위쪽에 그려지므로 그 자리까지 다시 그림
                top = int(self.pos_.y() - (CURSOR_R + 28 + CHECK_R * 1.3))
                rect = rect.united(QtCore.QRect(int(self.pos_.x()) - 34, top - 4, 68, 68))
        tm = TRAIL_W * 2 + 8                      # 잔상 굵기 + 그림자 + 곡선 보정으로 삐져나오는 여유
        for _, pt in self.trail:
            rect = rect.united(QtCore.QRect(int(pt.x()) - tm, int(pt.y()) - tm, 2 * tm, 2 * tm))
        return rect

    def _schedule(self):
        new = self._bounds()
        self.update(new.united(self._dirty))
        self._dirty = new

    # ── 그리기 ───────────────────────────────────────────────────
    def _paint_trail(self, p, th):
        """붓 자국 잔상: 오래된 쪽(꼬리)은 가늘고 연하게, 커서 쪽(머리)은 굵고 진하게. 그림자를 먼저 깔고 그 위에 띠."""
        now = time.time()
        pts = smooth_trail([(t, q.x(), q.y()) for t, q in self.trail])
        if len(pts) < 2:
            return
        left, right = [], []
        n = len(pts)
        for i, (t, x, y) in enumerate(pts):
            ax, ay = pts[max(i - 1, 0)][1:]
            bx, by = pts[min(i + 1, n - 1)][1:]
            tx, ty = bx - ax, by - ay
            L = math.hypot(tx, ty) or 1.0
            nx, ny = -ty / L, tx / L
            f = max(0.0, min(1.0, 1.0 - (now - t) / TRAIL_SEC))       # 1 = 방금 지나간 곳, 0 = 곧 사라질 곳
            w = TRAIL_W * (0.06 + 0.94 * f ** 1.3) / 2
            left.append(QtCore.QPointF(x + nx * w, y + ny * w))
            right.append(QtCore.QPointF(x - nx * w, y - ny * w))
        poly = QtGui.QPolygonF(left + right[::-1])
        tail, head = QtCore.QPointF(pts[0][1], pts[0][2]), QtCore.QPointF(pts[-1][1], pts[-1][2])
        p.setPen(QtCore.Qt.NoPen)
        # 그림자 (오른쪽 아래로 살짝, 두 겹으로 부드럽게)
        for dx, dy, a in ((2.0, 3.0, 0.16), (3.5, 5.5, 0.08)):
            g = QtGui.QLinearGradient(tail, head)
            g.setColorAt(0.0, QtGui.QColor(25, 35, 55, 0))
            g.setColorAt(1.0, QtGui.QColor(25, 35, 55, int(255 * a)))
            p.setBrush(QtGui.QBrush(g))
            p.drawPolygon(poly.translated(dx, dy))
        # 띠: 꼬리는 연한 테마색으로 사라지고 머리는 진한 테마색
        g = QtGui.QLinearGradient(tail, head)
        g.setColorAt(0.0, theme.with_alpha(th["light"], 0.0))
        g.setColorAt(0.5, theme.with_alpha(_mix(th["light"], th["main"], 0.6), 0.45))
        g.setColorAt(1.0, theme.with_alpha(th["main"], 0.8))
        p.setBrush(QtGui.QBrush(g))
        p.drawPolygon(poly)

    def paintEvent(self, event):
        if self.paused or self.hidden or self.pos_ is None:
            return
        th = theme.current()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        # 1) 시선 잔상 (붓 자국)
        if self.trail_on and len(self.trail) > 1:
            self._paint_trail(p, th)

        # 여기부터는 커서 가운데를 (0, 0)으로 놓고 그림
        p.translate(self.pos_)
        r = CURSOR_R

        # 2) 하이라이트: 누를 수 있는 곳 위 → 굵은 테마색 테두리 (+ 바깥쪽 흰 빛)
        if self.highlight:
            p.setBrush(QtCore.Qt.NoBrush)
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 170), 12))
            p.drawEllipse(QtCore.QPointF(0, 0), r + 8, r + 8)
            p.setPen(QtGui.QPen(th["deep"], 6))
            p.drawEllipse(QtCore.QPointF(0, 0), r + 8, r + 8)

        # 3) 커서 본체: 테마색 바둑알 (진하기 = self.opacity)
        paint_stone(p, 0, 0, r, th, self.opacity, CURSOR_GLOSS)

        # 4) 응시 게이지: 원형 차트처럼 12시 방향부터 시계방향으로 차오름
        if self.gauge > 0:
            gr = r + 16
            rect = QtCore.QRectF(-gr, -gr, 2 * gr, 2 * gr)
            p.setBrush(QtCore.Qt.NoBrush)
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 160), 9))
            p.drawEllipse(rect)
            pen = QtGui.QPen(th["main"], 7)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(rect, 90 * 16, int(-360 * 16 * self.gauge))

        # 5) 눈 인식 안 됨: 커서 오른쪽 위에 빨간 X (흰 동그라미 위에 그려서 어떤 배경에서도 보이게)
        if self.eye_lost:
            xc, yc = r * 0.75, -r * 0.75
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(255, 255, 255, 230))
            p.drawEllipse(QtCore.QPointF(xc, yc), 13, 13)
            pen = QtGui.QPen(theme.RED, 5)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen)
            d = 7
            p.drawLine(QtCore.QPointF(xc - d, yc - d), QtCore.QPointF(xc + d, yc + d))
            p.drawLine(QtCore.QPointF(xc - d, yc + d), QtCore.QPointF(xc + d, yc - d))

        # 6) 클릭 체크(✓) / 뒤로가기(←): 커서 바로 위에 톡 커졌다가, 끝에서 서서히 사라짐
        if self.check_t is not None:
            age = time.time() - self.check_t
            if age <= CHECK_SEC:
                f = age / CHECK_SEC
                pop = 0.6 + 0.6 * min(age / 0.12, 1.0) - 0.2 * min(max((age - 0.12) / 0.1, 0.0), 1.0)
                alpha = 1.0 if f < 0.6 else max(0.0, 1.0 - (f - 0.6) / 0.4)
                cy = -r - 22 - 6 * min(f * 2, 1.0)           # 살짝 위로 떠오름
                p.setOpacity(alpha)
                paint_badge(p, 0, cy, CHECK_R * pop, self.badge)
                p.setOpacity(1.0)
