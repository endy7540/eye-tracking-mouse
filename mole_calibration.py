# -*- coding: utf-8 -*-
"""
mole_calibration.py — "두더지 잡기" 캘리브레이션 화면

원본 gaze_tracker.py의 calibrate()와 똑같이 3단계로 진행합니다. 바뀐 건 화면뿐입니다.
    1) 격자 9점   [원본 collect_point()]         — 두더지를 2초 동안 흔들림 없이 보면 확정
    2) 자세 변화 3점 [원본 run_head_pose_variation()] — 두더지를 보며 고개를 움직이는 동안 데이터 수집
    3) 정확도 검증 2점 [원본 run_validation()]     — 학습에 안 쓴 새 위치로 실제 오차(px) 측정
점 대신 두더지(assets/mole.png)가 나오고, 한 마리가 끝날 때마다 뿅망치(assets/hammer.png)가
내려와 두더지를 때립니다(맞는 순간 assets/mole_hit.png 표정으로 바뀜). 3단계 모두 뿅망치로 끝납니다.

★ 격자 단계는 왜 "화면 좌표"가 아니라 "눈동자 값"으로 판정하나? ★
캘리브레이션이 끝나기 전에는 아직 W(특징값→화면좌표 변환식)가 없어서 "화면 어디를 보고 있는지"를
모릅니다. 그래서 원본처럼 "눈동자 좌우/상하 값(hx, vy)이 2초 동안 거의 안 흔들리는지"만 봅니다.

진행 방식
    - 실제 시선 데이터는 on_feature(feat, opens, 시각)로 들어옵니다 (main.py가 카메라 신호를 연결).
    - 화면 갱신과 시간 기반 판정(자세변화/검증 시간 종료, 애니메이션)은 _tick()이 60fps로 처리합니다.
    - 단계 사이에는 안내 화면(배너)이 잠깐 나왔다가 자동으로 넘어갑니다 (아무 키나 누르면 바로 넘어감).
    - 끝나면 결과 화면이 잠깐 나온 뒤 on_finished(W, base, 학습오차, 검증오차)를 호출하고 닫힙니다.
    - ESC를 누르면 on_cancelled()를 호출하고 닫힙니다.
    - mouse_mode=True(테스트용)이면 카메라 대신 마우스를 두더지 위에 2초 올려두면 확정됩니다.
"""
import math
import time
from collections import deque

import numpy as np
from PyQt5 import QtWidgets, QtCore, QtGui

import theme
from gaze_core import (BLINK_THRESHOLD, STABLE_SEC, STABLE_WINDOW_SEC, STABLE_MIN_SAMPLES,
                       STABLE_HX_TOL, STABLE_VY_TOL, MAX_WAIT_SEC, POSE_SEC, POSE_SETTLE_SEC,
                       VALID_SETTLE_SEC, VALID_COLLECT_SEC, grid_targets, pose_targets,
                       validation_targets, fit, predict_norm)

VALIDATE_SEC = VALID_SETTLE_SEC + VALID_COLLECT_SEC   # 검증 두더지 한 마리당 시간 (원본과 동일)
WHACK_ANIM_SEC = 0.65        # 뿅망치 애니메이션 전체 길이
HIT_AT = 0.45                # 애니메이션 중 이 비율 지점에서 망치가 두더지에 닿음
SUMMARY_SEC = 3.5            # 결과 화면을 보여주는 시간 (아무 키나 누르면 바로 넘어감)
MOUSE_RADIUS_PX = 80         # [마우스 테스트 모드] 두더지 중심에서 이 반경 안이면 '보고 있다'로 판단
FACE_LOST_WARN_SEC = 1.0     # 얼굴이 이 시간 이상 안 보이면 화면에 안내 문구 표시

# 두더지 이미지(800x800) 안에서 코의 위치 비율 — 이 지점이 캘리브레이션 목표 지점에 오도록 그림
MOLE_NOSE_Y = 0.52
MOLE_BOTTOM_Y = 0.92         # 흙구멍 아래쪽 (찌그러짐/기울임의 기준점)
HAMMER_PIVOT_Y = 0.922       # 뿅망치 이미지에서 손잡이 끝(회전 기준점)의 세로 위치 비율


