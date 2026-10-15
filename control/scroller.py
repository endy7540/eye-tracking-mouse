# -*- coding: utf-8 -*-
"""
scroller.py — 시선으로 웹 페이지를 위·아래로 스크롤 (스크롤 모드)

메뉴 오른쪽 아래의 [↕ 스크롤] 토글(ui/menu_bar.py의 ScrollToggle)로 켜고 끕니다.
켜져 있는 동안 화면 위·아래 가장자리 띠를 바라보면 스크롤됩니다.

    아래로 스크롤: 작업 영역 세로 85% ~ 100% (아래쪽 띠)
    위로 스크롤  : 작업 영역 세로  0% ~  15% (위쪽 띠)
    가로 범위    : 화면 가로 10% ~ 90% (모서리는 시선 오차가 커서 뺌)
    (작업 영역 = 작업표시줄을 뺀 화면 = QScreen.availableGeometry())

동작
    1) 띠 안에 START_DWELL_SEC(0.6초) 머무르면 스크롤 시작 (그동안 커서 둘레 게이지가 참)
    2) 띠 안으로 깊이 들어갈수록(화면 끝에 가까울수록) 빨라짐: SPEED_MIN ~ SPEED_MAX (휠 칸/초)
    3) 띠를 벗어나면 바로 멈춤. 경계에서 떨려도 끊기지 않게, 이미 스크롤 중이면 띠가 5% 더 넓게 적용됨
    4) 메뉴 독(토글·아이콘)·상태 확인 창 주변은 스크롤 띠에서 제외 (시선 오차를 감안해 EXCLUDE_MARGIN_PX만큼 더 넓게)
    5) AUTO_OFF_SEC(120초) 동안 스크롤을 한 번도 안 하면 스크롤 모드가 자동으로 꺼짐 (켜 놓고 잊는 경우)

안전
    - 휠 신호는 시선 좌표가 들어올 때(update)만 보냅니다. 카메라가 끊기거나 눈을 놓쳐서 좌표가 안 들어오면
      스크롤도 같이 멈춥니다 (STALE_SEC 이상 끊기면 처음부터 다시 머무름 시간을 잼).
    - 일시정지·캘리브레이션·키보드/메뉴창 열림·화면 확대 중에는 main.py가 blocked=True로 넘겨서 멈춥니다.
    - 시선이 GazeButton(메뉴·키보드 버튼) 위에 있을 때도 blocked로 멈춥니다.

휠은 "마우스 포인터 아래의 창"으로 갑니다. 시선 커서는 오버레이라서 실제 마우스 포인터는 따로 있으므로,
스크롤을 시작할 때 포인터가 페이지 본문 영역(가로 15~85%, 세로 30~70%) 밖에 있으면
본문 가운데(가로는 시선 위치)로 옮깁니다. 이미 본문 안이면 그대로 둡니다 (retarget_pointer=True일 때).

구조
    ScrollLogic : Qt와 무관한 순수 파이썬. 어디를 보는지·언제 시작하는지·얼마나 빨리 가는지만 계산 (화면 없이 테스트 가능)
    Scroller    : ScrollLogic + 화면 영역 읽기 + 포인터 이동 + 휠 전송 + 시그널 (main.py가 쓰는 쪽)

main.py 연결: control/scroller.py 아래쪽의 [main.py 연결 방법] 주석 참고.
"""
import ctypes
import sys
from collections import namedtuple

from PyQt5 import QtCore, QtGui, QtWidgets

# ── 스크롤 영역 ─────────────────────────────────────────────────────
ZONE_RATIO = 0.15            # 위·아래 띠 두께 (작업 영역 세로의 15%)
ZONE_X_MIN, ZONE_X_MAX = 0.10, 0.90   # 띠의 가로 범위 (작업 영역 가로의 10% ~ 90%)
HYSTERESIS_RATIO = 0.05      # 이미 스크롤 중이면 띠가 이만큼(세로·가로 각 5%) 더 넓게 적용 (경계 떨림 방지)
EXCLUDE_MARGIN_PX = 80       # 메뉴 독 등 제외할 창 둘레 여유 (시선 오차 감안)

