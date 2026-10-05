# -*- coding: utf-8 -*-
"""
seal_cursor.py — 반투명 물개 얼굴 커서 (화면 전체를 덮는 투명 창)

화면 전체 크기의 "투명하고 클릭이 그대로 통과되는" 창 위에 물개 얼굴(assets/seal_cursor.png)을
시선 위치에 그립니다. 클릭이 통과되기 때문에 커서가 버튼 위에 있어도 그 버튼은 정상적으로 눌립니다.

그리는 것
    - 물개 얼굴: 반투명(OPACITY), 기본 마우스 커서보다 큰 크기(SEAL_PX)
    - 시선 궤적(잔상): 최근 TRAIL_SEC 동안 지나온 자리에 점점 흐려지는 점과 선 (메뉴에서 ON/OFF)
    - 하이라이트: 시선이 누를 수 있는 버튼 위에 있으면 커서 둘레에 굵은 주황 테두리
    - 응시 게이지: 버튼을 바라보는 동안 커서 둘레에 원형 차트처럼 차오르는 호
    - 클릭 체크: 시선으로 클릭(윙크·응시·데모 버튼)될 때마다 커서 위에 초록 체크(✓)가 톡 튀어나왔다 사라짐
    - 뒤로가기 표시: 두 눈 3번 깜빡임으로 뒤로가기 할 때 같은 자리에 파란 동그라미 + 왼쪽 화살표(←)
    - 일시정지 중에는 아무것도 그리지 않음 (프로그램은 뒤에서 계속 실행)

성능: 화면 전체를 매번 다시 그리면 느려서, 커서와 궤적이 있는 영역만 골라 다시 그립니다(_schedule).
"""
import time
from collections import deque

from PyQt5 import QtWidgets, QtCore, QtGui

import theme
from gaze_widgets import setup_floating_window

SEAL_PX = 76          # 물개 커서 크기 (기본 마우스 커서보다 크게)
OPACITY = 0.8         # 반투명 정도 (1.0 = 불투명)
TRAIL_SEC = 0.8       # 잔상이 남아 있는 시간
TRAIL_COLOR = QtGui.QColor(110, 160, 220)
CHECK_SEC = 0.7       # 클릭 체크 표시가 보이는 시간
CHECK_R = 16          # 체크 동그라미 반지름
BADGE_COLOR = {"check": QtGui.QColor(70, 180, 110), "back": QtGui.QColor(70, 140, 230)}


def paint_badge(p, cx, cy, rr, kind):
    """(cx, cy)에 반지름 rr짜리 표시를 그림. kind: "check"(초록 ✓) / "back"(파랑 ←). 물개 커서·돋보기 공용."""
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


