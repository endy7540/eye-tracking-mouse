# -*- coding: utf-8 -*-
"""
main.py — 시선 추적 데모 실행 파일 (두더지 캘리브레이션 → 시선 커서 → 메뉴바)

설치:   pip install opencv-python mediapipe numpy PyQt5
실행:   python main.py                 (카메라로 실행 — 시작하면 두더지 캘리브레이션부터)
        python main.py --mouse         (테스트용 — 카메라 없이 마우스를 시선 대신 사용)
        python main.py --recalibrate   (저장된 캘리브레이션을 무시하고 처음부터 다시)
        python main.py --check         (시작할 때 숫자 맞추기로 정확도 확인 — 새로 보정한 직후에는 자동으로 함)
        python main.py --camera 1 --hd (카메라 번호 / 고해상도 — 원본과 같은 옵션)
종료:   메뉴창 오른쪽 아래 "종료" 버튼, 캘리브레이션 중 ESC, 또는 터미널에서 Ctrl+C

전체 흐름
    1) 카메라 스레드(CameraWorker)가 계속 얼굴 특징값을 보내줍니다.
    2) 두더지 캘리브레이션(MoleCalibrationWindow)이 그 값으로 W(시선→화면 변환식)를 만듭니다.
    3) 이후에는 GazeSession이 매 프레임 화면 좌표를 계산 →
       _on_gaze()가 시선 커서 이동 / 메뉴 아이콘 나타나기 / 시선 버튼(응시 클릭·하이라이트) / 스크롤에 나눠줍니다.
    4) 오른쪽 아래 메뉴 아이콘 → 화면 가운데 메뉴창에서 모드를 바꾸면, 이 파일의 함수들이 실제로 상태를 바꿉니다.
       (커서 투명도·테마·스크롤은 settings.json에 저장되어 다음에 켜도 그대로)
       ★ 메뉴창(설정 화면 포함) 안의 버튼은 윙크로만 눌립니다. 윙크 설정이 "끔"이어도 메뉴창 안에서는
         양쪽 눈 윙크를 받아서 지금 보고 있는 메뉴 버튼을 누릅니다 (_on_frame의 윙크 처리).

이 파일은 "누가 무엇을 할지" 연결만 하는 배선판입니다. 계산은 gaze_core.py, 화면은 각 UI 파일에 있습니다.
"""
import argparse
import math
import signal
import socket
import sys
import time
from collections import deque

import numpy as np

# mediapipe는 반드시 PyQt5보다 먼저 불러와야 합니다.
# PyQt5가 자기 폴더에 들어 있는 오래된 C++ 런타임 DLL을 먼저 올려버리면,
# 나중에 mediapipe를 불러올 때 "DLL 초기화 루틴을 실행할 수 없습니다" 오류가 납니다.
# (마우스 테스트 모드에선 카메라를 안 쓰므로 불러오지 않음)
if "--mouse" not in sys.argv:
    import mediapipe  # noqa: F401

EYE_LOST_SEC = 0.3   # 이 시간 이상 눈이 안 잡히면 X 표시 (잠깐 놓친 것까지 X가 깜빡이지 않도록)

# 자동 보정 — 실제 마우스 클릭을 "그곳을 보고 있었다"로 쓸지 판단하는 기준
MOUSE_MOVE_MIN_PX = 40      # 클릭 전 1.5초 동안 마우스가 이만큼은 움직였어야 함 (목표를 찾아간 클릭)
MOUSE_SETTLE_PX = 15        # 클릭 직전 0.12초 동안은 거의 멈춰 있어야 함 (목표에 도착해서 누른 클릭)
CALIB_PORT = 47322          # 미니게임이 맞힌 별·두더지 위치를 보내오는 UDP 포트 (minigames.py 와 같아야 함)
GAME_SETTLE_SEC = 0.30      # 맞힌 뒤 이만큼 기다렸다가(터지는 연출을 보는 동안의 눈 데이터를 모은 뒤) 샘플로 사용

from PyQt5 import QtWidgets, QtCore, QtGui