# ── 시간·속도 ───────────────────────────────────────────────────────
START_DWELL_SEC = 0.6        # 띠 안에 이만큼 머무르면 스크롤 시작
SPEED_MIN = 3.0              # 띠 입구에서의 속도 (휠 칸/초, 한 칸 ≈ 페이지 100px)
SPEED_MAX = 12.0             # 화면 맨 끝에서의 속도 (휠 칸/초)
WHEEL_DELTA = 120            # 윈도우 휠 한 칸의 단위
MIN_SEND_DELTA = 20          # 이 값 이상 모였을 때 한꺼번에 보냄 (너무 잘게 쪼갠 신호 방지)
STALE_SEC = 0.3              # 시선 좌표가 이만큼 끊기면 새로 시작으로 봄
MAX_DT = 0.1                 # 프레임 간격이 아무리 길어도 속도 계산에는 이만큼까지만 반영 (한꺼번에 튀는 것 방지)
AUTO_OFF_SEC = 120.0         # 스크롤을 안 하고 이만큼 지나면 모드 자동 꺼짐 (0이면 자동 끄기 안 함)

# ── 휠을 받을 본문 영역 (이 안에 포인터가 있으면 옮기지 않음) ────────────────
CONTENT_X_MIN, CONTENT_X_MAX = 0.15, 0.85
CONTENT_Y_MIN, CONTENT_Y_MAX = 0.30, 0.70

MOUSEEVENTF_WHEEL = 0x0800

ScrollStep = namedtuple("ScrollStep", "direction progress scrolling delta begin auto_off")
# direction: 0=띠 밖, +1=아래 띠, -1=위 띠 / progress: 시작 전 머무름 게이지 0~1 / scrolling: 지금 스크롤 중
# delta: 이번 프레임에 보낼 휠 양 (양수=위로, 음수=아래로, 0=보낼 것 없음) / begin: 스크롤이 막 시작된 프레임
# auto_off: 모드를 꺼야 함


