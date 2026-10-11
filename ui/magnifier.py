# -*- coding: utf-8 -*-
"""
magnifier.py — 메뉴 "확대/축소" 기능

ScreenZoom  (기본 — 화면 전체 확대)
    윈도우에 들어 있는 확대 기능(Magnification API, 윈도우 돋보기 프로그램이 쓰는 것과 같은 기능)을 불러서
    화면 전체를 키웁니다. 메뉴의 +/- 버튼을 누를 때마다 ZOOM_STEP(0.25배)씩 바뀝니다 (×1 → ×1.25 → ×1.5 … 최대 ×MAX_LEVEL).
    +/-를 누르면 메뉴창이 바로 닫히면서 확대가 보입니다 (main.py의 zoom_in/zoom_out).

    ★ 좌표 변환이 필요한 이유 ★
    화면이 확대되면 "눈이 보고 있는 화면 위치"와 "그 자리에 실제로 있는 프로그램의 위치"가 달라집니다.
    예) ×2 확대 중 화면 정가운데를 보고 있으면, 실제로는 확대된 영역(보이는 영역)의 가운데를 보고 있는 것.
    그래서 main.py는 시선 좌표를 to_desktop()으로 바꾼 뒤에 커서·버튼·클릭에 넘깁니다.
        화면 좌표(눈이 보는 곳)  →  to_desktop()  →  실제 좌표(커서를 그리고 클릭할 곳)

    ★ 화면 이동(팬) ★
    시선이 화면 가장자리(PAN_EDGE) 쪽에 머물면 그 방향으로 보이는 영역이 천천히 움직입니다.
    가장자리 끝에 가까울수록 빨리 움직이고, 가운데 쪽을 보면 멈춥니다 (눈 떨림으로 화면이 흔들리지 않게).
    오른쪽 아래 메뉴 아이콘 근처를 볼 때는 움직이지 않습니다 (아이콘을 누르려는 거라서).

    ★ 잠깐 원래 크기로 (suspended) ★
    메뉴창·화상 키보드·상태 확인 창·캘리브레이션이 떠 있을 때는 이 창들까지 같이 커져서 화면 밖으로 밀려나므로,
    그동안만 원래 크기(×1)로 돌렸다가 닫으면 다시 확대합니다. (배율 설정은 그대로 기억)

    주의: 윈도우 8 이상에서만 됩니다. 원격 데스크톱 등에서 확대 기능을 못 쓰면 available = False가 되고,
          main.py는 아래의 원형 돋보기(Magnifier)를 대신 씁니다.
          프로그램이 꺼질 때 확대를 원래대로 되돌립니다(shutdown).

Magnifier  (예비 — 원형 돋보기, 예전 방식)
    화면 전체 확대를 못 쓰는 컴퓨터에서만 씁니다.
    배율이 ×1보다 크면 시선 주변 화면을 찍어서(grabWindow) 확대한 모습을 둥근 돋보기 창에 보여줍니다.
    돋보기 창은 시선 위치에서 대각선으로 떨어진 곳(오른쪽 위)에 뜹니다. 시선 바로 위에 띄우면
    돋보기가 자기 자신을 다시 찍어서 화면이 끝없이 겹쳐 보이는 문제가 생기기 때문입니다.
    [돋보기를 켜 둔 동안] 커서는 숨기고, 돋보기 가운데의 십자가 커서 역할을 합니다.
    (예전엔 커서를 '화면 캡처에서 제외'시켰는데, 그러면 윈도우 녹화 프로그램이 녹화를 거부해서 이 방식으로 바꿈)
    그래서 커서에 뜨던 응시 게이지와 클릭 체크(✓)도 돋보기 안 십자 주변에 대신 그립니다.
"""
import atexit
import ctypes
import math
import sys
import time

from PyQt5 import QtWidgets, QtCore, QtGui

from . import theme
from .seal_cursor import paint_badge
from .gaze_widgets import setup_floating_window

MAX_LEVEL = 8.0        # 최대 배율
ZOOM_STEP = 0.25       # 메뉴의 +/- 한 번에 바뀌는 배율 (×1 → ×1.25 → ×1.5 → …)


def zoom_text(level):
    """배율을 화면에 보여줄 글자로. 예) 1.25 → ×1.25, 2.0 → ×2 (소수점 아래 0은 안 보임)"""
    return f"×{float(level):g}"

