# -*- coding: utf-8 -*-
"""
status_window.py — 메뉴 "상태 확인"으로 여는 창 (화면 왼쪽 위)

    - 카메라 미리보기: 거울처럼 보이고, 눈 테두리(주황)·홍채(초록) 점이 찍혀서 눈을 제대로 잡는지 확인
    - 눈 뜬 정도 막대: 왼눈/오른눈이 평소 대비 얼마나 떠 있는지. 윙크 판정 기준선(감음/뜸)이 같이 보여서
      "윙크가 왜 안 먹는지"(덜 감았는지, 반대쪽 눈도 같이 감기는지)를 눈으로 확인할 수 있음
    - 보정 상태: 처음 캘리브레이션 오차, 자동 보정 샘플 수, 최근 마우스 클릭 기준 실제 오차

창 안의 값은 main.py가 넘겨주는 get_state()로 0.15초마다 새로 읽습니다.
"""
from PyQt5 import QtWidgets, QtCore, QtGui

import theme
from clicker import WINK_CLOSE, WINK_OPEN, BLINK_COUNT, BACK_COUNT
from gaze_widgets import CloseButton, setup_floating_window
from menu_bar import paint_panel_background

WINK_LABEL = {"both": "아무 쪽 눈", "left": "왼눈", "right": "오른눈", "off": "끔"}


class EyeBars(QtWidgets.QWidget):
    """왼눈/오른눈 '평소 대비 뜬 정도' 막대 + 윙크 기준선."""
    MAX_R = 1.3

    def __init__(self):
        super().__init__()
        self.setFixedHeight(92)
        self.ratio = None
        self.wink_eyes = (0, 1)
        self.flash = False

    def set_values(self, ratio, wink_eyes, flash):
        self.ratio, self.wink_eyes, self.flash = ratio, wink_eyes, flash
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setFont(theme.ui_font(15))
        label_w, val_w = 92, 100
        x0, x1 = label_w, self.width() - val_w
        bw = x1 - x0
        for i, name in enumerate(("왼눈", "오른눈")):
            y = 8 + i * 40
            used = i in self.wink_eyes
            p.setPen(theme.INK if used else theme.INK_SOFT)
            p.drawText(QtCore.QRectF(0, y, label_w, 26), QtCore.Qt.AlignVCenter,
                       name + (" ★" if used else ""))
            bar = QtCore.QRectF(x0, y + 3, bw, 20)
            p.setPen(QtGui.QPen(theme.PANEL_EDGE, 1.5))
            p.setBrush(QtGui.QColor(255, 255, 255, 220))
            p.drawRoundedRect(bar, 10, 10)
            if self.ratio is not None:
                r = float(self.ratio[i])
                color = theme.RED if r < WINK_CLOSE else (theme.GREEN if r > WINK_OPEN else theme.YELLOW)
                p.setPen(QtCore.Qt.NoPen)
                p.setBrush(color)
                p.drawRoundedRect(QtCore.QRectF(x0 + 2, y + 5, (bw - 4) * min(r / self.MAX_R, 1.0), 16), 8, 8)
                p.setPen(theme.INK)
                state = "감음" if r < WINK_CLOSE else ("뜸" if r > WINK_OPEN else "중간")
                p.drawText(QtCore.QRectF(x1 + 8, y, val_w - 8, 26), QtCore.Qt.AlignVCenter, f"{r:.2f} {state}")
            for th in (WINK_CLOSE, WINK_OPEN):                         # 윙크 판정 기준선
                x = x0 + bw * th / self.MAX_R
                p.setPen(QtGui.QPen(theme.INK, 2, QtCore.Qt.DashLine))
                p.drawLine(QtCore.QPointF(x, y), QtCore.QPointF(x, y + 26))