class ScrollLogic:
    """어디를 보고 있는지 → 스크롤할지, 얼마나 빨리 할지. Qt·화면과 무관한 순수 계산."""

    def __init__(self):
        self.reset(0.0)

    def reset(self, now=0.0):
        """모드를 새로 켤 때: 모든 상태 초기화 + '안 쓴 시간' 재기 시작."""
        self._clear_zone()
        self.last_t = None
        self.idle_since = now

    def _clear_zone(self):
        self.direction = 0       # 지금 머무르거나 스크롤 중인 띠 (0 = 없음)
        self.enter_t = None
        self.scrolling = False
        self.acc = 0.0           # 아직 못 보낸 휠 양

    def _idle(self, direction=0, auto_off=False):
        return ScrollStep(direction, 0.0, False, 0, False, auto_off)

    def update(self, pos, now, area, excludes=(), blocked=False):
        """
        pos: (x, y) 시선 좌표 또는 None(시선 없음) / now: 시각(초)
        area: 작업 영역 (left, top, width, height) / excludes: 제외할 사각형들 (left, top, width, height)
        blocked: True면 이번엔 스크롤하지 않음 (일시정지 등)
        """
        if blocked or pos is None:
            self.idle_since = now            # 막혀 있는 동안은 '안 쓴 시간'으로 세지 않음
            self.last_t = None
            self._clear_zone()
            return self._idle()

        if self.last_t is not None and now - self.last_t > STALE_SEC:
            self._clear_zone()               # 좌표가 한동안 끊겼다 → 머무름 시간을 처음부터
        dt = 0.0 if self.last_t is None else min(max(now - self.last_t, 0.0), MAX_DT)
        self.last_t = now

        d = self._classify(pos[0], pos[1], area, excludes)
        if d == 0:
            self._clear_zone()
            off = bool(AUTO_OFF_SEC) and now - self.idle_since >= AUTO_OFF_SEC
            return self._idle(auto_off=off)

        self.idle_since = now                # 띠 안에 있는 동안은 '쓰는 중'
        if d != self.direction:              # 새 띠에 들어옴 (또는 위↔아래 이동) → 머무름 처음부터
            self._clear_zone()
            self.direction = d
            self.enter_t = now

        begin = False
        if not self.scrolling:
            frac = (now - self.enter_t) / START_DWELL_SEC
            if frac < 1.0:
                return ScrollStep(d, max(0.0, frac), False, 0, False, False)
            self.scrolling, self.acc, begin = True, 0.0, True

        notches = SPEED_MIN + (SPEED_MAX - SPEED_MIN) * self._depth(pos[1], d, area)
        self.acc += -d * notches * WHEEL_DELTA * dt      # 아래(+1) = 휠 음수, 위(-1) = 휠 양수
        delta = 0
        if abs(self.acc) >= MIN_SEND_DELTA:
            delta = int(self.acc)
            self.acc -= delta
        return ScrollStep(d, 0.0, True, delta, begin, False)

    def _classify(self, x, y, area, excludes):
        """(x, y)가 어느 띠인지: +1 아래, -1 위, 0 없음 (제외 영역·가로 범위 밖 포함)."""
        left, top, width, height = area
        down = y >= top + height - (ZONE_RATIO + (HYSTERESIS_RATIO if self.direction == 1 else 0.0)) * height
        up = y <= top + (ZONE_RATIO + (HYSTERESIS_RATIO if self.direction == -1 else 0.0)) * height
        d = 1 if down else (-1 if up else 0)
        if d == 0:
            return 0
        pad = HYSTERESIS_RATIO if self.direction == d else 0.0
        if not (left + (ZONE_X_MIN - pad) * width <= x <= left + (ZONE_X_MAX + pad) * width):
            return 0
        m = EXCLUDE_MARGIN_PX
        for (el, et, ew, eh) in excludes:
            if el - m <= x <= el + ew + m and et - m <= y <= et + eh + m:
                return 0
        return d

    @staticmethod
    def _depth(y, d, area):
        """띠 입구(0) ~ 화면 맨 끝(1). 깊이에 따라 속도가 SPEED_MIN ~ SPEED_MAX로 바뀜."""
        left, top, width, height = area
        if d == 1:
            entry, edge = top + height - ZONE_RATIO * height, top + height
            depth = (y - entry) / (edge - entry)
        else:
            entry, edge = top + ZONE_RATIO * height, top
            depth = (entry - y) / (entry - edge)
        return max(0.0, min(1.0, depth))


# ── 화면·마우스 (테스트에서 바꿔 끼울 수 있게 함수로 분리) ───────────────────
def _screen_area():
    g = QtWidgets.QApplication.primaryScreen().availableGeometry()
    return (g.left(), g.top(), g.width(), g.height())


def _cursor_pos():
    p = QtGui.QCursor.pos()
    return (p.x(), p.y())


def _set_cursor_pos(x, y):
    QtGui.QCursor.setPos(QtCore.QPoint(int(x), int(y)))


def send_wheel(delta):
    """휠 신호 보내기. delta: 양수=위로, 음수=아래로 (120 = 한 칸). 지금 마우스 포인터 아래의 창이 받음."""
    if sys.platform != "win32" or delta == 0:
        return False
    from control.text_sender import INPUT, _INPUTUNION, MOUSEINPUT, _user32   # clicker.click_at과 같은 방식
    event = INPUT(type=0, u=_INPUTUNION(mi=MOUSEINPUT(0, 0, int(delta) & 0xFFFFFFFF, MOUSEEVENTF_WHEEL, 0, 0)))
    arr = (INPUT * 1)(event)
    return _user32.SendInput(1, arr, ctypes.sizeof(INPUT)) == 1


