# -*- coding: utf-8 -*-
"""
gaze_widgets.py — "시선으로 누를 수 있는 버튼"과 그 버튼들을 관리하는 부분

GazeButton
    평범한 QPushButton을 상속해서 마우스로 클릭해도 되고, 시선으로 일정 시간 바라봐도 눌립니다.
    두 경우 모두 결국 같은 clicked 신호가 나가기 때문에, 메뉴/키보드 코드는 "어떻게 눌렸는지"를
    신경 쓸 필요가 없습니다.
    - 하이라이트: 시선(또는 마우스)이 올라가면 테두리가 굵은 주황색으로 바뀝니다.
    - 응시 진행률: 바라보는 동안 버튼 아래쪽에 주황색 막대가 차오릅니다.

    - 윙크 전용 버튼(wink_only = True): 메뉴창 안의 버튼들. 바라보면 하이라이트만 되고 응시로는 눌리지 않으며,
      윙크했을 때만 눌립니다 (GazeInteraction.wink_click). 마우스 클릭은 그대로 됩니다.
    - 테마 모양(themed = True): 화상 키보드 키처럼 테마색(흰 바탕 + 테마색 테두리·글자)으로 그립니다.
      themed = False(기본)면 예전 갈색 모양 그대로 (상태 확인 창 등).

GazeInteraction
    main.py가 매 프레임 시선 좌표를 update_gaze(x, y, 시각)로 넣어주면,
    1) 지금 시선 아래에 있는 GazeButton을 찾고 (하이라이트 켜기/끄기)
    2) 같은 버튼을 dwell_sec(기본 1.2초) 동안 계속 보면 그 버튼을 click() 합니다. (윙크 전용 버튼은 제외)
    3) main.py가 윙크를 감지하면 wink_click()을 불러, 지금 보고 있는 윙크 전용 버튼을 누릅니다.
    응시 진행률(0~1)과 하이라이트 여부를 신호로 내보내서, 시선 커서가 게이지/테두리를 그립니다.

[모듈화] ui 폴더 안 파일끼리는 "from . import theme"처럼 점(.)을 붙여 불러옵니다.
         (프로젝트 맨 위 폴더에서 python main.py로 실행할 때 ui 폴더를 하나의 묶음(패키지)으로 찾기 때문)
GazeButton의 기본 생김새(갈색·주황 테두리)는 상태 확인 창이 그대로 씁니다.
메뉴창의 테마색 카드는 menu_bar.py에서 GazeButton을 물려받아 따로 그립니다.
"""
from PyQt5 import QtWidgets, QtCore, QtGui

from . import theme

DWELL_CLICK_SEC = 1.2       # 버튼을 이만큼 바라보면 클릭 (요구사항: 1~1.5초)
REPEAT_GAP_SEC = 0.5        # 키보드처럼 '연속 입력'이 되는 버튼은, 한 번 눌린 뒤 이만큼 쉬었다가 다시 채움

_REGISTRY = []              # 만들어진 GazeButton 전부 (시선 위치와 비교할 대상 목록)


def setup_floating_window(widget, click_through=False):
    """메뉴·키보드·커서 같은 '떠 있는 창' 공통 설정.
    테두리 없음 + 항상 위 + 작업표시줄에 안 뜸 + 배경 투명 + 다른 프로그램의 포커스를 뺏지 않음."""
    flags = (QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint
             | QtCore.Qt.Tool | QtCore.Qt.WindowDoesNotAcceptFocus)
    if click_through:
        # 커서 창처럼 클릭이 밑으로 통과해야 하는 경우. 투명한 부분뿐 아니라
        # 물개 그림 위를 클릭해도 밑에 있는 버튼/프로그램이 눌리도록 "입력 받지 않는 창"으로 지정
        flags |= QtCore.Qt.WindowTransparentForInput
    widget.setWindowFlags(flags)
    widget.setAttribute(QtCore.Qt.WA_TranslucentBackground)
    widget.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
    if click_through:
        widget.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)


