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
import math
import signal
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

from PyQt5 import QtWidgets, QtCore, QtGui

from ui import theme
from vision.gaze_core import GazeSession, save_calibration, load_calibration
from calibration.adaptive import AdaptiveCalibrator, left_button_down
from control.clicker import (WinkDetector, DwellClicker, BlinkGesture, click_at, WINK_EYES, BLINK_COUNT,
                             BACK_COUNT)
from control.text_sender import send_back
from ui.status_window import StatusWindow
import json
from pathlib import Path

SETTINGS_FILE = Path(__file__).resolve().parent / "settings.json"
WINK_CYCLE = ["both", "left", "right", "off"]
from ui.gaze_widgets import GazeInteraction
from calibration.mole_calibration import MoleCalibrationWindow
from ui.seal_cursor import SealCursorOverlay
from ui.magnifier import Magnifier, MAX_LEVEL
from ui.menu_bar import MenuDock, MenuPanel, anchor_bottom_right
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
        self.zoom = 1
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
        self.last_wink_click_t = 0.0
        self.last_face_t = 0.0                           # 상태 확인 창: 마지막으로 얼굴이 잡힌 시각
        self.frame_times = deque(maxlen=30)              # 상태 확인 창: 카메라 fps 계산용
        self.calib_err = None                            # (학습 오차, 검증 오차) px
        self.wink = WinkDetector()
        self.dwell = DwellClicker()
        self.blink_gesture = BlinkGesture()   # 두 눈 연속 깜빡임: 3번 → 뒤로가기, 5번 → 일시정지/다시 시작
        self.synthetic_until = 0.0     # 우리가 만든 클릭 직후엔 '실제 마우스 클릭'으로 착각해 학습하지 않도록
        self.calib_win = None

        # 화면 부품들
        self.interaction = GazeInteraction()
        self.cursor = SealCursorOverlay()
        self.lens = Magnifier()
        self.dock = MenuDock()
        self.panel = MenuPanel()
        self.keyboard = OnScreenKeyboard()
        self.status_win = StatusWindow(self._status_state)

        # 시선 버튼 상태 → 물개 커서 (게이지, 하이라이트)
        self.interaction.progress_changed.connect(self._set_gauge)
        self.interaction.hover_changed.connect(self.cursor.set_highlight)
        self.interaction.dwell_clicked.connect(self._on_dwell_click)   # 응시 클릭 → 자동 보정 데이터

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
            from camera_worker import CameraWorker      # 마우스 모드에선 mediapipe를 불러오지 않음
            self.worker = CameraWorker(args.camera, args.hd)
            self.worker.frame_ready.connect(self._on_frame)
            self.worker.camera_error.connect(self._on_camera_error)
            self.worker.preview_ready.connect(self.status_win.set_frame)
            # 실제 마우스 클릭 감시 (다른 프로그램에서 누른 클릭까지) → 자동 보정 데이터
            self.mouse_poll = QtCore.QTimer(self)
            self.mouse_poll.timeout.connect(self._on_mouse_poll)
            self.mouse_poll.start(16)
        self.app.aboutToQuit.connect(self._shutdown)

    def start(self):
        if self.mouse_mode:
            self.mouse_timer.start(30)
            print("[마우스 테스트 모드] 마우스 위치를 시선 대신 사용합니다.")
        else:
            self.worker.start()
        saved = load_calibration() if (self.args.skip_calib and not self.mouse_mode) else None
        if saved is not None:
            n_on = len(saved["online_feats"])
            print(f"[캘리브레이션] 저장된 calibration.npz를 사용합니다. (자동 보정 샘플 {n_on}개 포함)")
            if "calib_err" in saved:
                self.calib_err = tuple(float(x) for x in saved["calib_err"])
            self._setup_model(saved["W"], saved["base"], saved["anchor_feats"], saved["anchor_labels"],
                              saved["anchor_weights"], saved["online_feats"], saved["online_labels"])
            self._enter_tracking()
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
            self._show_badge("back")            # 물개 커서(또는 돋보기) 위에 파란 ← 표시
        elif gesture == "pause":
            if self.paused:
                print("[깜빡임] 연속 깜빡임 → 다시 시작")
                self.resume()
            else:
                print("[깜빡임] 연속 깜빡임 → 일시정지")
                self.pause()
        if self.wink_mode != "off":
            fired = self.wink.update(opens, self.session.base, t, WINK_EYES[self.wink_mode])
            if fired and self._clicking_ready():
                self.last_wink_click_t = t
                self._gaze_click()              # 윙크 → 윙크 직전에 보던 곳(커서는 감는 동안 고정됨)을 클릭
        else:
            self.wink.update(opens, self.session.base, t, ())   # 꺼져 있어도 상태 확인 창의 눈 막대는 보여주기
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
        self.cursor.move_to(x, y, now)                  # 물개 커서 + 궤적
        if self.zoom > 1 and not self.paused:
            self.lens.follow(x, y)                      # 돋보기
        self.interaction.update_gaze(x, y, now)         # 응시 클릭 + 하이라이트
        if self.dwell_on and self._clicking_ready():   # 응시 클릭: 데모 버튼·메뉴 위가 아닐 때만 (버튼은 자기 방식대로 눌림)
            if self.interaction.over_button() or self._over_own_window(x, y):
                self.dwell.reset()
            else:
                frac, pt = self.dwell.update(x, y, now)
                self._set_gauge(frac)
                if pt is not None:
                    self._gaze_click(pt)

    # ── 시선 클릭 (윙크 / 응시) ─────────────────────────────────────
    def _clicking_ready(self):
        return (not self.mouse_mode and not self.calibrating and not self.paused
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

    def _set_gauge(self, frac):
        """응시 게이지: 물개 커서 둘레 + (돋보기를 켰다면) 돋보기 십자 둘레."""
        self.cursor.set_gauge(frac)
        self.lens.set_gauge(frac)

    def _show_check(self):
        self._show_badge("check")

    def _show_badge(self, kind):
        self.cursor.show_badge(kind)
        self.lens.show_badge(kind)

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
        }

    def _load_settings(self):
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_settings(self):
        try:
            SETTINGS_FILE.write_text(json.dumps({"wink_mode": self.wink_mode, "dwell_on": self.dwell_on}),
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
              "keyboard": self.keyboard_open, "wink": self.wink_mode, "dwell": self.dwell_on,
              "status": self.status_win.isVisible()}
        self.panel.update_state(st)
        self.lens.set_level(self.zoom)
        zoomed = self.zoom > 1 and not self.paused and not self.calibrating
        self.lens.setVisible(zoomed)
        self.cursor.set_hidden(zoomed)          # 돋보기 동안엔 물개 숨김 → 돋보기 속을 가리지 않음, 녹화도 정상

        if self.paused:
            text = f"일시정지 중 · 자물쇠를 3초 보거나 눈을 {BLINK_COUNT}번 빠르게 깜빡이면 다시 켜져요"
        else:
            parts = ["활성", f"배율 ×{self.zoom}", "잔상 ON" if self.trail_on else "잔상 OFF"]
            if self.adapt is not None and self.adapt.count:
                parts.append(f"자동 보정 {self.adapt.count}")
            if self.keyboard_open:
                parts.append("키보드")
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