class Scroller(QtCore.QObject):
    enabled_changed = QtCore.pyqtSignal(bool)     # 스크롤 모드 켜짐/꺼짐 (토글 표시를 맞추는 데 씀)
    progress_changed = QtCore.pyqtSignal(float)   # 시작 전 머무름 게이지 0~1 (커서 둘레 게이지)
    direction_changed = QtCore.pyqtSignal(int)    # 지금 스크롤 중인 방향: -1 위 / +1 아래 / 0 멈춤 (UI 표시용)
    pointer_moved = QtCore.pyqtSignal()           # 실제 마우스 포인터를 본문으로 옮겼음 (자동 보정이 헷갈리지 않게 알림)
    auto_off = QtCore.pyqtSignal()                # 오래 안 써서 모드를 스스로 껐음 (main.py가 self.scroll_on을 False로 맞추는 데 씀)

    def __init__(self, parent=None, retarget_pointer=True, exclude_rects=None):
        """
        retarget_pointer: 스크롤 시작 때 포인터를 본문으로 옮길지. 마우스로 시선을 흉내 내는 테스트 모드(--mouse)에서는
                          포인터가 곧 시선이라 False로 해야 함.
        exclude_rects: 호출하면 제외할 창들의 화면 사각형(QRect) 목록을 돌려주는 함수 (예: 메뉴 독, 상태 확인 창)
        """
        super().__init__(parent)
        self._logic = ScrollLogic()
        self._enabled = False
        self._retarget = retarget_pointer
        self._exclude_rects = exclude_rects
        self._progress = 0.0
        self._scroll_dir = 0

    # ── 상태 ──────────────────────────────────────────────────────
    @property
    def enabled(self):
        return self._enabled

    @property
    def engaged(self):
        """지금 띠 안에 있는지(머무르는 중 포함). 응시 클릭 등 다른 기능이 겹치지 않게 확인용."""
        return self._enabled and self._logic.direction != 0

    def set_enabled(self, on, now=None):
        on = bool(on)
        if on == self._enabled:
            return
        self._enabled = on
        self._logic.reset(now if now is not None else _now())
        self._publish(0, 0.0, False)
        self.enabled_changed.emit(on)

    def toggle(self):
        self.set_enabled(not self._enabled)

    def stop(self):
        """지금 진행 중인 스크롤·머무름만 멈춤 (모드는 그대로)."""
        self._logic._clear_zone()
        self._logic.last_t = None
        self._publish(0, 0.0, False)

    # ── main.py가 매 시선 프레임마다 호출 ─────────────────────────────
    def update(self, x, y, now, blocked=False):
        if not self._enabled:
            return
        pos = None if x is None or y is None else (x, y)
        excludes = []
        if self._exclude_rects is not None:
            excludes = [(r.left(), r.top(), r.width(), r.height()) for r in self._exclude_rects()]
        area = _screen_area()
        step = self._logic.update(pos, now, area, excludes, blocked)

        if step.auto_off:
            self.set_enabled(False)
            self.auto_off.emit()
            return
        self._publish(step.direction, step.progress, step.scrolling)
        if step.begin and self._retarget and pos is not None:
            self._move_pointer_to_content(pos[0], area)
        if step.delta:
            send_wheel(step.delta)

    # ── 내부 ──────────────────────────────────────────────────────
    def _publish(self, direction, progress, scrolling):
        if progress != self._progress:
            self._progress = progress
            self.progress_changed.emit(progress)
        scroll_dir = direction if scrolling else 0
        if scroll_dir != self._scroll_dir:
            self._scroll_dir = scroll_dir
            self.direction_changed.emit(scroll_dir)

    def _move_pointer_to_content(self, gaze_x, area):
        """실제 마우스 포인터가 본문 영역 밖이면 본문 가운데로 옮김 (휠이 본문으로 가도록)."""
        left, top, width, height = area
        x0, x1 = left + CONTENT_X_MIN * width, left + CONTENT_X_MAX * width
        y0, y1 = top + CONTENT_Y_MIN * height, top + CONTENT_Y_MAX * height
        cx, cy = _cursor_pos()
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            return
        _set_cursor_pos(min(max(gaze_x, x0), x1), top + height / 2)
        self.pointer_moved.emit()


def _now():
    import time
    return time.time()