class GridStabilityTracker:
    """[원본: collect_point()] 실제 눈동자 값(hx, vy)이 STABLE_SEC 이상 흔들리지 않는지 매 프레임 판정.
    확정되는 순간 최근 안정 구간의 중앙값(median)을 대표 샘플로 고정한다."""

    def __init__(self, now):
        self.recent = deque()          # (t, feat, opens) — 최근 STABLE_WINDOW_SEC 동안의 유효 프레임만 유지
        self.stable_since = None
        self.confirmed = False
        self.result = None             # (median_feat, median_opens)
        self.t_start = now

    def update(self, feat, opens, t):
        if self.confirmed:
            return
        valid = feat is not None and opens is not None and opens.min() > BLINK_THRESHOLD
        if valid:
            self.recent.append((t, feat, opens))
        while self.recent and t - self.recent[0][0] > STABLE_WINDOW_SEC:
            self.recent.popleft()

        stable_now = False
        if valid and len(self.recent) >= STABLE_MIN_SAMPLES:
            hxs = [r[1][0] for r in self.recent]
            vys = [r[1][1] for r in self.recent]
            stable_now = (max(hxs) - min(hxs) <= STABLE_HX_TOL) and (max(vys) - min(vys) <= STABLE_VY_TOL)

        if stable_now:
            if self.stable_since is None:
                self.stable_since = t
        else:
            self.stable_since = None

        elapsed_stable = (t - self.stable_since) if self.stable_since is not None else 0.0
        timed_out = (t - self.t_start) >= MAX_WAIT_SEC and len(self.recent) > 0   # 너무 오래 걸리면 강제 진행
        if elapsed_stable >= STABLE_SEC or timed_out:
            feats_arr = np.array([r[1] for r in self.recent])
            opens_arr = np.array([r[2] for r in self.recent])
            self.result = (np.median(feats_arr, axis=0), np.median(opens_arr, axis=0))
            self.confirmed = True

    def progress(self, now):
        if self.confirmed:
            return 1.0
        if self.stable_since is None:
            return 0.0
        return min((now - self.stable_since) / STABLE_SEC, 1.0)


class MouseStabilityTracker:
    """[마우스 테스트 모드 전용] 마우스가 두더지 근처에 STABLE_SEC 동안 머물면 확정."""

    def __init__(self, center):
        self.center = center
        self.stable_since = None
        self.confirmed = False

    def update(self, pos, t):
        if self.confirmed:
            return
        d = math.hypot(pos.x() - self.center[0], pos.y() - self.center[1])
        if d <= MOUSE_RADIUS_PX:
            if self.stable_since is None:
                self.stable_since = t
            if t - self.stable_since >= STABLE_SEC:
                self.confirmed = True
        else:
            self.stable_since = None

    def progress(self, now):
        if self.confirmed:
            return 1.0
        if self.stable_since is None:
            return 0.0
        return min((now - self.stable_since) / STABLE_SEC, 1.0)