# ── 화면 전체 확대 (ScreenZoom) 설정 ─────────────────────────────────────
PAN_EDGE = 0.18        # 화면 가장자리에서 이 비율 안쪽을 보면 그 방향으로 화면이 움직임
PAN_SPEED = 900        # 가장자리 끝을 볼 때 1초에 움직이는 양 (눈에 보이는 화면 픽셀 기준)
DOCK_GUARD_PX = 260    # 메뉴 아이콘 중심에서 이 거리 안을 볼 때는 화면을 움직이지 않음

# ── 원형 돋보기 (Magnifier, 예비) 설정 ──────────────────────────────────
LENS_PX = 300          # 돋보기 지름
OFFSET_PX = 200        # 시선 위치에서 돋보기 중심까지의 가로/세로 거리
CHECK_SEC = 0.7        # 클릭 체크 표시 시간 (커서와 같음)


class ScreenZoom(QtCore.QObject):
    """윈도우 확대 API로 화면 전체를 확대. 좌표는 모두 Qt 화면 좌표(main.py가 쓰는 것과 같은 단위)."""

    def __init__(self):
        super().__init__()
        self.available = False       # 화면 전체 확대를 쓸 수 있는지 (못 쓰면 원형 돋보기로)
        self.level = 1               # 메뉴에서 정한 배율
        self.suspended = False       # 메뉴창·키보드 등이 떠 있어서 잠깐 원래 크기로 돌려놓은 상태
        self.ox = self.oy = 0.0      # 보이는 영역의 왼쪽 위 (화면 왼쪽 위 기준, Qt 좌표)
        self.guard = None            # 화면을 움직이지 않을 지점 (메뉴 아이콘 중심, 화면 좌표)
        self._last_t = None
        self._applied = None         # 마지막으로 윈도우에 보낸 값 (같은 값이면 다시 안 보냄)
        self._api = None
        self._warned = False

        screen = QtWidgets.QApplication.primaryScreen()
        self.geo = screen.geometry()
        self.ratio = 1.0             # Qt 좌표 → 실제 모니터 픽셀 (화면 배율 125%, 150% 대응)
        if sys.platform != "win32":
            return
        try:
            phys_w = ctypes.windll.user32.GetSystemMetrics(0)          # 주 모니터의 실제 가로 픽셀
            if phys_w > 0 and self.geo.width() > 0:
                self.ratio = phys_w / self.geo.width()
            api = ctypes.WinDLL("Magnification.dll")
            api.MagInitialize.restype = ctypes.c_bool
            api.MagUninitialize.restype = ctypes.c_bool
            api.MagSetFullscreenTransform.argtypes = (ctypes.c_float, ctypes.c_int, ctypes.c_int)
            api.MagSetFullscreenTransform.restype = ctypes.c_bool
            if api.MagInitialize():
                self._api = api
                self.available = True
                atexit.register(self.shutdown)    # 프로그램이 어떻게 꺼지든 확대를 원래대로
            else:
                print("[확대] 윈도우 확대 기능을 켤 수 없어서 원형 돋보기로 대신해요.")
        except Exception as e:
            print("[확대] 화면 전체 확대를 쓸 수 없어서 원형 돋보기로 대신해요:", e)

    # ── 상태 ─────────────────────────────────────────────────────
    @property
    def active(self):
        """지금 실제로 확대되어 있는지."""
        return self.available and self.level > 1 and not self.suspended

    def effective_level(self):
        return self.level if self.active else 1

    def set_guard(self, x, y):
        """메뉴 아이콘 중심(화면 좌표). 이 근처를 볼 때는 화면을 움직이지 않음."""
        self.guard = (x, y)

    def set_level(self, level, center=None):
        """배율 바꾸기. center(실제 좌표)가 있으면 그 지점이 가운데 오도록, 없으면 지금 보던 가운데 유지."""
        level = max(1.0, min(MAX_LEVEL, float(level)))      # 1.25배처럼 소수 배율도 그대로 씀
        if center is None:
            vw, vh = self._view_size()
            center = (self.geo.x() + self.ox + vw / 2, self.geo.y() + self.oy + vh / 2)
        self.level = level
        self._center_on(*center)
        self._apply()

    def set_suspended(self, suspended):
        self.suspended = suspended
        self._last_t = None
        self._apply()

    def view_rect(self):
        """지금 화면에 보이는 영역 (실제 좌표). 확대 중이 아니면 화면 전체."""
        if not self.active:
            return QtCore.QRectF(self.geo)
        vw, vh = self._view_size()
        return QtCore.QRectF(self.geo.x() + self.ox, self.geo.y() + self.oy, vw, vh)

    # ── 좌표 변환 ────────────────────────────────────────────────
    def to_desktop(self, sx, sy):
        """화면 좌표(눈이 보는 곳) → 실제 좌표(그 자리에 있는 프로그램 위치)."""
        if not self.active:
            return sx, sy
        L = self.level
        return (self.geo.x() + self.ox + (sx - self.geo.x()) / L,
                self.geo.y() + self.oy + (sy - self.geo.y()) / L)

    def to_screen(self, dx, dy):
        """실제 좌표 → 화면 좌표 (to_desktop의 반대). 마우스 테스트 모드에서 씀."""
        if not self.active:
            return dx, dy
        L = self.level
        return (self.geo.x() + (dx - self.geo.x() - self.ox) * L,
                self.geo.y() + (dy - self.geo.y() - self.oy) * L)

    # ── 화면 이동 (팬) ───────────────────────────────────────────
    def follow(self, sx, sy):
        """시선(화면 좌표)이 가장자리 쪽이면 그 방향으로 보이는 영역을 움직임. 매 프레임 호출."""
        now = time.time()
        dt = 0.0 if self._last_t is None else min(now - self._last_t, 0.1)
        self._last_t = now
        if not self.active or dt <= 0:
            return
        if self.guard is not None and math.hypot(sx - self.guard[0], sy - self.guard[1]) < DOCK_GUARD_PX:
            return
        W, H = self.geo.width(), self.geo.height()
        lx, ly = sx - self.geo.x(), sy - self.geo.y()
        vx = self._edge_push(lx, W)
        vy = self._edge_push(ly, H)
        if vx == 0 and vy == 0:
            return
        speed = PAN_SPEED / self.level              # 실제 좌표로는 배율만큼 느리게 움직여야 눈에 보이는 속도가 같음
        self.ox += vx * speed * dt
        self.oy += vy * speed * dt
        self._clamp()
        self._apply()

    @staticmethod
    def _edge_push(v, size):
        """가장자리 쪽으로 얼마나 들어갔는지 (-1 ~ 1). 가운데 쪽이면 0."""
        band = size * PAN_EDGE
        if v < band:
            return -min(1.0, (band - v) / band)
        if v > size - band:
            return min(1.0, (v - (size - band)) / band)
        return 0.0

    # ── 내부 계산 ────────────────────────────────────────────────
    def _view_size(self):
        return self.geo.width() / self.level, self.geo.height() / self.level

    def _center_on(self, dx, dy):
        vw, vh = self._view_size()
        self.ox = dx - self.geo.x() - vw / 2
        self.oy = dy - self.geo.y() - vh / 2
        self._clamp()

    def _clamp(self):
        vw, vh = self._view_size()
        self.ox = min(max(self.ox, 0.0), self.geo.width() - vw)
        self.oy = min(max(self.oy, 0.0), self.geo.height() - vh)

    def _apply(self):
        """윈도우에 지금 배율·위치를 알려줌 (실제 모니터 픽셀 단위로 바꿔서)."""
        if self._api is None:
            return
        L = self.effective_level()
        if L > 1:
            x = int(round((self.geo.x() + self.ox) * self.ratio))
            y = int(round((self.geo.y() + self.oy) * self.ratio))
        else:
            x = y = 0
        key = (L, x, y)
        if key == self._applied:
            return
        if self._api.MagSetFullscreenTransform(float(L), x, y):
            self._applied = key
        elif not self._warned:
            self._warned = True
            print("[확대] 윈도우가 화면 확대를 거부했어요. 윈도우 '돋보기' 프로그램이 켜져 있다면 끄고 다시 해 보세요.")

    def shutdown(self):
        """확대를 원래대로 되돌리고 확대 기능을 정리 (프로그램 종료 시)."""
        if self._api is None:
            return
        try:
            self._api.MagSetFullscreenTransform(1.0, 0, 0)
            self._api.MagUninitialize()
        except Exception:
            pass
        self._api = None
        self.available = False


