# -*- coding: utf-8 -*-
"""
main.py — 시선 추적 데모 실행 파일 (두더지 캘리브레이션 → 물개 커서 → 메뉴바)

설치:   pip install opencv-python mediapipe numpy PyQt5
실행:   python main.py                 (카메라로 실행 — 시작하면 두더지 캘리브레이션부터)
        python main.py --mouse         (테스트용 — 카메라 없이 마우스를 시선 대신 사용)
        python main.py --skip-calib    (저장된 calibration.npz가 있으면 캘리브레이션 건너뜀)
        python main.py --camera 1 --hd (카메라 번호 / 고해상도 — 원본과 같은 옵션)
종료:   메뉴판 아래 "종료" 버튼, 캘리브레이션 중 ESC, 또는 터미널에서 Ctrl+C

전체 흐름
    1) 카메라 스레드(CameraWorker)가 계속 얼굴 특징값을 보내줍니다.
    2) 두더지 캘리브레이션(MoleCalibrationWindow)이 그 값으로 W(시선→화면 변환식)를 만듭니다.
    3) 이후에는 GazeSession이 매 프레임 화면 좌표를 계산 → _on_gaze()가
       물개 커서 이동 / 돋보기 위치 / 시선 버튼(응시 클릭·하이라이트)에 나눠줍니다.
    4) 오른쪽 아래 메뉴 아이콘 → 메뉴판에서 모드를 바꾸면, 이 파일의 함수들이 실제로 상태를 바꿉니다.

이 파일은 "누가 무엇을 할지" 연결만 하는 배선판입니다. 계산은 gaze_core.py, 화면은 각 UI 파일에 있습니다.
"""
import argparse
import signal
import sys
import time

EYE_LOST_SEC = 0.3   # 이 시간 이상 눈이 안 잡히면 X 표시 (잠깐 놓친 것까지 X가 깜빡이지 않도록)

from PyQt5 import QtWidgets, QtCore, QtGui

import theme
from gaze_core import GazeSession, save_calibration, load_calibration
from gaze_widgets import GazeInteraction
from mole_calibration import MoleCalibrationWindow
from seal_cursor import SealCursorOverlay
from magnifier import Magnifier, MAX_LEVEL
from menu_bar import MenuDock, MenuPanel, anchor_bottom_right
from onscreen_keyboard import OnScreenKeyboard


