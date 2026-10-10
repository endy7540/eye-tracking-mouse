# -*- coding: utf-8 -*-
"""
clicker.py — 시선으로 웹사이트·다른 프로그램까지 좌클릭

WinkDetector (기본 켜짐)
    한쪽 눈만 짧게(0.15~1초) 감았다 뜨면 클릭. 어느 눈으로 할지(양쪽/왼눈/오른눈)는 메뉴에서 고름. 양쪽 눈을 같이 감는 보통 눈 깜빡임은 무시합니다.
    눈을 감는 동안에는 GazeSession이 커서를 그 자리에 고정해 두므로(두 눈이 다 떠 있을 때만 갱신),
    윙크하기 직전에 보고 있던 위치가 클릭됩니다.

DwellClicker (기본 꺼짐, 메뉴에서 켜기)
    커서를 한곳(반경 60px 안)에 1.2초 머무르게 하면 그 자리를 클릭. 물개 커서 둘레에 게이지가 찹니다.
    한 번 누른 뒤에는 시선을 다른 곳으로 옮겼다 와야 다시 누를 수 있어서, 계속 같은 곳을 클릭하지 않습니다.
    글을 읽느라 한곳을 보고 있어도 클릭될 수 있으니 필요할 때만 켜서 쓰는 걸 권장합니다.

BlinkGesture
    두 눈을 같이 빠르게 연속으로 깜빡이는 횟수로 명령을 구분합니다.
        - 2초 안에 3번  → "back"  (뒤로가기 키)
        - 3.5초 안에 5번 → "pause" (일시정지/다시 시작)
    3번은 5번을 하는 도중에도 거치게 되므로, 3번째 깜빡임 후 0.8초 동안 더 깜빡이지 않을 때 "3번"으로 확정합니다.
    (그래서 뒤로가기는 마지막 깜빡임 뒤 약 0.8초 있다가 실행됨. 5번은 다섯 번째 깜빡임 즉시 실행)
    평소 자연스러운 깜빡임은 보통 3~4초에 한 번이라, 이렇게 빠른 연속 깜빡임은 일부러 하지 않으면 거의 안 나옴.

click_at(x, y)
    실제 윈도우 마우스를 (x, y)로 옮기고 왼쪽 버튼을 눌렀다 뗍니다 (진짜 마우스 클릭과 똑같이 동작).
"""
import math
import sys
from collections import deque

from PyQt5 import QtCore, QtGui

# ── 윙크 판정 기준 (평소 눈 뜬 정도 대비 비율) ─────────────────────────
WINK_CLOSE = 0.50       # 이보다 작으면 "감은 눈"
WINK_OPEN = 0.65        # 이보다 크면 "뜬 눈" (윙크 중 반대쪽 눈은 계속 이 이상이어야 함)
                        # [수정] 0.80 → 0.65: 윙크하면 반대쪽 눈도 같이 살짝 가늘어져서, 예전 기준으론 윙크가 잘 안 잡혔음
WINK_EYES = {"both": (0, 1), "left": (0,), "right": (1,)}   # 윙크 클릭에 쓸 눈 (0 = 왼눈, 1 = 오른눈)
WINK_MIN_SEC = 0.15     # 이보다 짧은 감음은 무시 (눈 깜빡임·떨림)
WINK_MAX_SEC = 1.0      # 이보다 길게 감고 있으면 취소 (그냥 한쪽 눈을 찡그린 것)
CLICK_COOLDOWN = 0.6    # 클릭 후 이 시간 동안은 다시 클릭하지 않음

# ── 연속 깜빡임 기준 ─────────────────────────────────────────────
BACK_COUNT = 3          # 뒤로가기: 이만큼 연속으로 깜빡이면
BACK_WINDOW_SEC = 2.0   # ... 이 시간 안에 (첫 번째 ~ 마지막 깜빡임)
BLINK_COUNT = 5         # 일시정지/다시 시작: 이만큼 연속으로 깜빡이면
BLINK_WINDOW_SEC = 3.5  # ... 이 시간 안에
SEQ_END_SEC = 0.8       # 마지막 깜빡임 뒤 이만큼 더 안 깜빡이면 "한 묶음 끝"으로 보고 횟수 판정
BLINK_MIN_SEC = 0.04    # 한 번의 깜빡임으로 인정할 감은 시간 (너무 짧은 건 인식 오류)
BLINK_MAX_SEC = 0.8     # 이보다 오래 감으면 깜빡임이 아니라 눈 감고 쉬는 것 → 세던 것 초기화
GESTURE_COOLDOWN = 1.5  # 전환 직후 이 시간 동안은 다시 세지 않음

# ── 응시 클릭 기준 ─────────────────────────────────────────────
DWELL_SEC = 1.2         # 한곳에 이만큼 머물면 클릭
DWELL_RADIUS = 60       # "한곳"으로 보는 반경 (px)
REARM_RADIUS = 120      # 클릭 후 이만큼 시선을 옮겨야 다시 클릭 가능