from ui import theme
from vision.gaze_core import GazeSession, save_calibration, load_calibration
from calibration.adaptive import AdaptiveCalibrator, left_button_down
from control.clicker import (WinkDetector, DwellClicker, BlinkGesture, click_at, WINK_EYES, BLINK_COUNT,
                             BACK_COUNT)
from control.text_sender import send_back
from control.scroller import Scroller
from ui.status_window import StatusWindow
import json
from pathlib import Path

SETTINGS_FILE = Path(__file__).resolve().parent / "settings.json"
WINK_CYCLE = ["both", "left", "right", "off"]
from ui.gaze_widgets import GazeInteraction
from calibration.mole_calibration import MoleCalibrationWindow
from calibration.number_check import NumberCheckWindow
from ui.seal_cursor import SealCursorOverlay, DEFAULT_OPACITY, OPACITY_STEP, MIN_OPACITY, MAX_OPACITY
from ui.menu_bar import MenuDock, MenuPanel
from ui.onscreen_keyboard import OnScreenKeyboard


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
        self.trail_on = True
        self.keyboard_open = False
        self.panel_open = False
        self.last_eye_t = time.time()  # 마지막으로 눈이 인식된 시각

        self.session = None            # 캘리브레이션이 끝나면 GazeSession (마우스 모드에선 사용 안 함)
        self.adapt = None              # 자동 보정기 (adaptive.py)
        self.last_gaze = None          # 마지막 시선 위치 (화면 좌표)
        self.mouse_hist = deque()      # 실제 마우스 위치 기록 (시각, x, y)
        self.mouse_was_down = False

        # 시선으로 다른 프로그램 클릭 (clicker.py)
        cfg = self._load_settings()
        self.wink_mode = cfg.get("wink_mode", "both")   # 윙크 클릭: 아무 쪽/왼눈/오른눈/끔 (기본: 아무 쪽 눈이든 한쪽만 감으면 클릭)
        if self.wink_mode not in WINK_CYCLE:
            self.wink_mode = "both"
        self.dwell_on = bool(cfg.get("dwell_on", False))  # 응시 클릭: 기본 꺼짐 (읽다가 실수로 눌릴 수 있어서)
        self.scroll_on = bool(cfg.get("scroll_on", False))  # 스크롤 모드: 기본 꺼짐 (메뉴 아이콘 옆 토글로 켜고 끔)
        theme.set_theme(cfg.get("theme", theme.DEFAULT_THEME))   # 테마 (메뉴·아이콘·커서 색) — 기본: 하늘
        try:
            self.cursor_opacity = float(cfg.get("cursor_opacity", DEFAULT_OPACITY))   # 커서 진하기 (투명도 = 1 - 진하기)
        except (TypeError, ValueError):
            self.cursor_opacity = DEFAULT_OPACITY
        self.cursor_opacity = max(MIN_OPACITY, min(MAX_OPACITY, self.cursor_opacity))
        self.last_wink_click_t = 0.0
        self.last_face_t = 0.0                           # 상태 확인 창: 마지막으로 얼굴이 잡힌 시각
        self.frame_times = deque(maxlen=30)              # 상태 확인 창: 카메라 fps 계산용
        self.calib_err = None                            # (학습 오차, 검증 오차) px
        self.wink = WinkDetector()
        self.dwell = DwellClicker()
        self.blink_gesture = BlinkGesture()   # 두 눈 연속 깜빡임: 3번 → 뒤로가기, 5번 → 일시정지/다시 시작
        self.synthetic_until = 0.0     # 우리가 만든 클릭 직후엔 '실제 마우스 클릭'으로 착각해 학습하지 않도록
        self.calib_win = None
        self.checking = False          # 숫자 맞추기(정확도 확인) 중
        self.number_win = None
        self.check_err = None          # 마지막 숫자 맞추기의 평균 오차(px)

        # 화면 부품들
        self.interaction = GazeInteraction()
        self.cursor = SealCursorOverlay()
        self.dock = MenuDock()
        self.panel = MenuPanel()
        self.keyboard = OnScreenKeyboard()
        self.status_win = StatusWindow(self._status_state)
        # 스크롤 모드: 켜져 있으면(self.scroll_on) 화면 위·아래 가장자리를 볼 때 스크롤 (control/scroller.py)
        self.scroller = Scroller(retarget_pointer=not self.mouse_mode,
                                 exclude_rects=lambda: [w.frameGeometry() for w in (self.dock, self.status_win)
                                                        if w.isVisible()])
        self.scroller.auto_off.connect(self._on_scroll_auto_off)
        self.scroller.pointer_moved.connect(self._on_scroll_pointer_moved)
        self.scroller.progress_changed.connect(self._set_gauge)    # 스크롤 시작 전 머무름 게이지
        self.cursor.set_opacity(self.cursor_opacity)

        # 시선 버튼 상태 → 시선 커서 (게이지, 하이라이트)
        self.interaction.progress_changed.connect(self._set_gauge)
        self.interaction.hover_changed.connect(self.cursor.set_highlight)
        self.interaction.dwell_clicked.connect(self._on_dwell_click)   # 응시 클릭 → 자동 보정 데이터

        # 메뉴 버튼 → 실제 동작
        self.dock.open_requested.connect(self.open_panel)
        self.dock.unlock_requested.connect(self.resume)
        self.dock.scroll_toggle_requested.connect(self.toggle_scroll)
        self.panel.close_requested.connect(self.close_panel)
        self.panel.transparency_up_requested.connect(lambda: self.change_opacity(-OPACITY_STEP))    # 투명도 + = 진하기 -
        self.panel.transparency_down_requested.connect(lambda: self.change_opacity(+OPACITY_STEP))
        self.panel.theme_selected.connect(self.set_theme)
        self.panel.pause_requested.connect(self.pause)
        self.panel.keyboard_toggle_requested.connect(self.toggle_keyboard)
        self.panel.trail_toggle_requested.connect(self.toggle_trail)
        self.panel.recalibrate_requested.connect(self.recalibrate)
        self.panel.wink_toggle_requested.connect(self.toggle_wink)
        self.panel.dwell_toggle_requested.connect(self.toggle_dwell)
        self.panel.status_requested.connect(self.toggle_status)
        self.status_win.close_requested.connect(self.toggle_status)
        self.panel.quit_requested.connect(self.app.quit)
        self.keyboard.close_requested.connect(self.toggle_keyboard)

        # 시선 입력원: 카메라 또는 (테스트용) 마우스
        if self.mouse_mode:
            self.mouse_timer = QtCore.QTimer(self)
            self.mouse_timer.timeout.connect(self._on_mouse_tick)
        else:
            from vision.camera_worker import CameraWorker      # 마우스 모드에선 mediapipe를 불러오지 않음
            self.worker = CameraWorker(args.camera, args.hd)
            self.worker.frame_ready.connect(self._on_frame)
            self.worker.camera_error.connect(self._on_camera_error)
            self.worker.preview_ready.connect(self.status_win.set_frame)
            # 실제 마우스 클릭 감시 (다른 프로그램에서 누른 클릭까지) → 자동 보정 데이터
            self.mouse_poll = QtCore.QTimer(self)
            self.mouse_poll.timeout.connect(self._on_mouse_poll)
            self.mouse_poll.start(16)
        self._open_game_socket()
        self.app.aboutToQuit.connect(self._shutdown)

    def start(self):
        if self.mouse_mode:
            self.mouse_timer.start(30)
            print("[마우스 테스트 모드] 마우스 위치를 시선 대신 사용합니다.")
        else:
            self.worker.start()
        saved = load_calibration() if (not self.args.recalibrate and not self.mouse_mode) else None 
        if saved is not None:
            n_on = len(saved["online_feats"])
            print(f"[캘리브레이션] 저장된 calibration.npz를 사용합니다. (자동 보정 샘플 {n_on}개 포함)")
            if "calib_err" in saved:
                self.calib_err = tuple(float(x) for x in saved["calib_err"])
            self._setup_model(saved["W"], saved["base"], saved["anchor_feats"], saved["anchor_labels"],
                              saved["anchor_weights"], saved["online_feats"], saved["online_labels"])
            self._enter_tracking()
            if self.args.check:
                QtCore.QTimer.singleShot(400, self.start_number_check)
        else:
            self.start_calibration()

    # ── 캘리브레이션 ──────────────────────────────────────────────
    def start_calibration(self):
        self.calibrating = True
        self.interaction.enabled = False
        self.interaction.reset()
        self.panel_open = self.keyboard_open = False
        if self.status_win.isVisible():
            self.toggle_status()
        for w in (self.cursor, self.dock, self.panel, self.keyboard):
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
            nan = float("nan")
            self.calib_err = (train_err if train_err is not None else nan,
                              val_err if val_err is not None else nan)
            cw = self.calib_win          # 새 캘리브레이션 = 자동 보정 샘플도 처음부터 다시
            self._setup_model(W, base, cw.feats, cw.labels, cw.fit_weights)
            msg = "[캘리브레이션] 완료"
            if train_err is not None:
                msg += f" — 학습 오차 약 {train_err:.0f}px"
            if val_err is not None:
                msg += f", 검증 오차 약 {val_err:.0f}px"
            print(msg)
        self._enter_tracking()
        if not self.mouse_mode or self.args.check:      # 새 보정 직후 숫자 맞추기로 정확도 확인 + 추가 학습
            QtCore.QTimer.singleShot(400, self.start_number_check)

    def _setup_model(self, W, base, anchor_feats, anchor_labels, anchor_weights,
                     online_feats=None, online_labels=None):
        """캘리브레이션 결과로 자동 보정기와 GazeSession을 만들고 저장."""
        w, h = self.geo.width(), self.geo.height()
        self.adapt = AdaptiveCalibrator(W, anchor_feats, anchor_labels, anchor_weights, w, h,
                                        online_feats, online_labels)
        self.session = GazeSession(self.adapt.W, base, w, h, ranges=self.adapt.ranges, adaptive=self.adapt)
        self._save_model()

    def _save_model(self):
        extra = self.adapt.to_arrays()
        if self.calib_err is not None:
            extra["calib_err"] = np.array(self.calib_err, dtype=float)
        save_calibration(self.session.W, self.session.base, extra)

    # ── 미니게임에서 맞힌 별·두더지 → 자동 보정 (minigames.py 가 "T,x,y" 를 UDP 로 보내줌) ──
    def _open_game_socket(self):
        self.game_sock = None
        if self.mouse_mode:
            return
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind(("127.0.0.1", CALIB_PORT))
            s.setblocking(False)
            self.game_sock = s
        except OSError as e:
            print(f"[미니게임 보정] 포트 {CALIB_PORT} 를 열 수 없어요({e}) → 미니게임은 보정에 쓰지 않아요.")
            return
        self.game_poll = QtCore.QTimer(self)
        self.game_poll.timeout.connect(self._poll_game_targets)
        self.game_poll.start(30)

    def _poll_game_targets(self):
        while True:
            try:
                data, _ = self.game_sock.recvfrom(256)
            except (BlockingIOError, InterruptedError, OSError):
                break
            try:
                tag, xs, ys = data.decode("ascii", "ignore").split(",")[:3]
                x, y = float(xs), float(ys)
            except ValueError:
                continue
            if tag == "T" and self._learning_ready() and not self.checking and not self.paused:
                QtCore.QTimer.singleShot(int(GAME_SETTLE_SEC * 1000), lambda x=x, y=y: self._learn_game(x, y))

    def _learn_game(self, x, y):
        if self._learning_ready() and not self.checking and not self.paused:
            self._learn(time.time(), x, y, "game")

    # ── 숫자 맞추기: 보정 직후 정확도 확인 + 통과한 숫자를 정답으로 자동 보정에 반영 ──
    def start_number_check(self):
        if self.checking or self.calibrating or self.paused or not self.tracking_started:
            return
        self.checking = True
        self.interaction.enabled = False
        self.interaction.reset()
        self.panel_open = self.keyboard_open = False
        for w in (self.dock, self.panel, self.keyboard):
            w.hide()
        self.number_win = NumberCheckWindow(self.geo, self._on_check_sample, self._on_check_done)
        self.number_win.showFullScreen()
        self.number_win.activateWindow()
        self._raise_cursor()
        QtCore.QTimer.singleShot(200, self._raise_cursor)

    def _on_check_sample(self, t, x, y):
        """숫자를 통과 = 그 숫자를 보고 있었음 → 응시 클릭과 같은 방식으로 자동 보정 샘플로 사용."""
        self._show_check()
        if self._learning_ready():
            self._learn(t, x, y, "dwell")

    def _on_check_done(self, errs, skipped, cancelled):
        self.checking = False
        self.number_win = None
        self.interaction.enabled = True
        self.dock.show()
        if errs:
            self.check_err = sum(errs) / len(errs)
            print(f"[숫자 맞추기] 평균 오차 약 {self.check_err:.0f}px (통과 {len(errs)}개, 건너뜀 {skipped}개)")
        self._apply_state()

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
        self.frame_times.append(t)
        if feat is not None:
            self.last_face_t = t
        gesture = self.blink_gesture.update(opens, self.session.base, t)   # 일시정지 중에도 동작해야 다시 켤 수 있음
        if gesture == "back" and self._clicking_ready():
            print("[깜빡임] 3번 → 뒤로가기")
            send_back()
            self._show_badge("back")            # 시선 커서 위에 파란 ← 표시
        elif gesture == "pause":
            if self.paused:
                print("[깜빡임] 연속 깜빡임 → 다시 시작")
                self.resume()
            else:
                print("[깜빡임] 연속 깜빡임 → 일시정지")
                self.pause()
        # 윙크: 메뉴창(설정 화면 포함)이 열려 있으면 윙크 설정과 상관없이 양쪽 눈 윙크를 받아서 메뉴 버튼을 누름.
        #       메뉴창 밖(또는 메뉴 버튼이 아닌 곳)을 보고 윙크하면 원래대로 윙크 설정을 따라 실제 마우스 클릭.
        if self.panel_open:
            eyes = WINK_EYES["both"]
        else:
            eyes = WINK_EYES[self.wink_mode] if self.wink_mode != "off" else ()   # 꺼져 있어도 눈 막대는 보여주기
        fired = self.wink.update(opens, self.session.base, t, eyes)
        if fired and self._clicking_ready():
            if self.panel_open and self.interaction.wink_click(t):
                self.last_wink_click_t = t
                self._show_check()              # 메뉴 버튼을 윙크로 누름 → 커서 위에 초록 체크
            elif self.wink_mode != "off":
                self.last_wink_click_t = t
                self._gaze_click()              # 윙크 → 윙크 직전에 보던 곳(커서는 감는 동안 고정됨)을 클릭
        p = self.session.process(feat, opens, t)
        if p is not None:                       # None = 얼굴 없음/깜빡임 → 커서는 그 자리에 그대로
            self._on_gaze(p[0] + self.geo.x(), p[1] + self.geo.y(), t)

    def _on_mouse_tick(self):
        if self.calibrating or not self.tracking_started:
            return
        pos = QtGui.QCursor.pos()
        self._on_gaze(pos.x(), pos.y(), time.time())

    def _on_gaze(self, x, y, now):
        self.last_gaze = (x, y)
        try:                                            # 미니게임(minigames.py)에 시선 좌표 전달 (UDP, 로컬)
            if getattr(self, "_gs", None) is None:
                import socket
                self._gs = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._gs.sendto(f"{x:.0f},{y:.0f}".encode(), ("127.0.0.1", 47321))
        except Exception:
            pass
        self.cursor.move_to(x, y, now)                  # 시선 커서 + 궤적
        if self.checking and self.number_win is not None:
            self.number_win.on_gaze(x, y, now)          # 숫자 맞추기에 시선 전달
        if not self.checking:
            self.dock.update_gaze(x, y)                 # 커서가 가까이 오면 메뉴 아이콘이 나타남
        self.interaction.update_gaze(x, y, now)         # 응시 클릭 + 하이라이트
        self.scroller.update(x, y, now, self._scroll_blocked())    # 스크롤 모드 (꺼져 있으면 아무것도 안 함)
        if self.dwell_on and self._clicking_ready():   # 응시 클릭: 데모 버튼·메뉴 위가 아닐 때만 (버튼은 자기 방식대로 눌림)
            if self.interaction.over_button() or self._over_own_window(x, y) or self.scroller.engaged:
                self.dwell.reset()
            else:
                frac, pt = self.dwell.update(x, y, now)
                self._set_gauge(frac)
                if pt is not None:
                    self._gaze_click(pt)

    # ── 시선 클릭 (윙크 / 응시) ─────────────────────────────────────
    def _clicking_ready(self):
        return (not self.mouse_mode and not self.calibrating and not self.paused and not self.checking
                and self.session is not None and self.tracking_started)

    def _over_own_window(self, x, y):
        pt = QtCore.QPoint(int(x), int(y))
        return any(w.isVisible() and w.frameGeometry().contains(pt)
                   for w in (self.dock, self.panel, self.keyboard, self.status_win))

    def _gaze_click(self, pt=None):
        """실제 마우스로 좌클릭. pt가 없으면 마지막 시선 위치."""
        pt = pt or self.last_gaze
        if pt is None:
            return
        self.synthetic_until = time.time() + 0.4
        self.mouse_hist.clear()                 # 마우스가 순간이동한 기록이 자동 보정 판단에 섞이지 않게
        click_at(*pt)
        self._show_check()                      # 커서 위에 초록 체크 ✓
        self._set_gauge(0.0)
        self.cursor.set_highlight(True)         # 눌렸다는 표시로 커서 테두리를 잠깐 깜빡임
        QtCore.QTimer.singleShot(220, lambda: self.cursor.set_highlight(self.interaction.over_button()))

    def _scroll_blocked(self):
        """스크롤 띠를 잠깐 멈춰야 하는 상태 (모드는 그대로 두고 동작만 멈춤)."""
        return (self.paused or self.calibrating or self.checking or self.keyboard_open or self.panel_open
                or self.interaction.over_button())

    def _on_scroll_auto_off(self):
        """오래 스크롤을 안 써서 스크롤 모드가 스스로 꺼짐 → 토글·설정·상태 글자도 같이 끔."""
        self.scroll_on = False
        self._save_settings()
        self._apply_state()

    def _on_scroll_pointer_moved(self):
        """스크롤하려고 우리가 마우스 포인터를 옮긴 것을 '실제 마우스 조작'으로 착각해 학습하지 않게."""
        self.synthetic_until = time.time() + 0.4
        self.mouse_hist.clear()

    def _set_gauge(self, frac):
        """응시 게이지: 시선 커서 둘레."""
        self.cursor.set_gauge(frac)

    def _show_check(self):
        self._show_badge("check")

    def _show_badge(self, kind):
        self.cursor.show_badge(kind)

    def toggle_wink(self):
        """윙크 클릭: 아무 쪽 → 왼눈만 → 오른눈만 → 끔 → 아무 쪽 … (두 눈 같이 감기는 항상 무시)"""
        self.wink_mode = WINK_CYCLE[(WINK_CYCLE.index(self.wink_mode) + 1) % len(WINK_CYCLE)]
        self.wink.reset()
        self._save_settings()
        self._apply_state()

    def toggle_dwell(self):
        self.dwell_on = not self.dwell_on
        self.dwell.reset()
        self._set_gauge(0.0)
        self._save_settings()
        self._apply_state()

    def toggle_scroll(self):
        """메뉴 아이콘 옆 스크롤 ON/OFF. 실제 스크롤은 스크롤 담당 코드가 self.scroll_on을 보고 함."""
        self.scroll_on = not self.scroll_on
        self._save_settings()
        self._apply_state()

    def toggle_status(self):
        """상태 확인 창 열기/닫기. 열려 있을 때만 카메라 미리보기를 만들어서 평소엔 부담이 없게."""
        show = not self.status_win.isVisible()
        if not self.mouse_mode:
            self.worker.preview_on = show
        self.status_win.setVisible(show)
        self._apply_state()

    def _status_state(self):
        now = time.time()
        ft = self.frame_times
        fps = (len(ft) - 1) / (ft[-1] - ft[0]) if len(ft) > 1 and ft[-1] > ft[0] else 0.0
        return {
            "mouse_mode": self.mouse_mode,
            "face": now - self.last_face_t < 0.5,
            "fps": fps,
            "ratio": self.wink.last_ratio,
            "wink_mode": self.wink_mode,
            "wink_flash": now - self.last_wink_click_t < 0.8,
            "blinks": self.blink_gesture.progress(now),
            "paused": self.paused,
            "calib_err": self.calib_err,
            "adapt_count": self.adapt.count if self.adapt else 0,
            "big_fixes": self.adapt.big_fixes if self.adapt else 0,
            "recent_acc": self.adapt.recent_accuracy() if self.adapt else None,
            "check_err": self.check_err,
        }

    def _load_settings(self):
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_settings(self):
        try:
            SETTINGS_FILE.write_text(json.dumps({"wink_mode": self.wink_mode, "dwell_on": self.dwell_on,
                                                 "theme": theme.current_key(),
                                                 "cursor_opacity": self.cursor_opacity,
                                                 "scroll_on": self.scroll_on}),
                                     encoding="utf-8")
        except Exception as e:
            print("[설정] 저장 실패:", e)

    # ── 자동 보정 (쓰면 쓸수록 정확해짐) ──────────────────────────────
    def _learning_ready(self):
        return not self.mouse_mode and not self.calibrating and self.adapt is not None

    def _on_dwell_click(self, rect, t):
        """응시 클릭 성공 = 그 버튼을 보고 있었음. 버튼 위치를 정답으로 사용.
        가로로 긴 버튼(띄어쓰기 등)은 버튼 안 어디를 봤는지 모르니 가로 방향은 정답으로 쓰지 않음(세로도 마찬가지)."""
        self._show_check()                      # 데모 버튼을 바라봐서 눌렀을 때도 체크 ✓
        if not self._learning_ready():
            return
        gx, gy = self.last_gaze if self.last_gaze else (rect.center().x(), rect.center().y())
        w, h = rect.width(), rect.height()
        lx = rect.center().x() if w <= 1.6 * h else min(max(gx, rect.left() + h / 2), rect.right() - h / 2)
        ly = rect.center().y() if h <= 1.6 * w else min(max(gy, rect.top() + w / 2), rect.bottom() - w / 2)
        self._learn(t, lx, ly, "dwell")

    def _on_mouse_poll(self):
        """실제 마우스를 계속 지켜보다가, '목표로 움직여서 멈춘 뒤 누른 클릭'만 자동 보정에 사용."""
        now = time.time()
        pos = QtGui.QCursor.pos()
        self.mouse_hist.append((now, pos.x(), pos.y()))
        while self.mouse_hist and now - self.mouse_hist[0][0] > 2.0:
            self.mouse_hist.popleft()
        down = left_button_down()
        if now < self.synthetic_until:          # 윙크/응시로 우리가 누른 클릭은 학습에 쓰지 않음 (정답이 아니라 예측값이라서)
            self.mouse_was_down = down
            return
        if down and not self.mouse_was_down and self._learning_ready():
            moved = [(x, y) for (mt, x, y) in self.mouse_hist if now - 1.5 <= mt <= now - 0.12]
            path = sum(math.hypot(x2 - x1, y2 - y1) for (x1, y1), (x2, y2) in zip(moved, moved[1:]))
            settled = all(math.hypot(x - pos.x(), y - pos.y()) <= MOUSE_SETTLE_PX
                          for (mt, x, y) in self.mouse_hist if mt > now - 0.12)
            if path >= MOUSE_MOVE_MIN_PX and settled:
                self._learn(now, pos.x(), pos.y(), "mouse")
        self.mouse_was_down = down

    def _learn(self, t, x, y, kind):
        label = ((x - self.geo.x()) / self.geo.width(), (y - self.geo.y()) / self.geo.height())
        result = self.adapt.add_click(t, label, kind)
        if result in ("refit", "kept"):
            if result == "refit":
                self.session.set_model(self.adapt.W, self.adapt.ranges)
                print(f"[자동 보정] 샘플 {self.adapt.count}개로 다시 학습했어요")
            self._save_model()
            self._apply_state()

    # ── 메뉴 동작 ─────────────────────────────────────────────────
    def open_panel(self):
        self.panel_open = True
        self._apply_state()
        self.panel.show()
        self.panel.place()                      # 화면 가운데에 크게
        self._raise_cursor()

    def close_panel(self):
        self.panel_open = False
        self.panel.hide()
        self.dock.show()
        self._apply_state()

    def pause(self):
        """일시정지: 커서만 숨기고 프로그램은 뒤에서 계속 실행. 메뉴 아이콘은 자물쇠로 바뀜.
        열려 있던 메뉴창·화상 키보드·상태 확인 창도 같이 닫음 (일시정지 중엔 시선으로 누를 수 없어서)."""
        self.paused = True
        self.interaction.paused = True
        self.interaction.reset()
        self.cursor.set_paused(True)
        self.panel_open = False
        self.panel.hide()
        if self.keyboard_open:                  # 일시정지 중엔 키를 누를 수 없으니 화상 키보드도 닫음
            self.keyboard_open = False
            self.keyboard.hide()
        if self.status_win.isVisible():         # 상태 확인 창도 닫음 (카메라 미리보기도 끔)
            if not self.mouse_mode:
                self.worker.preview_on = False
            self.status_win.hide()
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

    def change_opacity(self, delta):
        """커서 진하기를 delta만큼 바꿈 (메뉴의 커서 투명도 -/+). 10%씩, 20%~100% 사이."""
        self.cursor_opacity = max(MIN_OPACITY, min(MAX_OPACITY, round(self.cursor_opacity + delta, 2)))
        self.cursor.set_opacity(self.cursor_opacity)
        self._save_settings()
        self._apply_state()

    def set_theme(self, key):
        """테마 바꾸기 → 메뉴창·메뉴 아이콘·스크롤 토글·커서·화상 키보드 색을 다시 그림."""
        theme.set_theme(key)
        self.cursor.refresh_theme()
        self.dock.refresh_theme()
        self.panel.refresh_theme()
        self.keyboard.refresh_theme()
        self._save_settings()
        self._apply_state()

    def recalibrate(self):
        self.panel_open = False
        self.panel.hide()
        QtCore.QTimer.singleShot(150, self.start_calibration)   # 버튼 처리가 끝난 뒤 시작

    # ── 화면 정리 ─────────────────────────────────────────────────
    def _apply_state(self):
        """모드가 바뀔 때마다: 메뉴창 카드 상태, 오른쪽 아래 상태 글자·스크롤 토글 표시를 맞춤."""
        st = {"paused": self.paused, "trail": self.trail_on,
              "keyboard": self.keyboard_open, "wink": self.wink_mode, "dwell": self.dwell_on,
              "status": self.status_win.isVisible(), "opacity": self.cursor_opacity,
              "theme": theme.current_key()}
        self.panel.update_state(st)
        self.dock.set_scroll(self.scroll_on)        # 메뉴 아이콘 옆 스크롤 토글 표시
        self.scroller.set_enabled(self.scroll_on and not self.paused)   # 스크롤 로직도 같은 값을 따라감 (일시정지 중엔 스크롤 띠도 숨김)
        self.dock.set_menu_open(self.panel_open)    # 메뉴창이 열려 있으면 아이콘만 숨기고 토글은 그대로

        if self.paused:
            text = f"일시정지 중 · 자물쇠를 3초 보거나 눈을 {BLINK_COUNT}번 빠르게 깜빡이면 다시 켜져요"
        else:
            parts = ["활성", "잔상 ON" if self.trail_on else "잔상 OFF"]
            if self.adapt is not None and self.adapt.count:
                parts.append(f"자동 보정 {self.adapt.count}")
            if self.keyboard_open:
                parts.append("키보드")
            if self.scroll_on:
                parts.append("스크롤")
            if not self.mouse_mode:
                wink_name = {"both": "윙크", "left": "왼눈 윙크", "right": "오른눈 윙크"}.get(self.wink_mode)
                clicks = [n for n, on in ((wink_name, self.wink_mode != "off"), ("응시", self.dwell_on)) if on]
                parts.append("클릭: " + "·".join(clicks) if clicks else "클릭 끔")
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
        """시선 커서가 메뉴·키보드보다 항상 위에 보이도록."""
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
    ap.add_argument("--check", action="store_true",
                    help="시작할 때 숫자 맞추기(정확도 확인)를 한 번 함 (새로 보정하면 자동으로 함)")
    ap.add_argument("--recalibrate", action="store_true",
                    help="저장된 캘리브레이션을 무시하고 처음부터 다시 함")
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