class GazeButton(QtWidgets.QPushButton):
    def __init__(self, text="", parent=None, dwell_sec=DWELL_CLICK_SEC, repeatable=False,
                 font_px=22, radius=16, themed=False):
        super().__init__(text, parent)
        self.dwell_sec = dwell_sec            # 이 버튼을 누르는 데 필요한 응시 시간
        self.repeatable = repeatable          # 계속 보고 있으면 반복 입력 (키보드 글자키)
        self.wink_only = False                # True = 응시로는 안 눌리고 윙크로만 (메뉴창 버튼)
        self.themed = themed                  # True = 테마색으로 그림 (화상 키보드)
        self.active_when_paused = False       # 일시정지 중에도 시선으로 누를 수 있는지 (자물쇠만 True)
        self.on = False                       # 토글 버튼이 '켜짐' 상태로 보일지
        self.gaze_hover = False
        self.progress = 0.0
        self.radius = radius
        self.setFont(theme.ui_font(font_px))
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        _REGISTRY.append(self)

    # GazeInteraction이 호출
    def set_gaze_hover(self, on):
        if self.gaze_hover != on:
            self.gaze_hover = on
            self.update()

    def set_progress(self, frac):
        frac = max(0.0, min(1.0, frac))
        if abs(frac - self.progress) > 0.01 or (frac == 0.0) != (self.progress == 0.0):
            self.progress = frac
            self.update()

    def set_on(self, on):
        self.on = on
        self.update()

    def is_highlighted(self):
        return self.gaze_hover or self.underMouse()

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(3, 3, -3, -3)
        hl = self.is_highlighted()
        if self.themed:                        # 테마색: 흰 바탕(켜짐 = 연한 테마색) + 테마색 테두리, 하이라이트 = 진한 테마색
            th = theme.current()
            bg = QtGui.QColor(th["light"]) if self.on else QtGui.QColor(255, 255, 255, 225)
            if not self.isEnabled():
                bg = QtGui.QColor(255, 255, 255, 130)
            edge = th["deep"] if hl else theme.with_alpha(th["main"], 0.55 if self.isEnabled() else 0.25)
            gauge, ink = th["main"], (th["deep"] if self.isEnabled() else theme.with_alpha(th["deep"], 0.45))
        else:                                  # 기본: 갈색 (상태 확인 창 등)
            bg = QtGui.QColor(theme.BTN_ON if self.on else theme.BTN_BG)
            edge = theme.HIGHLIGHT if hl else theme.BTN_EDGE
            gauge, ink = theme.GAUGE, (theme.INK if self.isEnabled() else theme.INK_SOFT)
        if self.isDown():
            bg = bg.darker(108)
        p.setPen(QtGui.QPen(edge, 5 if hl else 2))   # 하이라이트 = 굵은 테두리
        p.setBrush(bg)
        p.drawRoundedRect(r, self.radius, self.radius)

        if self.progress > 0:                  # 응시 진행 막대
            bar = QtCore.QRectF(r.left() + 12, r.bottom() - 10, (r.width() - 24) * self.progress, 5)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(gauge)
            p.drawRoundedRect(bar, 2.5, 2.5)

        p.setPen(ink)
        p.setFont(self.font())
        p.drawText(r, QtCore.Qt.AlignCenter, self.text())


class CloseButton(GazeButton):
    """크롬 창처럼 오른쪽 위에 붙는 X 버튼. 평소엔 X만 보이고, 시선/마우스가 올라가면 빨간 배경."""

    def __init__(self, parent=None, size=46, themed=False):
        super().__init__("", parent, themed=themed)
        self.setFixedSize(size, size)
        self.setToolTip("닫기")

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(2, 2, -2, -2)
        hl = self.is_highlighted()
        if hl:
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(232, 17, 35))          # 크롬 닫기 버튼의 빨강
            p.drawRoundedRect(r, 10, 10)
        ink = theme.current()["deep"] if self.themed else theme.INK
        gauge = theme.current()["main"] if self.themed else theme.GAUGE
        if self.themed and not hl:                         # 테마 모양: 흰 동그라미 바탕
            p.setPen(QtGui.QPen(theme.with_alpha(theme.current()["main"], 0.6), 2))
            p.setBrush(QtGui.QColor(255, 255, 255, 235))
            p.drawEllipse(r)
        if self.progress > 0:                              # 응시 진행률을 테두리로 표시
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255) if hl else gauge, 4))
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawArc(r.adjusted(4, 4, -4, -4), 90 * 16, int(-360 * 16 * self.progress))
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255) if hl else ink, 3.5)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen)
        c = r.center()
        d = r.width() * 0.2
        p.drawLine(QtCore.QPointF(c.x() - d, c.y() - d), QtCore.QPointF(c.x() + d, c.y() + d))
        p.drawLine(QtCore.QPointF(c.x() - d, c.y() + d), QtCore.QPointF(c.x() + d, c.y() - d))


