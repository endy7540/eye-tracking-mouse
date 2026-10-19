# -*- coding: utf-8 -*-
"""
number_check.py — "숫자 맞추기": 보정 직후에 하는 정확도 확인 + 추가 학습

화면에 흩어진 숫자 1~12를 차례로 바라보면 됩니다 (클릭·윙크 필요 없음).
    - 지금 보는 숫자에 시선 커서를 0.9초 두면 통과 → 다음 숫자
    - 숫자 위치는 화면 가장자리까지 고르게 퍼져 있고, 연속된 숫자는 일부러 멀리 떨어뜨림
    - 통과할 때마다 두 가지를 합니다
        1) 오차 기록: 그동안 시선 커서 위치(중앙값)와 숫자 중심의 거리(px)
        2) 정답 전달: "이 숫자를 보고 있었다" → on_sample(시각, x, y) → 자동 보정(adaptive.py) 응시 클릭 샘플로 사용
    - 끝나면 평균 오차(px)를 보여줌 (설계 목표: 평균 50px, 중간 목표 80px)
    - 너무 안 맞아서 못 통과하면 4초마다 인정 반경이 커지고, 12초가 지나면 그 숫자는 건너뜀(샘플로 쓰지 않음)

구성: 위쪽은 화면과 상관없는 규칙(NumberCheck, Qt 없이 테스트 가능), 아래쪽이 PyQt5 화면(NumberCheckWindow)입니다.
main.py가 해 주는 일: on_gaze(x, y, now)로 시선 좌표를 계속 넘겨주기 + on_sample / on_done 연결.
"""
import math
import random
import time

# ════════════════════════════════════════════════════════════════
#  1. 설정
# ════════════════════════════════════════════════════════════════
COUNT = 12                 # 숫자 개수
COLS = (0.10, 0.37, 0.63, 0.90)   # 숫자 자리 4열 × 3줄 = 12자리 (화면 비율, 가장자리까지)
ROWS = (0.17, 0.50, 0.83)
DWELL_SEC = 0.9            # 통과에 필요한 응시 시간 (adaptive.py의 샘플 간격 0.8초보다 길게)
LEAVE_GRACE = 0.2          # 이 시간 안에 반경으로 돌아오면 응시가 이어진 것으로 봄
RADIUS_PX = 110.0          # 처음 인정 반경 (숫자 중심에서 이만큼 안이면 바라보는 중)
RADIUS_GROW = 1.25         # 못 통과하면 4초마다 반경 × 1.25
RADIUS_STEP_SEC = 4.0
RADIUS_MAX_MUL = 2.0       # 반경 최대 = 처음의 2배
SKIP_SEC = 12.0            # 이 시간 안에 통과 못 하면 건너뜀
MIN_FAR = 0.28             # 연속된 숫자는 화면 대각선(비율)의 이만큼 이상 떨어지게 배치
GOAL_PX, MID_GOAL_PX = 50.0, 80.0   # 설계 목표 (보고서와 동일)


def median(vals):
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def grade_text(mean_err):
    if mean_err is None:
        return "측정된 숫자가 없어요"
    if mean_err <= GOAL_PX:
        return "목표 달성!"
    if mean_err <= MID_GOAL_PX:
        return "중간 목표 달성 — 쓸수록 더 좋아져요"
    return "아직 오차가 커요 — 한 번 더 하면 좋아져요"