class StatusWindow(QtWidgets.QWidget):
    close_requested = QtCore.pyqtSignal()

    def __init__(self, get_state):
        super().__init__()
        setup_floating_window(self)
        self.get_state = get_state

        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(20, 14, 14, 18)
        v.setSpacing(10)

        head = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("상태 확인")
        title.setFont(theme.title_font(28))
        title.setStyleSheet("color: #4A3428; background: transparent;")
        self.close_btn = CloseButton()
        self.close_btn.clicked.connect(lambda: self.close_requested.emit())
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.close_btn, 0, QtCore.Qt.AlignTop)
        v.addLayout(head)

        self.cam = QtWidgets.QLabel("카메라 준비 중…")
        self.cam.setAlignment(QtCore.Qt.AlignCenter)
        self.cam.setFixedSize(320, 240)
        self.cam.setFont(theme.ui_font(16, bold=False))
        self.cam.setStyleSheet("QLabel { background-color: rgba(60, 45, 35, 200); color: white;"
                               " border-radius: 12px; }")
        v.addWidget(self.cam, 0, QtCore.Qt.AlignHCenter)

        self.face = self._label(17)
        v.addWidget(self.face)

        v.addWidget(self._label(17, "눈 뜬 정도  (평소 = 1.00, 점선 = 윙크 기준)"))
        self.bars = EyeBars()
        v.addWidget(self.bars)
        self.wink = self._label(17)
        v.addWidget(self.wink)
        self.blink = self._label(17)
        v.addWidget(self.blink)

        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setStyleSheet("color: rgba(150, 115, 85, 120);")
        v.addWidget(line)

        self.calib = self._label(16)
        v.addWidget(self.calib)

        self.setFixedWidth(400)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.refresh)

    def _label(self, px, text=""):
        lab = QtWidgets.QLabel(text)
        lab.setFont(theme.ui_font(px, bold=False))
        lab.setWordWrap(True)
        lab.setTextFormat(QtCore.Qt.RichText)
        lab.setStyleSheet("color: #4A3428; background: transparent;")
        return lab

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        self.timer.start(150)
        area = QtWidgets.QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(area.left() + 24, area.top() + 24)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def set_frame(self, qimg):
        if self.isVisible():
            self.cam.setPixmap(QtGui.QPixmap.fromImage(qimg))

    def refresh(self):
        st = self.get_state()
        if st["mouse_mode"]:
            self.cam.setText("마우스 테스트 모드\n(카메라를 쓰지 않아요)")
            self.face.setText("")
            self.bars.set_values(None, (), False)
            self.wink.setText("")
            self.blink.setText("")
            self.calib.setText("마우스 테스트 모드라 보정 정보가 없어요.")
            return

        ok = '<span style="color:#2E8B57;">●</span>'
        bad = '<span style="color:#D0443A;">●</span>'
        if st["face"]:
            self.face.setText(f"{ok} 얼굴 인식 중 · 카메라 {st['fps']:.0f}fps")
        else:
            self.face.setText(f"{bad} 얼굴이 안 보여요 — 카메라 정면에 앉아 주세요")

        mode = st["wink_mode"]
        eyes = {"both": (0, 1), "left": (0,), "right": (1,)}.get(mode, ())
        self.bars.set_values(st["ratio"], eyes, st["wink_flash"])
        if mode == "off":
            msg = "윙크 클릭: 꺼짐"
        elif st["wink_flash"]:
            msg = '<b style="color:#F28228;">윙크 감지 → 클릭!</b>'
        elif st["paused"]:
            msg = f"윙크 클릭: {WINK_LABEL[mode]} (일시정지 중이라 클릭은 안 돼요)"
        else:
            msg = f"윙크 클릭: {WINK_LABEL[mode]} — ★ 눈 막대가 빨간 칸까지 내려가고, 반대쪽은 초록이어야 해요"
        self.wink.setText(msg)
        n = st["blinks"]
        action = "다시 시작" if st["paused"] else "일시정지"
        dots = "●" * min(n, BLINK_COUNT) + "○" * (BLINK_COUNT - min(n, BLINK_COUNT))
        self.blink.setText(f'깜빡임 <span style="color:#F28228;">{dots}</span>  '
                           f"— {BACK_COUNT}번: 뒤로가기 · {BLINK_COUNT}번: {action}")

        lines = []
        cal = st["calib_err"]
        if cal is not None:
            tr, va = cal
            txt = "처음 캘리브레이션 오차: "
            txt += f"학습 약 {tr:.0f}px" if tr == tr else "학습 -"
            txt += f" · 검증 약 {va:.0f}px" if va == va else ""
            lines.append(txt)
        lines.append(f"자동 보정 샘플: <b>{st['adapt_count']}개</b>"
                     + (f" · 큰 보정 {st['big_fixes']}회" if st["big_fixes"] else ""))
        acc = st["recent_acc"]
        if acc is None:
            lines.append("최근 실제 오차: 아직 마우스 클릭 기록이 없어요")
        else:
            n, px = acc
            grade = "좋음" if px < 150 else ("보통" if px < 300 else "많이 틀어짐")
            lines.append(f"최근 실제 오차: <b>약 {px:.0f}px</b> ({grade}, 최근 마우스 클릭 {n}번 기준)")
        self.calib.setText("<br>".join(lines))

    def paintEvent(self, event):
        paint_panel_background(self)