class GazeInteraction(QtCore.QObject):
    progress_changed = QtCore.pyqtSignal(float)    # 0~1 — 물개 커서 둘레 게이지
    hover_changed = QtCore.pyqtSignal(bool)        # 시선이 버튼 위에 있는지 — 물개 커서 하이라이트
    dwell_clicked = QtCore.pyqtSignal(object, float)   # (눌린 버튼의 화면 위치 QRect, 시각) — 자동 보정용

    def __init__(self, parent=None):
        super().__init__(parent)
        self.enabled = True        # 캘리브레이션 중에는 False
        self.paused = False        # 일시정지 중에는 active_when_paused 버튼(자물쇠)만 반응
        self._target = None
        self._start = 0.0
        self._fired = False

    def reset(self):
        """현재 보고 있던 버튼의 하이라이트/진행률을 지움."""
        if self._target is not None:
            try:
                self._target.set_gaze_hover(False)
                self._target.set_progress(0.0)
            except RuntimeError:           # 버튼이 이미 삭제된 경우
                pass
        self._target = None
        self.progress_changed.emit(0.0)
        self.hover_changed.emit(False)

    def over_button(self):
        """지금 시선이 데모의 버튼 위에 있는지 (응시 클릭이 다른 프로그램 클릭과 겹치지 않게 확인용)."""
        return self._target is not None

    def _hit_test(self, x, y):
        """화면 좌표 (x, y) 아래에 있는, 지금 누를 수 있는 GazeButton을 찾음."""
        pt = QtCore.QPoint(int(x), int(y))
        for btn in list(_REGISTRY):
            try:
                if not btn.isVisible() or not btn.isEnabled():
                    continue
                if self.paused and not btn.active_when_paused:
                    continue
                rect = QtCore.QRect(btn.mapToGlobal(QtCore.QPoint(0, 0)), btn.size())
                if rect.contains(pt):
                    return btn
            except RuntimeError:           # 삭제된 버튼은 목록에서 제거
                _REGISTRY.remove(btn)
        return None

    def update_gaze(self, x, y, now):
        if not self.enabled:
            return
        target = self._hit_test(x, y)

        if target is not self._target:      # 다른 버튼(또는 빈 곳)으로 시선 이동 → 처음부터 다시
            self.reset()
            self._target = target
            self._start = now
            self._fired = False
            if target is not None:
                target.set_gaze_hover(True)
                self.hover_changed.emit(True)

        if target is None:
            return
        if target.wink_only:                # 메뉴창 버튼: 하이라이트만, 응시 게이지·응시 클릭 없음 (윙크로만 누름)
            return
        if self._fired:                     # 이미 눌렀고 반복 입력 버튼이 아니면, 시선을 뗐다가 다시 와야 함
            return

        frac = (now - self._start) / target.dwell_sec
        if frac >= 1.0:
            target.set_progress(0.0)
            self.progress_changed.emit(0.0)
            if target.repeatable:
                self._start = now + REPEAT_GAP_SEC
            else:
                self._fired = True
            # 자동 보정: "방금 이 버튼을 보고 있었다"는 정보. 클릭하면 버튼이 사라질 수도 있어서 먼저 위치를 보냄
            self.dwell_clicked.emit(QtCore.QRect(target.mapToGlobal(QtCore.QPoint(0, 0)), target.size()), now)
            target.click()                  # 마우스로 누른 것과 똑같이 clicked 신호 발생
            return
        frac = max(0.0, frac)
        target.set_progress(frac)
        self.progress_changed.emit(frac)

    def wink_click(self, now=0.0):
        """윙크했을 때 호출 (main.py). 지금 보고 있는 버튼이 윙크 전용(메뉴창 버튼)이면 그 버튼을 누르고 True.
        아니면 아무것도 안 하고 False → main.py가 대신 실제 마우스 클릭을 함."""
        target = self._target
        if target is None or not target.wink_only:
            return False
        try:
            if not target.isVisible() or not target.isEnabled():
                return False
            self.dwell_clicked.emit(QtCore.QRect(target.mapToGlobal(QtCore.QPoint(0, 0)), target.size()), now)
        except RuntimeError:
            return False
        target.click()
        return True