class MoleCalibrationWindow(QtWidgets.QWidget):
    def __init__(self, mouse_mode=False, on_finished=None, on_cancelled=None):
        super().__init__()
        self.mouse_mode = mouse_mode
        self.on_finished = on_finished
        self.on_cancelled = on_cancelled
        self._done = False             # on_finished / on_cancelled가 두 번 불리지 않도록

        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setGeometry(QtWidgets.QApplication.primaryScreen().geometry())

        # 두더지 크기: 화면 짧은 변의 17% (너무 작거나 크지 않게 140~200px)
        S = int(max(140, min(200, min(self.width(), self.height()) * 0.17)))
        self.S = S
        smooth = QtCore.Qt.SmoothTransformation
        self.mole_pix = theme.pixmap("mole.png").scaled(S, S, QtCore.Qt.KeepAspectRatio, smooth)
        self.hit_pix = theme.pixmap("mole_hit.png").scaled(S, S, QtCore.Qt.KeepAspectRatio, smooth)
        self.hammer_pix = theme.pixmap("hammer.png").scaledToHeight(int(S * 1.1), smooth)

        self.steps = self._build_steps()
        self.index = 0
        self.step_t0 = time.time()
        self.anim_t0 = None            # 뿅망치 애니메이션 시작 시각 (None이면 재생 중 아님)
        self.showing_summary = False
        self.summary_t0 = None
        self.last_face_t = time.time()

        # 실제 캘리브레이션 데이터 (원본 calibrate()의 feats, labels, opens_all)
        self.feats, self.labels, self.opens_all = [], [], []
        self.tracker = None
        self.validate_samples = []
        self.val_errors = []
        self.W = self.base = self.train_err = None

        self._start_step()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def showEvent(self, event):
        super().showEvent(event)
        self.activateWindow()
        self.setFocus()                # ESC / 아무 키 입력을 받기 위해

    # ── 진행 순서 만들기 [원본 calibrate()의 순서] ─────────────────────
    def _build_steps(self):
        steps = [{"kind": "banner", "title": "두더지 잡기 캘리브레이션!",
                  "sub": f"화면에 나오는 두더지를 {STABLE_SEC:.0f}초 동안 가만히 바라봐 주세요", "dur": 3.0}]
        grid = [{"kind": "grid", "tx": x, "ty": y} for x, y in grid_targets()]
        pose = [{"kind": "pose", "tx": x, "ty": y} for x, y in pose_targets()]
        valid = [{"kind": "validate", "tx": x, "ty": y} for x, y in validation_targets()]
        for group in (grid, pose, valid):
            for i, s in enumerate(group, 1):
                s["n"], s["total"] = i, len(group)
        steps += grid
        steps.append({"kind": "banner", "title": "2단계 · 자세 변화",
                      "sub": "두더지를 계속 보면서 고개를 천천히 움직여 주세요", "dur": 2.5})
        steps += pose
        steps.append({"kind": "banner", "title": "3단계 · 정확도 확인",
                      "sub": "새로 나오는 두더지를 바라봐 주세요", "dur": 2.0})
        steps += valid
        return steps

    def _current(self):
        return self.steps[self.index]

    def _target_px(self, s):
        return s["tx"] * self.width(), s["ty"] * self.height()

    def _start_step(self):
        s = self._current()
        now = time.time()
        self.step_t0 = now
        self.anim_t0 = None
        self.tracker = None
        self.validate_samples = []
        if s["kind"] == "grid":
            self.tracker = (MouseStabilityTracker(self._target_px(s)) if self.mouse_mode
                            else GridStabilityTracker(now))
        # [원본 calibrate()] 격자+자세변화가 끝나고 검증이 시작되는 순간 W를 학습
        if s["kind"] == "validate" and s["n"] == 1 and not self.mouse_mode:
            self._fit_model()

    def _fit_model(self):
        if not self.feats:
            return
        try:
            self.W = fit(self.feats, self.labels)
            self.base = np.median(np.array(self.opens_all), axis=0)    # [왼눈, 오른눈] 평소 개폐 비율
            pred = np.array([predict_norm(self.W, f) for f in self.feats]) * [self.width(), self.height()]
            true = np.array(self.labels) * [self.width(), self.height()]
            self.train_err = float(np.linalg.norm(pred - true, axis=1).mean())
        except Exception as e:
            print("[캘리브레이션] 학습 실패:", e)
            self.W = self.base = None

    def _finish_validate_point(self, s):
        """[원본: run_validation()] 이 두더지를 보는 동안 모은 샘플로 예측 위치와 실제 위치의 거리(px) 계산."""
        if self.W is not None and self.validate_samples:
            pred = np.array([predict_norm(self.W, f) for f in self.validate_samples]).mean(axis=0)
            pred_px = pred * [self.width(), self.height()]
            true_px = np.array(self._target_px(s))
            self.val_errors.append(float(np.linalg.norm(pred_px - true_px)))

    def _start_whack(self):
        self.anim_t0 = time.time()

    def _advance(self):
        self.index += 1
        if self.index >= len(self.steps):
            self.showing_summary = True
            self.summary_t0 = time.time()
            return
        self._start_step()

    # ── 실제 시선 데이터 입구 (main.py가 카메라 신호를 연결) ────────────
    def on_feature(self, feat, opens, t):
        if feat is not None:
            self.last_face_t = t
        if self.showing_summary or self.anim_t0 is not None or self.mouse_mode:
            return
        s = self._current()
        valid = feat is not None and opens is not None and opens.min() > BLINK_THRESHOLD

        if s["kind"] == "grid":
            self.tracker.update(feat, opens, t)
            if self.tracker.confirmed:
                f_med, o_med = self.tracker.result
                self.feats.append(f_med)
                self.labels.append((s["tx"], s["ty"]))
                self.opens_all.append(o_med)
                self._start_whack()
        elif s["kind"] == "pose":
            if valid and (t - self.step_t0) > POSE_SETTLE_SEC:
                self.feats.append(feat)
                self.labels.append((s["tx"], s["ty"]))
                self.opens_all.append(opens)
        elif s["kind"] == "validate":
            elapsed = t - self.step_t0
            if valid and VALID_SETTLE_SEC <= elapsed < VALIDATE_SEC:
                self.validate_samples.append(feat)

    # ── 시간 진행 (60fps) ─────────────────────────────────────────
    def _tick(self):
        now = time.time()
        if self.showing_summary:
            if now - self.summary_t0 >= SUMMARY_SEC:
                self._finish()
            self.update()
            return

        s = self._current()
        if self.anim_t0 is not None:                       # 뿅망치 애니메이션 중
            if now - self.anim_t0 >= WHACK_ANIM_SEC:
                self._advance()
            self.update()
            return

        if s["kind"] == "banner":
            if now - self.step_t0 >= s["dur"]:
                self._advance()
        elif s["kind"] == "grid":
            if self.mouse_mode:
                self.tracker.update(self.mapFromGlobal(QtGui.QCursor.pos()), now)
                if self.tracker.confirmed:
                    self._start_whack()
        elif s["kind"] == "pose":
            if now - self.step_t0 >= POSE_SEC:
                self._start_whack()
        elif s["kind"] == "validate":
            if now - self.step_t0 >= VALIDATE_SEC:
                self._finish_validate_point(s)
                self._start_whack()
        self.update()

    def _finish(self):
        if self._done:
            return
        self._done = True
        self.timer.stop()
        val_err = float(np.mean(self.val_errors)) if self.val_errors else None
        if self.on_finished:
            self.on_finished(self.W, self.base, self.train_err, val_err)
        self.close()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            if not self._done:
                self._done = True
                self.timer.stop()
                if self.on_cancelled:
                    self.on_cancelled()
                self.close()
            return
        if self.showing_summary:                           # 결과 화면: 아무 키나 → 바로 시작
            self._finish()
        elif self._current()["kind"] == "banner":          # 안내 화면: 아무 키나 → 바로 넘어감
            self._advance()

    # ── 그리기 ───────────────────────────────────────────────────
    def paintEvent(self, event):
        now = time.time()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), theme.BG)

        if self.showing_summary:
            self._paint_summary(p)
            return
        s = self._current()
        if s["kind"] == "banner":
            self._paint_banner(p, s, now)
            return

        cx, cy = self._target_px(s)
        playing = self.anim_t0 is not None
        t = (now - self.anim_t0) / WHACK_ANIM_SEC if playing else 0.0
        impact = playing and t >= HIT_AT
        after = min((t - HIT_AT) / (1 - HIT_AT), 1.0) if impact else 0.0

        tilt = 0.0
        if s["kind"] == "pose" and not playing:            # 자세 변화: 고개를 갸웃거리는 두더지
            tilt = 9 * math.sin((now - self.step_t0) * 3.2)
        squash = 1.0 - 0.22 * math.sin(after * math.pi) if impact else 1.0
        self._draw_mole(p, self.hit_pix if impact else self.mole_pix, cx, cy, tilt, squash)

        if playing:
            self._draw_hammer(p, cx, cy, t)
            if impact:
                self._draw_star(p, cx - 0.28 * self.S, cy - 0.45 * self.S, after)
        else:
            self._draw_progress(p, s, cx, cy, now)
        self._draw_caption(p, s, now)

    def _draw_mole(self, p, pix, cx, cy, tilt, squash):
        S = self.S
        top = cy - MOLE_NOSE_Y * S                        # 코가 목표 지점에 오도록
        p.save()
        p.translate(cx, top + MOLE_BOTTOM_Y * S)           # 흙구멍 아래쪽을 기준으로 기울이고/찌그러뜨림
        p.rotate(tilt)
        p.scale(1.0, squash)
        p.drawPixmap(QtCore.QPointF(-S / 2, -MOLE_BOTTOM_Y * S), pix)
        p.restore()

    def _draw_progress(self, p, s, cx, cy, now):
        """두더지 아래쪽 진행 막대. 격자=빨강→노랑(진행)→초록, 자세변화=노랑, 검증=초록."""
        if s["kind"] == "grid":
            frac = self.tracker.progress(now) if self.tracker else 0.0
            fill = theme.GREEN if frac >= 1.0 else theme.YELLOW
            edge = theme.RED if frac == 0.0 else fill
        elif s["kind"] == "pose":
            frac, fill, edge = min((now - self.step_t0) / POSE_SEC, 1.0), theme.YELLOW, theme.YELLOW
        else:
            frac, fill, edge = min((now - self.step_t0) / VALIDATE_SEC, 1.0), theme.GREEN, theme.GREEN

        w, h = 0.8 * self.S, 16
        y = cy + (1 - MOLE_NOSE_Y) * self.S + 4
        if y + h > self.height() - 6:                     # 화면 아래쪽이면 두더지 머리 위에 표시
            y = cy - MOLE_NOSE_Y * self.S + 0.1 * self.S - h - 8
        bar = QtCore.QRectF(cx - w / 2, y, w, h)
        p.setPen(QtGui.QPen(edge, 3))
        p.setBrush(QtGui.QColor(255, 255, 255, 200))
        p.drawRoundedRect(bar, h / 2, h / 2)
        if frac > 0:
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(QtCore.QRectF(bar.left() + 3, bar.top() + 3, (w - 6) * frac, h - 6),
                              (h - 6) / 2, (h - 6) / 2)

    def _draw_hammer(self, p, cx, cy, t):
        """뿅망치: 오른쪽 위로 들려 있다가(+28°) 왼쪽 아래로 내려찍음(-50°), 닿은 뒤 살짝 튕김."""
        if t < HIT_AT:
            s = t / HIT_AT
            angle = 28 - 78 * s * s                       # 점점 빨라지며 내려옴
        else:
            angle = -50 + 8 * math.sin(min((t - HIT_AT) / (1 - HIT_AT), 1.0) * math.pi)
        pw, ph = self.hammer_pix.width(), self.hammer_pix.height()
        p.save()
        p.translate(cx + 0.60 * self.S, cy + 0.16 * self.S)   # 손잡이 끝(회전 기준점)의 화면 위치
        p.rotate(angle)
        p.drawPixmap(QtCore.QPointF(-pw / 2, -HAMMER_PIVOT_Y * ph), self.hammer_pix)
        p.restore()

    def _draw_star(self, p, x, y, frac):
        """맞는 순간 튀어나오는 노란 별."""
        scale = math.sin(min(frac, 1.0) * math.pi) * 1.15
        if scale <= 0.01:
            return
        r_out, r_in = 0.14 * self.S, 0.06 * self.S
        pts = []
        for i in range(16):
            ang = math.radians(i * 22.5 - 90)
            r = r_out if i % 2 == 0 else r_in
            pts.append(QtCore.QPointF(r * math.cos(ang), r * math.sin(ang)))
        p.save()
        p.translate(x, y)
        p.scale(scale, scale)
        p.setPen(QtGui.QPen(QtGui.QColor(75, 50, 38), 3))
        p.setBrush(QtGui.QColor(255, 205, 60))
        p.drawPolygon(QtGui.QPolygonF(pts))
        p.restore()

    def _caption_rect(self, s):
        """안내 문구 위치: 두더지들과 겹치지 않는 줄 (격자/자세변화 = 위에서 28%, 검증 = 위에서 86%)."""
        y = self.height() * (0.86 if s["kind"] == "validate" else 0.28)
        return QtCore.QRectF(0, y - 30, self.width(), 60)

    def _draw_caption(self, p, s, now):
        n, total = s["n"], s["total"]
        text = {
            "grid": f"두더지를 {STABLE_SEC:.0f}초동안 안정적으로 봐주세요  ({n}/{total})",
            "pose": f"두더지를 계속 보면서 고개를 움직여 주세요  (자세 변화 {n}/{total})",
            "validate": f"두더지를 바라봐 주세요  (정확도 검증 {n}/{total})",
        }[s["kind"]]
        rect = self._caption_rect(s)
        p.setPen(theme.INK)
        p.setFont(theme.title_font(34))
        p.drawText(rect, QtCore.Qt.AlignCenter, text)

        if not self.mouse_mode and now - self.last_face_t > FACE_LOST_WARN_SEC:
            p.setPen(theme.RED)
            p.setFont(theme.ui_font(22))
            p.drawText(rect.translated(0, 48), QtCore.Qt.AlignCenter,
                       "얼굴이 안 보여요 — 카메라 정면에 앉아 주세요")
        p.setPen(theme.INK_SOFT)
        p.setFont(theme.ui_font(16, bold=False))
        p.drawText(self.rect().adjusted(0, 0, -24, -16), QtCore.Qt.AlignRight | QtCore.Qt.AlignBottom,
                   "ESC: 취소" + ("   [마우스 테스트 모드]" if self.mouse_mode else ""))

    def _paint_banner(self, p, s, now):
        cx, cy = self.width() / 2, self.height() / 2
        big = self.mole_pix.scaled(int(self.S * 1.4), int(self.S * 1.4), QtCore.Qt.KeepAspectRatio,
                                   QtCore.Qt.SmoothTransformation)
        p.drawPixmap(QtCore.QPointF(cx - big.width() / 2, cy - big.height() - 40), big)
        p.setPen(theme.INK)
        p.setFont(theme.title_font(64))
        p.drawText(QtCore.QRectF(0, cy - 30, self.width(), 90), QtCore.Qt.AlignCenter, s["title"])
        p.setFont(theme.ui_font(28))
        p.drawText(QtCore.QRectF(0, cy + 60, self.width(), 50), QtCore.Qt.AlignCenter, s["sub"])
        left = max(0, math.ceil(s["dur"] - (now - self.step_t0)))
        p.setPen(theme.INK_SOFT)
        p.setFont(theme.ui_font(20, bold=False))
        p.drawText(QtCore.QRectF(0, cy + 120, self.width(), 40), QtCore.Qt.AlignCenter,
                   f"{left}초 뒤에 시작해요  ·  아무 키나 누르면 바로 시작  ·  ESC: 취소")

    def _paint_summary(self, p):
        cx, cy = self.width() / 2, self.height() / 2
        big = self.hit_pix.scaled(int(self.S * 1.2), int(self.S * 1.2), QtCore.Qt.KeepAspectRatio,
                                  QtCore.Qt.SmoothTransformation)
        p.drawPixmap(QtCore.QPointF(cx - big.width() / 2, cy - big.height() - 70), big)
        p.setPen(theme.GREEN)
        p.setFont(theme.title_font(60))
        p.drawText(QtCore.QRectF(0, cy - 60, self.width(), 80), QtCore.Qt.AlignCenter, "캘리브레이션 완료!")
        p.setPen(theme.INK)
        p.setFont(theme.ui_font(24))
        if self.mouse_mode:
            lines = ["마우스 테스트 모드라 오차 계산은 건너뛰었어요"]
        else:
            lines = [f"학습 데이터 평균 오차: 약 {self.train_err:.0f}px" if self.train_err is not None
                     else "학습 데이터가 부족해요"]
            if self.val_errors:
                lines.append(f"검증(홀드아웃) 평균 오차: 약 {np.mean(self.val_errors):.0f}px")
        y = cy + 30
        for line in lines:
            p.drawText(QtCore.QRectF(0, y, self.width(), 40), QtCore.Qt.AlignCenter, line)
            y += 42
        p.setPen(theme.INK_SOFT)
        p.setFont(theme.ui_font(20, bold=False))
        p.drawText(QtCore.QRectF(0, y + 20, self.width(), 40), QtCore.Qt.AlignCenter,
                   "잠시 후 시작해요  ·  아무 키나 누르면 바로 시작")