class Magnifier(QtWidgets.QWidget):
    """[예비] 원형 돋보기 — 화면 전체 확대(ScreenZoom)를 못 쓰는 컴퓨터에서만 씀."""

    def __init__(self):
        super().__init__()
        setup_floating_window(self, click_through=True)
        self.resize(LENS_PX, LENS_PX)
        self.level = 1
        self.center = QtCore.QPoint(0, 0)     # 확대할 지점 (화면 좌표)
        self.shot = QtGui.QPixmap()
        self.gauge = 0.0                      # 응시 게이지 (0~1)
        self.check_t = None                   # 표시(체크/뒤로가기) 시작 시각
        self.badge = "check"
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._grab)
        self.timer.start(50)                  # 초당 20번 화면을 다시 찍음

    def set_level(self, level):
        self.level = level

    def set_gauge(self, frac):
        self.gauge = frac
        self.update()

    def show_check(self):
        self.show_badge("check")

    def show_badge(self, kind):
        self.badge = kind
        self.check_t = time.time()
        self.update()

    def follow(self, gx, gy):
        """시선 위치를 따라 돋보기 위치를 옮김."""
        self.center = QtCore.QPoint(int(gx), int(gy))
        screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
        dx = OFFSET_PX if gx + OFFSET_PX + LENS_PX / 2 < screen.right() else -OFFSET_PX
        dy = -OFFSET_PX if gy - OFFSET_PX - LENS_PX / 2 > screen.top() else OFFSET_PX
        self.move(int(gx + dx - LENS_PX / 2), int(gy + dy - LENS_PX / 2))

    def _grab(self):
        if not self.isVisible() or self.level <= 1:
            return
        screen = QtWidgets.QApplication.primaryScreen()
        geo = screen.geometry()
        full = screen.grabWindow(0)
        # 화면 배율(125%, 150% 등)이 켜져 있으면 찍힌 이미지 크기가 논리 좌표와 달라서 비율을 맞춰줌
        scale = full.width() / max(1, geo.width())
        src = LENS_PX / self.level
        x = (self.center.x() - geo.x() - src / 2) * scale
        y = (self.center.y() - geo.y() - src / 2) * scale
        self.shot = full.copy(QtCore.QRect(int(x), int(y), int(src * scale), int(src * scale)))
        self.update()

    def paintEvent(self, event):
        th = theme.current()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        rect = QtCore.QRectF(6, 6, LENS_PX - 12, LENS_PX - 12)

        path = QtGui.QPainterPath()
        path.addEllipse(rect)
        p.setClipPath(path)
        p.fillRect(rect, QtGui.QColor(255, 255, 255))
        if not self.shot.isNull():
            p.drawPixmap(rect, self.shot, QtCore.QRectF(self.shot.rect()))
        p.setClipping(False)

        p.setBrush(QtCore.Qt.NoBrush)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 220), 10))
        p.drawEllipse(rect)
        p.setPen(QtGui.QPen(th["deep"], 4))
        p.drawEllipse(rect)

        # 가운데 십자 표시(지금 보고 있는 지점) + 배율 표시
        c = rect.center()
        p.setPen(QtGui.QPen(theme.with_alpha(th["main"], 0.85), 2))
        p.drawLine(QtCore.QPointF(c.x() - 10, c.y()), QtCore.QPointF(c.x() + 10, c.y()))
        p.drawLine(QtCore.QPointF(c.x(), c.y() - 10), QtCore.QPointF(c.x(), c.y() + 10))
        if self.gauge > 0:                    # 응시 게이지: 십자 둘레에 차오르는 호
            gr = QtCore.QRectF(c.x() - 24, c.y() - 24, 48, 48)
            p.setBrush(QtCore.Qt.NoBrush)
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 170), 8))
            p.drawEllipse(gr)
            pen = QtGui.QPen(th["main"], 6)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(gr, 90 * 16, int(-360 * 16 * self.gauge))
        if self.check_t is not None:          # 클릭 체크(✓) / 뒤로가기(←): 십자 위쪽
            age = time.time() - self.check_t
            if age > CHECK_SEC:
                self.check_t = None
            else:
                k = age / CHECK_SEC
                p.setOpacity(1.0 if k < 0.6 else max(0.0, 1.0 - (k - 0.6) / 0.4))
                paint_badge(p, c.x(), c.y() - 46, 15, self.badge)
                p.setOpacity(1.0)

        tag = QtCore.QRectF(c.x() - 34, rect.bottom() - 46, 68, 32)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(theme.with_alpha(th["deep"], 0.82))
        p.drawRoundedRect(tag, 16, 16)
        p.setPen(QtGui.QColor(255, 255, 255))
        p.setFont(theme.ui_font(18))
        p.drawText(tag, QtCore.Qt.AlignCenter, zoom_text(self.level))