class WinkDetector:
    def __init__(self):
        self.state = "idle"          # idle → winking → (클릭) → idle / 취소 시 wait_open
        self.eye = None              # 0 = 왼눈, 1 = 오른눈
        self.t0 = 0.0
        self.last_click = -10.0
        self.last_ratio = None       # 상태 확인 창 표시용: 마지막 [왼눈, 오른눈] 개폐 비율

    def reset(self):
        self.state, self.eye = "idle", None

    def update(self, opens, base, t, eyes=(0, 1)):
        """매 프레임 호출. 윙크가 끝나는 순간(감았던 눈을 뜰 때) True. eyes: 윙크로 인정할 눈."""
        if opens is None or base is None:
            self.reset()
            self.last_ratio = None
            return False
        r = opens / base
        self.last_ratio = r
        closed, opened = r < WINK_CLOSE, r > WINK_OPEN

        if self.state == "wait_open":                       # 취소된 뒤: 두 눈이 다 떠질 때까지 대기
            if opened.all():
                self.reset()
            return False

        if self.state == "idle":
            for eye in eyes:
                if closed[eye] and opened[1 - eye]:         # 한쪽만 감음 → 윙크 시작
                    self.state, self.eye, self.t0 = "winking", eye, t
            return False

        # winking
        other = 1 - self.eye
        if closed[other]:                                   # 반대쪽 눈도 감김 = 보통 눈 깜빡임 → 취소
            self.state = "wait_open"
            return False
        if t - self.t0 > WINK_MAX_SEC:                      # 너무 오래 감음 → 취소
            self.state = "wait_open"
            return False
        if opened[self.eye] and opened[other]:              # 감았던 눈을 다시 뜸 → 윙크 완료
            dur = t - self.t0
            self.reset()
            if dur >= WINK_MIN_SEC and t - self.last_click >= CLICK_COOLDOWN:
                self.last_click = t
                return True
        return False


class BlinkGesture:
    def __init__(self):
        self.closed_since = None
        self.seq = []                # 지금 묶음의 깜빡임 시각들
        self.cooldown_until = 0.0

    def progress(self, t):
        """상태 확인 창 표시용: 지금 묶음에서 몇 번째까지 셌는지."""
        return len(self.seq)

    def _judge(self):
        n = len(self.seq)
        if n == BACK_COUNT and self.seq[-1] - self.seq[0] <= BACK_WINDOW_SEC:
            return "back"
        return None

    def update(self, opens, base, t):
        """매 프레임 호출. 명령이 확정되는 순간 "back" 또는 "pause", 아니면 None."""
        result = None
        if self.seq and self.closed_since is None and t - self.seq[-1] > SEQ_END_SEC:
            result = self._judge()               # 한 묶음이 끝남 → 몇 번이었는지 판정
            self.seq = []
            if result:
                self.cooldown_until = t + 0.5
        if opens is None or base is None:      # 얼굴을 놓치면 감은 상태로 보지 않음 (고개 돌림 등)
            self.closed_since = None
            return result
        r = opens / base
        both_closed = (r < WINK_CLOSE).all()
        both_open = (r > WINK_OPEN).all()
        if both_closed:
            if self.closed_since is None:
                self.closed_since = t
            elif t - self.closed_since > BLINK_MAX_SEC:   # 오래 감고 있음 → 처음부터
                self.seq = []
            return result
        if both_open and self.closed_since is not None:  # 감았다 뜸 = 깜빡임 1번
            dur = t - self.closed_since
            self.closed_since = None
            if t < self.cooldown_until or not (BLINK_MIN_SEC <= dur <= BLINK_MAX_SEC):
                return result
            self.seq.append(t)
            if len(self.seq) >= BLINK_COUNT and t - self.seq[0] <= BLINK_WINDOW_SEC:
                self.seq = []                    # 5번은 기다릴 필요 없이 바로 확정
                self.cooldown_until = t + GESTURE_COOLDOWN
                return "pause"
        return result


class DwellClicker:
    def __init__(self):
        self.reset()

    def reset(self):
        self.sum = None              # 머무는 동안의 좌표 합 (평균 위치 = 클릭 위치)
        self.n = 0
        self.t0 = 0.0
        self.armed = True
        self.clicked_at = None

    def update(self, x, y, t):
        """반환: (게이지 0~1, 클릭할 위치 또는 None)."""
        if not self.armed:                                  # 클릭 후 시선을 충분히 옮겨야 다시 준비
            cx, cy = self.clicked_at
            if math.hypot(x - cx, y - cy) > REARM_RADIUS:
                self.armed, self.sum = True, None
            return 0.0, None
        if self.sum is not None:
            mx, my = self.sum[0] / self.n, self.sum[1] / self.n
            if math.hypot(x - mx, y - my) > DWELL_RADIUS:   # 다른 곳으로 이동 → 처음부터
                self.sum = None
        if self.sum is None:
            self.sum, self.n, self.t0 = [x, y], 1, t
            return 0.0, None
        self.sum[0] += x
        self.sum[1] += y
        self.n += 1
        frac = (t - self.t0) / DWELL_SEC
        if frac >= 1.0:
            pt = (self.sum[0] / self.n, self.sum[1] / self.n)
            self.armed, self.clicked_at, self.sum = False, pt, None
            return 0.0, pt
        return frac, None


def click_at(x, y):
    """실제 마우스를 (x, y)로 옮기고 좌클릭. x, y는 Qt 화면 좌표 (화면 배율은 Qt가 알아서 변환)."""
    QtGui.QCursor.setPos(QtCore.QPoint(int(x), int(y)))
    if sys.platform != "win32":
        return
    import ctypes
    from control.text_sender import INPUT, _INPUTUNION, MOUSEINPUT, _user32
    LEFTDOWN, LEFTUP = 0x0002, 0x0004
    events = [INPUT(type=0, u=_INPUTUNION(mi=MOUSEINPUT(0, 0, 0, flag, 0, 0))) for flag in (LEFTDOWN, LEFTUP)]
    arr = (INPUT * 2)(*events)
    _user32.SendInput(2, arr, ctypes.sizeof(INPUT))