# ════════════════════════════════════════════════════════════════
#  2. 규칙 (화면과 무관)
# ════════════════════════════════════════════════════════════════
class NumberCheck:
    """
    state: play → result.   사용법: chk.on_gaze(x, y, now) 를 시선이 올 때마다, chk.update(now) 를 주기적으로 부름.
    좌표는 전부 '화면 전체 좌표'(origin 은 모니터 왼쪽 위).
    """

    def __init__(self, x0, y0, w, h, on_sample=None, rng=None, count=COUNT):
        self.rng = rng or random.Random()
        self.x0, self.y0, self.w, self.h = x0, y0, w, h
        self.on_sample = on_sample or (lambda t, x, y: None)
        self.targets = self._layout(count)           # 번호 순서대로 (x, y)
        self.idx = 0
        self.state = "play"
        self.errs = []                               # 통과한 숫자의 오차(px)
        self.skipped = 0
        self.t_target0 = None
        self.t_result = None
        self._reset_dwell()

    # ── 배치: 12자리를 섞되, 연속된 숫자가 가까이 붙지 않게 ──
    def _layout(self, count):
        slots = [(self.x0 + cx * self.w, self.y0 + ry * self.h) for ry in ROWS for cx in COLS][:count]
        diag = math.hypot(self.w, self.h)
        best = None
        for _ in range(200):
            order = slots[:]
            self.rng.shuffle(order)
            gaps = [math.hypot(a[0] - b[0], a[1] - b[1]) / diag for a, b in zip(order, order[1:])]
            if min(gaps) >= MIN_FAR:
                return order
            if best is None or min(gaps) > best[0]:
                best = (min(gaps), order)
        return best[1]

    def _reset_dwell(self):
        self.dwell_since = None
        self.last_in = 0.0
        self.pts = []
        self.progress = 0.0

    @property
    def target(self):
        return self.targets[self.idx] if self.idx < len(self.targets) else None

    @property
    def mean_err(self):
        return sum(self.errs) / len(self.errs) if self.errs else None

    def radius(self, now):
        if self.t_target0 is None:
            return RADIUS_PX
        steps = int(max(0.0, now - self.t_target0) // RADIUS_STEP_SEC)
        return RADIUS_PX * min(RADIUS_MAX_MUL, RADIUS_GROW ** steps)

    # ── 시선 입력 ──
    def on_gaze(self, x, y, now):
        if self.state != "play":
            return
        if self.t_target0 is None:
            self.t_target0 = now
        tx, ty = self.target
        if math.hypot(x - tx, y - ty) <= self.radius(now):
            if self.dwell_since is None:
                self.dwell_since, self.pts = now, []
            self.last_in = now
            self.pts.append((x, y))
            self.progress = min((now - self.dwell_since) / DWELL_SEC, 1.0)
            if self.progress >= 1.0:
                self._pass(now)
        elif self.dwell_since is not None and now - self.last_in > LEAVE_GRACE:
            self._reset_dwell()

    def update(self, now):
        if self.state == "play":
            if self.t_target0 is None:
                self.t_target0 = now
            if now - self.t_target0 >= SKIP_SEC:
                self.skipped += 1
                self._next(now)
            elif self.dwell_since is not None and now - self.last_in > LEAVE_GRACE:
                self._reset_dwell()

    def _pass(self, now):
        tx, ty = self.target
        mx, my = median([p[0] for p in self.pts]), median([p[1] for p in self.pts])
        self.errs.append(math.hypot(mx - tx, my - ty))
        self.on_sample(now, tx, ty)
        self._next(now)

    def _next(self, now):
        self.idx += 1
        self.t_target0 = now
        self._reset_dwell()
        if self.idx >= len(self.targets):
            self.state, self.t_result = "result", now


# ════════════════════════════════════════════════════════════════
#  3. PyQt5 화면
# ════════════════════════════════════════════════════════════════
from PyQt5 import QtWidgets, QtCore, QtGui   # noqa: E402

RESULT_SEC = 6.0
BG_TOP, BG_BOTTOM = QtGui.QColor(20, 33, 61), QtGui.QColor(31, 49, 88)
WHITE = QtGui.QColor(255, 255, 255)
SOFT = QtGui.QColor(185, 196, 219)
BLUE = QtGui.QColor(127, 176, 255)
GREEN = QtGui.QColor(90, 200, 130)
ORANGE = QtGui.QColor(255, 178, 122)
FONT = "Malgun Gothic"


class NumberCheckWindow(QtWidgets.QWidget):
    """전체 화면 숫자 맞추기. on_sample(t, x, y): 숫자를 통과할 때, on_done(errs, skipped, cancelled): 끝났을 때."""

    def __init__(self, geo, on_sample, on_done):
        super().__init__()
        self.geo, self.on_done = geo, on_done
        self.chk = NumberCheck(geo.x(), geo.y(), geo.width(), geo.height(), on_sample)
        self._finished = False
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        self.setGeometry(geo)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(30)

    def on_gaze(self, x, y, now):
        self.chk.on_gaze(x, y, now)

    def _tick(self):
        now = time.time()
        self.chk.update(now)
        if self.chk.state == "result" and now - self.chk.t_result >= RESULT_SEC:
            self._finish(False)
        self.update()

    def keyPressEvent(self, event):
        key = event.key()
        if key == QtCore.Qt.Key_Escape:
            self._finish(self.chk.state != "result")
        elif key in (QtCore.Qt.Key_Space, QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) and self.chk.state == "result":
            self._finish(False)

    def _finish(self, cancelled):
        if self._finished:
            return
        self._finished = True
        self.timer.stop()
        self.close()
        self.on_done(list(self.chk.errs), self.chk.skipped, cancelled)

    # ── 그리기 ──
    def _font(self, px, bold=True):
        f = QtGui.QFont(FONT)
        f.setPixelSize(max(8, int(px)))
        f.setBold(bold)
        return f

    def _local(self, gx, gy):
        return gx - self.geo.x(), gy - self.geo.y()

    def paintEvent(self, event):
        now = time.time()
        c, w, h = self.chk, self.width(), self.height()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        grad = QtGui.QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0, BG_TOP)
        grad.setColorAt(1, BG_BOTTOM)
        p.fillRect(self.rect(), grad)

        if c.state == "play":
            self._draw_numbers(p, now)
            self._text(p, w / 2, h * 0.055, f"숫자를 {c.idx + 1}번부터 차례로 바라보세요", h * 0.034, WHITE)
            self._text(p, w / 2, h * 0.098, f"{min(c.idx + 1, len(c.targets))} / {len(c.targets)}   ·   ESC: 건너뛰기",
                       h * 0.022, SOFT, bold=False)
        else:
            self._draw_result(p)

    def _draw_numbers(self, p, now):
        c, base = self.chk, min(self.width(), self.height())
        r = base * 0.045
        for i, (gx, gy) in enumerate(c.targets):
            x, y = self._local(gx, gy)
            if i < c.idx:                                   # 지나간 숫자: 초록 체크 느낌으로 흐리게
                p.setPen(QtGui.QPen(QtGui.QColor(90, 200, 130, 140), 4))
                p.setBrush(QtGui.QColor(90, 200, 130, 40))
                p.drawEllipse(QtCore.QPointF(x, y), r * 0.8, r * 0.8)
                self._text(p, x, y, str(i + 1), r * 0.9, QtGui.QColor(90, 200, 130, 170))
            elif i == c.idx:                                # 지금 숫자: 크고 밝게 + 숨쉬듯 커졌다 작아짐
                pulse = 1.0 + 0.06 * math.sin(now * 5)
                rr = r * 1.35 * pulse
                p.setPen(QtGui.QPen(WHITE, 5))
                p.setBrush(BLUE)
                p.drawEllipse(QtCore.QPointF(x, y), rr, rr)
                self._text(p, x, y, str(i + 1), rr * 1.0, BG_TOP)
                if c.progress > 0:                          # 응시 진행 링
                    ring = QtCore.QRectF(x - rr - 14, y - rr - 14, 2 * (rr + 14), 2 * (rr + 14))
                    pen = QtGui.QPen(GREEN, 9)
                    pen.setCapStyle(QtCore.Qt.RoundCap)
                    p.setPen(pen)
                    p.setBrush(QtCore.Qt.NoBrush)
                    p.drawArc(ring, 90 * 16, int(-360 * 16 * c.progress))
            else:                                           # 앞으로 올 숫자: 작고 흐리게 (위치만 보이게)
                p.setPen(QtGui.QPen(QtGui.QColor(185, 196, 219, 110), 3))
                p.setBrush(QtCore.Qt.NoBrush)
                p.drawEllipse(QtCore.QPointF(x, y), r * 0.8, r * 0.8)
                self._text(p, x, y, str(i + 1), r * 0.8, QtGui.QColor(185, 196, 219, 130))

    def _draw_result(self, p):
        c, w, h = self.chk, self.width(), self.height()
        err = c.mean_err
        self._text(p, w / 2, h * 0.30, "숫자 맞추기 끝!", h * 0.07, WHITE)
        big = f"평균 오차 {err:.0f}px" if err is not None else "측정 결과 없음"
        good = err is not None and err <= MID_GOAL_PX
        self._text(p, w / 2, h * 0.45, big, h * 0.11, GREEN if good else ORANGE)
        self._text(p, w / 2, h * 0.58, grade_text(err), h * 0.04, WHITE)
        self._text(p, w / 2, h * 0.66, f"통과 {len(c.errs)}개 · 건너뜀 {c.skipped}개   (설계 목표: 평균 {GOAL_PX:.0f}px)",
                   h * 0.026, SOFT, bold=False)
        self._text(p, w / 2, h * 0.74, "통과한 숫자는 보정에 반영됐어요   ·   SPACE: 닫기", h * 0.022, SOFT, bold=False)

    def _text(self, p, cx, cy, text, px, color, bold=True):
        p.setFont(self._font(px, bold))
        p.setPen(color)
        p.drawText(QtCore.QRectF(cx - 2000, cy - px * 1.2, 4000, px * 2.4), QtCore.Qt.AlignCenter, text)