class SealCursorOverlay(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        setup_floating_window(self, click_through=True)
        self.setGeometry(QtWidgets.QApplication.primaryScreen().geometry())

        self.seal = theme.pixmap("seal_cursor.png").scaled(
            SEAL_PX, SEAL_PX, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self.pos_ = None                 # 창 안의 좌표 (QPointF)
        self.trail = deque()             # (시각, QPointF)
        self.trail_on = True
        self.paused = False
        self.gauge = 0.0
        self.highlight = False
        self.eye_lost = False           # 눈 인식 안 됨 → 오른쪽 위 빨간 X
        self.check_t = None             # 표시(체크/뒤로가기)를 시작한 시각 (None = 표시 안 함)
        self.badge = "check"            # 지금 보여줄 표시 종류
        self.hidden = False             # 돋보기를 켜 둔 동안 숨김 (돋보기 십자가 커서 역할)
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
        """돋보기를 쓰는 동안 물개 커서를 숨김. 창은 그대로 두고 아무것도 그리지 않음 → 돋보기 화면에 안 찍힘."""
        if self.hidden != hidden:
            self.hidden = hidden
            self.trail.clear()
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
        while self.trail and now - self.trail[0][0] > TRAIL_SEC:
            self.trail.popleft()
        if self.check_t is not None and now - self.check_t > CHECK_SEC:
            self.check_t = None
            self._schedule()                     # 사라진 체크 자리를 지움
        elif self.trail or self.check_t is not None:
            self._schedule()

    def _bounds(self):
        rect = QtCore.QRect()
        if self.pos_ is not None:
            m = SEAL_PX // 2 + 20
            rect = QtCore.QRect(int(self.pos_.x()) - m, int(self.pos_.y()) - m, 2 * m, 2 * m)
            if self.check_t is not None:          # 체크는 커서 위쪽에 그려지므로 그 자리까지 다시 그림
                top = int(self.pos_.y() - SEAL_PX / 2 - 22 - CHECK_R * 1.3)
                rect = rect.united(QtCore.QRect(int(self.pos_.x()) - 30, top - 4, 60, 60))
        for _, pt in self.trail:
            rect = rect.united(QtCore.QRect(int(pt.x()) - 16, int(pt.y()) - 16, 32, 32))
        return rect

    def _schedule(self):
        new = self._bounds()
        self.update(new.united(self._dirty))
        self._dirty = new

    # ── 그리기 ───────────────────────────────────────────────────
    def paintEvent(self, event):
        if self.paused or self.hidden or self.pos_ is None:
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

        # 1) 시선 궤적(잔상): 오래된 점일수록 작고 흐리게
        if self.trail_on and len(self.trail) > 1:
            now = time.time()
            pts = list(self.trail)
            for (t0, a), (t1, b) in zip(pts[:-1], pts[1:]):
                life = max(0.0, 1.0 - (now - t1) / TRAIL_SEC)
                c = QtGui.QColor(TRAIL_COLOR)
                c.setAlphaF(0.45 * life)
                pen = QtGui.QPen(c, 2 + 8 * life)
                pen.setCapStyle(QtCore.Qt.RoundCap)
                p.setPen(pen)
                p.drawLine(a, b)
            p.setPen(QtCore.Qt.NoPen)
            for t0, pt in pts[::3]:
                life = max(0.0, 1.0 - (now - t0) / TRAIL_SEC)
                c = QtGui.QColor(255, 255, 255)
                c.setAlphaF(0.7 * life)
                p.setBrush(c)
                p.drawEllipse(pt, 3 + 4 * life, 3 + 4 * life)

        r = SEAL_PX / 2
        # 2) 하이라이트: 누를 수 있는 곳 위 → 굵은 주황 테두리 (+ 바깥쪽 흰 빛)
        if self.highlight:
            p.setBrush(QtCore.Qt.NoBrush)
            glow = QtGui.QColor(255, 255, 255, 170)
            p.setPen(QtGui.QPen(glow, 12))
            p.drawEllipse(self.pos_, r + 6, r + 6)
            p.setPen(QtGui.QPen(theme.HIGHLIGHT, 6))
            p.drawEllipse(self.pos_, r + 6, r + 6)

        # 3) 물개 얼굴 (반투명)
        p.setOpacity(OPACITY)
        p.drawPixmap(QtCore.QPointF(self.pos_.x() - self.seal.width() / 2,
                                    self.pos_.y() - self.seal.height() / 2), self.seal)
        p.setOpacity(1.0)

        # 4) 응시 게이지: 원형 차트처럼 12시 방향부터 시계방향으로 차오름
        if self.gauge > 0:
            gr = r + 14
            rect = QtCore.QRectF(self.pos_.x() - gr, self.pos_.y() - gr, 2 * gr, 2 * gr)
            p.setBrush(QtCore.Qt.NoBrush)
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 160), 9))
            p.drawEllipse(rect)
            pen = QtGui.QPen(theme.GAUGE, 7)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(rect, 90 * 16, int(-360 * 16 * self.gauge))
        # 5) 눈 인식 안 됨: 커서 오른쪽 위에 빨간 X (흰 동그라미 위에 그려서 어떤 배경에서도 보이게)
        if self.eye_lost:
            xc, yc = self.pos_.x() + r * 0.75, self.pos_.y() - r * 0.75
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
                k = age / CHECK_SEC
                pop = 0.6 + 0.6 * min(age / 0.12, 1.0) - 0.2 * min(max((age - 0.12) / 0.1, 0.0), 1.0)
                alpha = 1.0 if k < 0.6 else max(0.0, 1.0 - (k - 0.6) / 0.4)
                cx, cy = self.pos_.x(), self.pos_.y() - r - 22 - 6 * min(k * 2, 1.0)   # 살짝 위로 떠오름
                p.setOpacity(alpha)
                paint_badge(p, cx, cy, CHECK_R * pop, self.badge)
                p.setOpacity(1.0)