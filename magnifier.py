# -*- coding: utf-8 -*-
"""
magnifier.py — 메뉴 "확대/축소"용 원형 돋보기

배율이 ×2 이상이면 시선 주변 화면을 찍어서(grabWindow) 확대한 모습을 둥근 돋보기 창에 보여줍니다.
메뉴의 +/- 버튼을 누를 때마다 배율이 2배씩 바뀝니다 (×1 → ×2 → ×4 → ×8). ×1이면 돋보기를 숨깁니다.

돋보기 창은 시선 위치에서 대각선으로 떨어진 곳(오른쪽 위)에 뜹니다. 시선 바로 위에 띄우면
돋보기가 자기 자신을 다시 찍어서 화면이 끝없이 겹쳐 보이는 문제가 생기기 때문입니다.
화면 가장자리에 가까우면 반대쪽(왼쪽/아래)으로 옮겨 뜹니다.
"""
from PyQt5 import QtWidgets, QtCore, QtGui

import theme
from gaze_widgets import setup_floating_window

LENS_PX = 300          # 돋보기 지름
OFFSET_PX = 200        # 시선 위치에서 돋보기 중심까지의 가로/세로 거리
MAX_LEVEL = 8


class Magnifier(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        setup_floating_window(self, click_through=True)
        self.resize(LENS_PX, LENS_PX)
        self.level = 1
        self.center = QtCore.QPoint(0, 0)     # 확대할 지점 (화면 좌표)
        self.shot = QtGui.QPixmap()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._grab)
        self.timer.start(50)                  # 초당 20번 화면을 다시 찍음

    def set_level(self, level):
        self.level = level

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
        tag = QtCore.QRectF(c.x() - 34, rect.bottom() - 46, 68, 32)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(74, 52, 40, 210))
        p.drawRoundedRect(tag, 16, 16)
        p.setPen(QtGui.QColor(255, 255, 255))
        p.setFont(theme.ui_font(18))
        p.drawText(tag, QtCore.Qt.AlignCenter, f"×{self.level}")
