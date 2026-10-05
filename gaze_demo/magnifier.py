# -*- coding: utf-8 -*-
"""
magnifier.py — 메뉴 "확대/축소"용 원형 돋보기

배율이 ×2 이상이면 시선 주변 화면을 찍어서(grabWindow) 확대한 모습을 둥근 돋보기 창에 보여줍니다.
메뉴의 +/- 버튼을 누를 때마다 배율이 2배씩 바뀝니다 (×1 → ×2 → ×4 → ×8). ×1이면 돋보기를 숨깁니다.

돋보기 창은 시선 위치에서 대각선으로 떨어진 곳(오른쪽 위)에 뜹니다. 시선 바로 위에 띄우면
돋보기가 자기 자신을 다시 찍어서 화면이 끝없이 겹쳐 보이는 문제가 생기기 때문입니다.
화면 가장자리에 가까우면 반대쪽(왼쪽/아래)으로 옮겨 뜹니다.

[돋보기를 켜 둔 동안] 물개 커서는 숨기고, 돋보기 가운데의 주황 십자가 커서 역할을 합니다.
물개 커서는 항상 확대 지점 한가운데에 있어서, 그대로 두면 돋보기 속에서 보려던 곳을 가려 버리기 때문입니다.
(예전엔 물개 커서를 '화면 캡처에서 제외'시켰는데, 그러면 윈도우 녹화 프로그램이 녹화를 거부해서 이 방식으로 바꿈)
그래서 물개 커서에 뜨던 응시 게이지와 클릭 체크(✓)도 돋보기 안 십자 주변에 대신 그립니다.
"""
import time

from PyQt5 import QtWidgets, QtCore, QtGui

import theme
from seal_cursor import paint_badge
from gaze_widgets import setup_floating_window

LENS_PX = 300          # 돋보기 지름
OFFSET_PX = 200        # 시선 위치에서 돋보기 중심까지의 가로/세로 거리
MAX_LEVEL = 8
CHECK_SEC = 0.7        # 클릭 체크 표시 시간 (물개 커서와 같음)

class Magnifier(QtWidgets.QWidget):
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
        p.setPen(QtGui.QPen(theme.INK, 4))
        p.drawEllipse(rect)

        # 가운데 십자 표시(지금 보고 있는 지점) + 배율 표시
        c = rect.center()
        p.setPen(QtGui.QPen(QtGui.QColor(242, 130, 40, 200), 2))
        p.drawLine(QtCore.QPointF(c.x() - 10, c.y()), QtCore.QPointF(c.x() + 10, c.y()))
        p.drawLine(QtCore.QPointF(c.x(), c.y() - 10), QtCore.QPointF(c.x(), c.y() + 10))
        if self.gauge > 0:                    # 응시 게이지: 십자 둘레에 차오르는 호
            gr = QtCore.QRectF(c.x() - 24, c.y() - 24, 48, 48)
            p.setBrush(QtCore.Qt.NoBrush)
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 170), 8))
            p.drawEllipse(gr)
            pen = QtGui.QPen(theme.GAUGE, 6)
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
        p.setBrush(QtGui.QColor(74, 52, 40, 210))
        p.drawRoundedRect(tag, 16, 16)
        p.setPen(QtGui.QColor(255, 255, 255))
        p.setFont(theme.ui_font(18))
        p.drawText(tag, QtCore.Qt.AlignCenter, f"×{self.level}")