class DemoApp(QtCore.QObject):
    def __init__(self, app, args):
        super().__init__()
        self.app, self.args = app, args
        self.mouse_mode = args.mouse
        self.geo = app.primaryScreen().geometry()

        # 지금 상태 (메뉴판 상태 칩과 오른쪽 아래 표시에 그대로 보여짐)
        self.calibrating = False
        self.tracking_started = False
        self.paused = False
        self.zoom = 1
        self.trail_on = True
        self.keyboard_open = False
        self.panel_open = False
        self.last_eye_t = time.time()  # 마지막으로 눈이 인식된 시각

        self.session = None            # 캘리브레이션이 끝나면 GazeSession (마우스 모드에선 사용 안 함)
        self.calib_win = None

        # 화면 부품들
        self.interaction = GazeInteraction()
        self.cursor = SealCursorOverlay()
        self.lens = Magnifier()
        self.dock = MenuDock()
        self.panel = MenuPanel()
        self.keyboard = OnScreenKeyboard()

        # 시선 버튼 상태 → 물개 커서 (게이지, 하이라이트)
        self.interaction.progress_changed.connect(self.cursor.set_gauge)
        self.interaction.hover_changed.connect(self.cursor.set_highlight)

        # 메뉴 버튼 → 실제 동작
        self.dock.open_requested.connect(self.open_panel)
        self.dock.unlock_requested.connect(self.resume)
        self.panel.close_requested.connect(self.close_panel)
        self.panel.zoom_in_requested.connect(self.zoom_in)
        self.panel.zoom_out_requested.connect(self.zoom_out)
        self.panel.pause_requested.connect(self.pause)
        self.panel.keyboard_toggle_requested.connect(self.toggle_keyboard)
        self.panel.trail_toggle_requested.connect(self.toggle_trail)
        self.panel.recalibrate_requested.connect(self.recalibrate)
        self.panel.quit_requested.connect(self.app.quit)
        self.keyboard.close_requested.connect(self.toggle_keyboard)

        # 시선 입력원: 카메라 또는 (테스트용) 마우스
        if self.mouse_mode:
            self.mouse_timer = QtCore.QTimer(self)
            self.mouse_timer.timeout.connect(self._on_mouse_tick)
        else:
            from camera_worker import CameraWorker      # 마우스 모드에선 mediapipe를 불러오지 않음
            self.worker = CameraWorker(args.camera, args.hd)
            self.worker.frame_ready.connect(self._on_frame)
            self.worker.camera_error.connect(self._on_camera_error)
        self.app.aboutToQuit.connect(self._shutdown)

    def start(self):
        if self.mouse_mode:
            self.mouse_timer.start(30)
            print("[마우스 테스트 모드] 마우스 위치를 시선 대신 사용합니다.")
        else:
            self.worker.start()
        saved = load_calibration() if (self.args.skip_calib and not self.mouse_mode) else None
        if saved is not None:
            print("[캘리브레이션] 저장된 calibration.npz를 사용합니다.")
            self.session = GazeSession(saved[0], saved[1], self.geo.width(), self.geo.height())
            self._enter_tracking()
        else:
            self.start_calibration()

    # ── 캘리브레이션 ──────────────────────────────────────────────
    def start_calibration(self):
        self.calibrating = True
        self.interaction.enabled = False
        self.interaction.reset()
        self.panel_open = self.keyboard_open = False
        for w in (self.cursor, self.lens, self.dock, self.panel, self.keyboard):
            w.hide()
        # 이전 캘리브레이션 창은 여기서 새 창으로 교체될 때 정리됨 (닫힌 뒤라 안전)
        self.calib_win = MoleCalibrationWindow(self.mouse_mode, self._on_calib_finished,
                                               self._on_calib_cancelled)
        self.calib_win.showFullScreen()

    def _on_calib_finished(self, W, base, train_err, val_err):
        self.calibrating = False
        if not self.mouse_mode:
            if W is None or base is None:
                QtWidgets.QMessageBox.warning(None, "캘리브레이션 실패",
                                              "얼굴 데이터가 부족해요. 카메라 정면에 앉아서 다시 진행해 주세요.")
                QtCore.QTimer.singleShot(0, self.start_calibration)
                return
            save_calibration(W, base)
            self.session = GazeSession(W, base, self.geo.width(), self.geo.height())
            msg = "[캘리브레이션] 완료"
            if train_err is not None:
                msg += f" — 학습 오차 약 {train_err:.0f}px"
            if val_err is not None:
                msg += f", 검증 오차 약 {val_err:.0f}px"
            print(msg)
        self._enter_tracking()

    def _on_calib_cancelled(self):
        self.calibrating = False
        if not self.tracking_started:          # 처음 캘리브레이션을 취소하면 데모 종료
            self.app.quit()
            return
        self._enter_tracking()                 # 다시 하기를 취소하면 예전 결과로 계속

    def _enter_tracking(self):
        self.tracking_started = True
        self.paused = False
        self.interaction.paused = False
        self.interaction.enabled = True
        self.cursor.set_paused(False)
        self.dock.set_locked(False)
        self.cursor.show()
        self.dock.show()
        self._apply_state()
        self.last_eye_t = time.time()
        self.cursor.set_eye_lost(False)

    # ── 시선 입력 ─────────────────────────────────────────────────
    def _on_frame(self, feat, opens, t):
        """카메라 한 프레임. 캘리브레이션 중이면 두더지 창으로, 아니면 화면 좌표로 바꿔서 사용."""
        if self.calibrating:
            if self.calib_win is not None:
                self.calib_win.on_feature(feat, opens, t)
            return
        if self.session is None:
            return
        if feat is None:                                    # 얼굴/눈을 못 찾음
            if t - self.last_eye_t > EYE_LOST_SEC:
                self.cursor.set_eye_lost(True)
        else:                                               # 다시 인식됨 → X 사라짐
            self.last_eye_t = t
            self.cursor.set_eye_lost(False)
        p = self.session.process(feat, opens)
        if p is not None:                       # None = 얼굴 없음/깜빡임 → 커서는 그 자리에 그대로
            self._on_gaze(p[0] + self.geo.x(), p[1] + self.geo.y(), t)

    def _on_mouse_tick(self):
        if self.calibrating or not self.tracking_started:
            return
        pos = QtGui.QCursor.pos()
        self._on_gaze(pos.x(), pos.y(), time.time())

    def _on_gaze(self, x, y, now):
        self.cursor.move_to(x, y, now)                  # 물개 커서 + 궤적
        if self.zoom > 1 and not self.paused:
            self.lens.follow(x, y)                      # 돋보기
        self.interaction.update_gaze(x, y, now)         # 응시 클릭 + 하이라이트

    # ── 메뉴 동작 ─────────────────────────────────────────────────
    def open_panel(self):
        self.panel_open = True
        self.dock.hide()
        self._apply_state()
        self.panel.show()
        anchor_bottom_right(self.panel)
        self._raise_cursor()

    def close_panel(self):
        self.panel_open = False
        self.panel.hide()
        self.dock.show()
        self._apply_state()

    def zoom_in(self):
        self.zoom = min(MAX_LEVEL, self.zoom * 2)
        self._apply_state()

    def zoom_out(self):
        self.zoom = max(1, self.zoom // 2)
        self._apply_state()

    def pause(self):
        """일시정지: 커서만 숨기고 프로그램은 뒤에서 계속 실행. 메뉴 아이콘은 자물쇠로 바뀜."""
        self.paused = True
        self.interaction.paused = True
        self.interaction.reset()
        self.cursor.set_paused(True)
        self.panel_open = False
        self.panel.hide()
        self.dock.set_locked(True)
        self.dock.show()
        self._apply_state()

    def resume(self):
        """자물쇠를 3초 바라보면(또는 클릭하면) 다시 활성화."""
        self.paused = False
        self.interaction.paused = False
        self.interaction.reset()
        self.cursor.set_paused(False)
        self.dock.set_locked(False)
        self._apply_state()

    def toggle_keyboard(self):
        self.keyboard_open = not self.keyboard_open
        if self.keyboard_open:
            self.keyboard.show()
            self._place_keyboard()
        else:
            self.keyboard.hide()
        self._apply_state()

    def toggle_trail(self):
        self.trail_on = not self.trail_on
        self.cursor.set_trail(self.trail_on)
        self._apply_state()

    def recalibrate(self):
        self.panel_open = False
        self.panel.hide()
        QtCore.QTimer.singleShot(150, self.start_calibration)   # 버튼 처리가 끝난 뒤 시작

    # ── 화면 정리 ─────────────────────────────────────────────────
    def _apply_state(self):
        """모드가 바뀔 때마다: 메뉴판 상태 칩, 오른쪽 아래 상태 글자, 돋보기 표시를 맞춤."""
        st = {"paused": self.paused, "zoom": self.zoom, "trail": self.trail_on,
              "keyboard": self.keyboard_open}
        self.panel.update_state(st)
        self.lens.set_level(self.zoom)
        self.lens.setVisible(self.zoom > 1 and not self.paused and not self.calibrating)

        if self.paused:
            text = "일시정지 중 · 자물쇠를 3초 바라보면 다시 켜져요"
        else:
            parts = ["활성", f"배율 ×{self.zoom}", "잔상 ON" if self.trail_on else "잔상 OFF"]
            if self.keyboard_open:
                parts.append("키보드")
            text = " · ".join(parts)
        self.dock.set_status_text(text)
        if self.keyboard_open:
            self._place_keyboard()
        self._raise_cursor()

    def _place_keyboard(self):
        """키보드는 화면 아래 가운데. 오른쪽 아래 메뉴 아이콘과 겹치면 왼쪽으로 비켜줌."""
        kb = self.keyboard
        kb.adjustSize()
        area = self.app.primaryScreen().availableGeometry()
        x = area.center().x() - kb.width() // 2
        dock_left = self.dock.x() if self.dock.isVisible() else area.right()
        if x + kb.width() > dock_left - 16:
            x = max(area.left() + 16, dock_left - 16 - kb.width())
        kb.move(x, area.bottom() - kb.height() - 20)

    def _raise_cursor(self):
        """물개 커서와 돋보기가 메뉴·키보드보다 항상 위에 보이도록."""
        if self.lens.isVisible():
            self.lens.raise_()
        self.cursor.raise_()

    def _on_camera_error(self, msg):
        QtWidgets.QMessageBox.critical(None, "카메라 오류", msg)
        self.app.quit()

    def _shutdown(self):
        if not self.mouse_mode:
            self.worker.stop()
            self.worker.wait(1500)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--hd", action="store_true",
                    help="웹캠이 720p/1080p를 지원하면 더 높은 해상도로 시도 (기본은 640x480)")
    ap.add_argument("--mouse", action="store_true", help="카메라 없이 마우스로 UI 테스트")
    ap.add_argument("--skip-calib", action="store_true",
                    help="저장된 calibration.npz가 있으면 캘리브레이션 건너뜀")
    args = ap.parse_args()

    # 화면 배율(125%, 150%)이 켜진 노트북에서도 창 크기·좌표가 어긋나지 않도록
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)   # 캘리브레이션 창이 닫히는 순간 프로그램이 꺼지지 않도록
    signal.signal(signal.SIGINT, signal.SIG_DFL)   # 터미널 Ctrl+C로 바로 종료

    theme.load_fonts()
    demo = DemoApp(app, args)
    demo.start()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
