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
import random
import time
from collections import Counter, deque

import numpy as np
from PyQt5 import QtWidgets, QtCore, QtGui

import theme
from gaze_core import (BLINK_THRESHOLD, MARGIN, GRID_ROWS, STABLE_SEC, STABLE_WINDOW_SEC, STABLE_MIN_SAMPLES,
                       STABLE_HX_TOL, STABLE_VY_TOL, MAX_WAIT_SEC, POSE_SEC, POSE_SETTLE_SEC,
                       VALID_SETTLE_SEC, VALID_COLLECT_SEC, PURSUIT_SEC, PURSUIT_SETTLE_SEC,
                       PURSUIT_LAG_SEC, PURSUIT_SEGMENT_SEC, grid_targets, pose_targets,
                       validation_targets, pursuit_pos, fit, predict_norm)

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

# [추가] 진짜 두더지잡기처럼 — 구멍에서 쏙 올라오고, 따라 보기 땐 땅을 파고 숨어서 이동
POP_SEC = 0.25               # 두더지가 구멍에서 올라오는 시간 (격자/자세/검증)
PURSUIT_DIG_SEC = 0.9        # 따라 보기 시작: 두더지가 땅을 파고 들어가는 시간 (이 동안은 데이터 안 모음)
PURSUIT_POP_SEC = 0.35       # 따라 보기 끝: 이동을 마친 두더지가 다시 튀어나오는 시간
HOLE_MID_Y = 0.79            # 두더지 이미지에서 구멍 입구(어두운 부분) 가운데의 세로 위치 비율
RISE_DEPTH = 0.72            # 완전히 숨었을 때 두더지를 아래로 내리는 거리 (두더지 크기 대비)
DIRT = QtGui.QColor(160, 110, 72)        # 흙 색
DIRT_DARK = QtGui.QColor(92, 60, 38)     # 흙 테두리
HOLE_DARK = QtGui.QColor(66, 42, 34)     # 구멍 안쪽
HOLE_RIM = QtGui.QColor(122, 84, 62)     # 구멍 테두리 (흙더미보다 진하게 — 모래 바닥에서 잘 보이게)
HOLE_EDGE = QtGui.QColor(70, 45, 35)     # 구멍 바깥 선
RING_R = 0.5                             # 진행 고리 반지름 (두더지 크기 대비)

# [추가] 배경: 모래색 땅 + 흙 자국(짧은 줄무늬) + 격자 자리마다 미리 파여 있는 구멍들 (진짜 두더지잡기 판처럼)
SAND = QtGui.QColor(238, 226, 200)       # 땅 색
SAND_MARK = QtGui.QColor(221, 205, 172)  # 흙 자국 색
MARK_DENSITY = 1 / 9000                  # 화면 넓이(px²) 대비 흙 자국 개수


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
        self.bg_pix = None             # 배경 그림 (처음 그릴 때 한 번 만들어 두고 계속 재사용)

        # 실제 캘리브레이션 데이터 (원본 calibrate()의 feats, labels, opens_all)
        self.feats, self.labels, self.opens_all = [], [], []
        self.groups = []               # 각 샘플이 몇 번째 두더지에서 나왔는지 (가중치 계산용)
        self.tracker = None
        self.validate_samples = []
        self.val_errors = []
        self.W = self.base = self.train_err = None
        self.fit_weights = None        # 학습에 쓴 샘플 가중치 — 자동 보정이 두더지 데이터를 기준점으로 다시 쓸 때 필요

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
        # 진짜 두더지잡기처럼 어디서 튀어나올지 모르게 순서를 섞음 (위치 자체는 그대로라 학습에는 영향 없음)
        grid_pts = grid_targets()
        random.shuffle(grid_pts)
        grid = [{"kind": "grid", "tx": x, "ty": y} for x, y in grid_pts]
        pursuit = [{"kind": "pursuit", "tx": 0.5, "ty": 0.5}]
        pose = [{"kind": "pose", "tx": x, "ty": y} for x, y in pose_targets()]
        valid_pts = validation_targets()
        random.shuffle(valid_pts)
        valid = [{"kind": "validate", "tx": x, "ty": y} for x, y in valid_pts]
        for group in (grid, pursuit, pose, valid):
            for i, s in enumerate(group, 1):
                s["n"], s["total"] = i, len(group)
        steps += grid
        steps.append({"kind": "banner", "title": "2단계 · 따라 보기",
                      "sub": "두더지가 땅을 파고 숨어서 움직여요 — 고개는 가만히, 흙더미를 눈으로만 따라가 주세요",
                      "dur": 3.0})
        steps += pursuit
        steps.append({"kind": "banner", "title": "3단계 · 자세 변화",
                      "sub": "두더지를 계속 보면서 고개를 천천히 움직여 주세요", "dur": 2.5})
        steps += pose
        steps.append({"kind": "banner", "title": "4단계 · 정확도 확인",
                      "sub": "새로 나오는 두더지를 바라봐 주세요", "dur": 2.0})
        steps += valid
        return steps

    def _current(self):
        return self.steps[self.index]

    def _target_px(self, s):
        if s["kind"] == "pursuit":                         # 따라 보기: 시간에 따라 움직이는 위치
            tx, ty = pursuit_pos(time.time() - self.step_t0 - PURSUIT_DIG_SEC)   # 땅 파는 동안은 출발점
            return tx * self.width(), ty * self.height()
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
            # 두더지 한 마리당 가중치 합이 같도록: 격자 점(샘플 1개)과 자세변화 점(샘플 수십 개)의 균형 맞춤
            counts = Counter(self.groups)
            weights = np.array([1.0 / counts[g] for g in self.groups])
            self.W = fit(self.feats, self.labels, weights=weights)
            self.fit_weights = weights
            self.base = np.median(np.array(self.opens_all), axis=0)    # [왼눈, 오른눈] 평소 개폐 비율
            pred = np.array([predict_norm(self.W, f) for f in self.feats]) * [self.width(), self.height()]
            true = np.array(self.labels) * [self.width(), self.height()]
            self.train_err = float(np.average(np.linalg.norm(pred - true, axis=1), weights=weights))
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
                self.groups.append(self.index)
                self._start_whack()
        elif s["kind"] == "pursuit":
            # 지연 보정: 이 프레임의 눈은 PURSUIT_LAG_SEC 전의 두더지 위치를 보고 있다고 봄
            seen_at = (t - self.step_t0) - PURSUIT_DIG_SEC - PURSUIT_LAG_SEC
            if valid and PURSUIT_SETTLE_SEC <= seen_at <= PURSUIT_SEC:
                self.feats.append(feat)
                self.labels.append(pursuit_pos(seen_at))
                self.opens_all.append(opens)
                self.groups.append(f"{self.index}-{int(seen_at // PURSUIT_SEGMENT_SEC)}")
        elif s["kind"] == "pose":
            if valid and (t - self.step_t0) > POSE_SETTLE_SEC:
                self.feats.append(feat)
                self.labels.append((s["tx"], s["ty"]))
                self.opens_all.append(opens)
                self.groups.append(self.index)
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
        elif s["kind"] == "pursuit":
            if now - self.step_t0 >= PURSUIT_DIG_SEC + PURSUIT_SEC + PURSUIT_POP_SEC:
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
        if self.bg_pix is None or self.bg_pix.size() != self.size():
            self.bg_pix = self._make_background()
        p.drawPixmap(0, 0, self.bg_pix)

        if self.showing_summary:
            self._paint_summary(p)
            return
        s = self._current()
        if s["kind"] == "banner":
            self._paint_banner(p, s, now)
            return

        cx, cy = self._target_px(s)
        playing = self.anim_t0 is not None
        if s["kind"] == "pursuit" and not playing:         # 따라 보기: 땅 파기 → 흙더미 이동 → 튀어나오기
            self._paint_pursuit(p, now)
            self._draw_caption(p, s, now)
            return
        t = (now - self.anim_t0) / WHACK_ANIM_SEC if playing else 0.0
        impact = playing and t >= HIT_AT
        after = min((t - HIT_AT) / (1 - HIT_AT), 1.0) if impact else 0.0

        tilt = 0.0
        if s["kind"] == "pose" and not playing:            # 자세 변화: 고개를 갸웃거리는 두더지
            tilt = 9 * math.sin((now - self.step_t0) * 3.2)
        squash = 1.0 - 0.22 * math.sin(after * math.pi) if impact else 1.0
        k = min((now - self.step_t0) / POP_SEC, 1.0)
        rise = 1.0 if playing else 1 - (1 - k) ** 3        # 구멍에서 쏙 (처음엔 빠르게, 끝에서 살짝 느리게)
        self._draw_mole(p, self.hit_pix if impact else self.mole_pix, cx, cy, tilt, squash, rise)

        if playing:
            self._draw_hammer(p, cx, cy, t)
            if impact:
                self._draw_star(p, cx - 0.28 * self.S, cy - 0.45 * self.S, after)
        else:
            self._draw_progress(p, s, cx, cy, now)
        self._draw_caption(p, s, now)

    def _draw_mole(self, p, pix, cx, cy, tilt, squash, rise=1.0):
        """rise: 1 = 완전히 나온 두더지, 0 = 구멍 속에 완전히 숨음 (그 사이는 머리만 빼꼼)."""
        S = self.S
        top = cy - MOLE_NOSE_Y * S                        # 코가 목표 지점에 오도록
        p.save()
        p.translate(cx, top + MOLE_BOTTOM_Y * S)           # 흙구멍 아래쪽을 기준으로 기울이고/찌그러뜨림
        if rise < 1.0:
            self._draw_hole(p)
            # 구멍 입구보다 아래는 안 보이게 자름. 거의 다 나오면 자르는 선도 내려가서 구멍 테두리까지 자연스럽게 보임
            clip_bottom = (HOLE_MID_Y + (1.0 - HOLE_MID_Y) * rise ** 2 - MOLE_BOTTOM_Y) * S
            p.setClipRect(QtCore.QRectF(-S, -2 * S, 2 * S, 2 * S + clip_bottom))
            p.translate(0, (1.0 - rise) * RISE_DEPTH * S)
        p.rotate(tilt)
        p.scale(1.0, squash)
        p.drawPixmap(QtCore.QPointF(-S / 2, -MOLE_BOTTOM_Y * S), pix)
        p.restore()

    def _make_background(self):
        """모래색 땅 + 흙 자국 + 격자 자리의 구멍들을 한 장의 그림으로 미리 그려 둠 (60fps 다시 그리기 부담 줄이기).
        흙 자국은 실행할 때마다 같은 모양이 되도록 고정된 난수로 뿌림."""
        w, h = self.width(), self.height()
        pix = QtGui.QPixmap(w, h)
        pix.fill(SAND)
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        rng = random.Random(7)
        pen = QtGui.QPen(SAND_MARK, 3.5)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen)
        for _ in range(int(w * h * MARK_DENSITY)):
            x, y = rng.uniform(0, w), rng.uniform(0, h)
            length = rng.uniform(10, 34)
            ang = math.radians(rng.uniform(-14, 14))
            dx, dy = math.cos(ang) * length / 2, math.sin(ang) * length / 2
            p.drawLine(QtCore.QPointF(x - dx, y - dy), QtCore.QPointF(x + dx, y + dy))
        for tx, ty in grid_targets():               # 두더지가 튀어나올 수 있는 구멍들
            p.save()
            cx, cy = tx * w, ty * h
            p.translate(cx, cy - MOLE_NOSE_Y * self.S + MOLE_BOTTOM_Y * self.S)   # _draw_mole과 같은 기준점
            self._draw_hole(p)
            p.restore()
        p.end()
        return pix

    def _draw_hole(self, p):
        """두더지가 들어가고 나오는 흙구멍 (_draw_mole 안에서, 구멍 아래쪽 기준 좌표로 그림)."""
        S = self.S
        y = (HOLE_MID_Y + 0.02 - MOLE_BOTTOM_Y) * S
        p.setPen(QtGui.QPen(HOLE_EDGE, 3))
        p.setBrush(HOLE_RIM)
        p.drawEllipse(QtCore.QPointF(0, y), 0.39 * S, 0.105 * S)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(HOLE_DARK)
        p.drawEllipse(QtCore.QPointF(0, y + 0.004 * S), 0.33 * S, 0.075 * S)

    def _paint_pursuit(self, p, now):
        """따라 보기 단계 그림: ① 두더지가 땅을 파고 들어감 → ② 땅속에서 흙더미가 8자로 이동 → ③ 다시 튀어나옴."""
        e = now - self.step_t0
        if e < PURSUIT_DIG_SEC:                                      # ① 땅 파기: 부들부들 떨며 쏙 들어감
            k = e / PURSUIT_DIG_SEC
            cx, cy = self._target_px(self._current())
            self._draw_mole(p, self.mole_pix, cx, cy, 7 * math.sin(e * 38), 1.0, 1 - k * k)
            self._draw_dirt_spray(p, cx, cy, k)
        elif e < PURSUIT_DIG_SEC + PURSUIT_SEC:                      # ② 흙더미 이동
            self._draw_tunnel(p, e - PURSUIT_DIG_SEC)
        else:                                                        # ③ 도착해서 튀어나옴
            k = min((e - PURSUIT_DIG_SEC - PURSUIT_SEC) / PURSUIT_POP_SEC, 1.0)
            cx, cy = self._target_px(self._current())
            self._draw_mole(p, self.mole_pix, cx, cy, 0.0, 1.0, 1 - (1 - k) ** 3)

    def _draw_dirt_spray(self, p, cx, cy, k):
        """땅 팔 때 구멍 주변으로 튀는 흙덩이."""
        S = self.S
        hole_y = cy + (HOLE_MID_Y - MOLE_NOSE_Y) * S
        p.setPen(QtGui.QPen(DIRT_DARK, 2))
        p.setBrush(DIRT)
        for i in range(7):
            phase = (k * 2.2 + i * 0.37) % 1.0                       # 흙덩이마다 시차를 두고 반복해서 튐
            side = -1 if i % 2 else 1
            x = cx + side * (0.18 + 0.05 * (i % 3)) * S + side * phase * 0.35 * S
            y = hole_y - math.sin(phase * math.pi) * (0.25 + 0.06 * (i % 3)) * S
            r = (0.025 + 0.008 * (i % 3)) * S
            p.drawEllipse(QtCore.QPointF(x, y), r, r)

    def _draw_tunnel(self, p, m):
        """땅속을 지나가는 두더지: 지나온 길에 흙 자국을 남기며 움직이는 흙더미. 흙더미 가운데가 바라볼 지점."""
        S, w, h = self.S, self.width(), self.height()
        p.setPen(QtCore.Qt.NoPen)
        trail = 18
        for j in range(trail, 0, -1):                                # 지나온 길 (오래된 것일수록 작고 흐리게)
            tt = m - j * 0.06
            if tt < 0:
                continue
            x, y = pursuit_pos(tt)
            a = 1 - j / trail
            c = QtGui.QColor(DIRT)
            c.setAlpha(int(40 + 150 * a))
            p.setBrush(c)
            r = (0.07 + 0.09 * a) * S
            p.drawEllipse(QtCore.QPointF(x * w, y * h), r, r * 0.55)

        x, y = pursuit_pos(m)
        px, py = x * w, y * h
        wob = 1 + 0.07 * math.sin(m * 18)                           # 땅 파는 느낌으로 들썩들썩
        p.setPen(QtGui.QPen(DIRT_DARK, 3))
        p.setBrush(DIRT)
        p.drawEllipse(QtCore.QPointF(px, py), 0.24 * S * wob, 0.14 * S / wob)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(196, 148, 104))                     # 위쪽 하이라이트
        p.drawEllipse(QtCore.QPointF(px - 0.05 * S, py - 0.045 * S), 0.11 * S, 0.04 * S)
        p.setPen(QtGui.QPen(DIRT_DARK, 2))
        p.setBrush(DIRT)
        for ox, oy, r in ((-0.27, 0.07, 0.035), (0.26, 0.05, 0.03), (0.17, -0.11, 0.022), (-0.15, -0.12, 0.02)):
            p.drawEllipse(QtCore.QPointF(px + ox * S * wob, py + oy * S), r * S, r * S)   # 흙덩이
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(HOLE_DARK)                                       # 가운데 작은 구멍 = 눈으로 따라갈 점
        p.drawEllipse(QtCore.QPointF(px, py), 0.035 * S, 0.025 * S)

    def _draw_progress(self, p, s, cx, cy, now):
        """두더지를 감싸는 진행 고리. 격자: 안 보고 있으면 빨간 고리 → 보는 동안 노랗게 차오름 → 확정되면 초록.
        자세변화=노랑, 검증=초록으로 시간에 따라 차오름."""
        if s["kind"] == "grid":
            frac = self.tracker.progress(now) if self.tracker else 0.0
            fill = theme.GREEN if frac >= 1.0 else theme.YELLOW
            edge = theme.RED if frac == 0.0 else fill
        elif s["kind"] == "pursuit":
            frac, fill, edge = min((now - self.step_t0) / PURSUIT_SEC, 1.0), theme.YELLOW, theme.YELLOW
        elif s["kind"] == "pose":
            frac, fill, edge = min((now - self.step_t0) / POSE_SEC, 1.0), theme.YELLOW, theme.YELLOW
        else:
            frac, fill, edge = min((now - self.step_t0) / VALIDATE_SEC, 1.0), theme.GREEN, theme.GREEN

        R = RING_R * self.S
        ring = QtCore.QRectF(cx - R, cy + 0.05 * self.S - R, 2 * R, 2 * R)   # 두더지+구멍 전체를 감싸는 원
        base = edge if edge == theme.RED else QtGui.QColor(255, 255, 255, 235)
        p.setBrush(QtCore.Qt.NoBrush)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 230), 12))        # 바깥 흰 테 (어떤 배경에서도 보이게)
        p.drawEllipse(ring)
        p.setPen(QtGui.QPen(base, 7))
        p.drawEllipse(ring)
        if frac > 0:
            pen = QtGui.QPen(fill, 7)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(ring, 90 * 16, int(-360 * 16 * frac))                # 12시부터 시계방향으로 차오름

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

    def _caption_top(self, s):
        """안내 문구 블록(제목·진행 점·경고)의 윗변 y. 두더지들과 겹치지 않는 자리.
        격자/따라보기/자세변화 = 맨 윗줄 두더지 고리 바로 아래, 검증 = 화면 가운데 (검증 두더지는 네 귀퉁이 쪽에만 나옴)."""
        if s["kind"] == "validate":
            return self.height() * 0.5 - self._title_px()
        ys = np.linspace(MARGIN, 1 - MARGIN, GRID_ROWS)
        return self.height() * ys[0] + (0.05 + RING_R) * self.S + 10

    def _title_px(self):
        return max(24, min(40, int(self.height() * 0.036)))

    def _outlined_text(self, p, cx, cy, text, font, fill, outline, width):
        """(cx, cy)를 가운데로 하는 테두리 글씨 (사진처럼 굵은 외곽선 → 어떤 배경에서도 잘 보임)."""
        fm = QtGui.QFontMetricsF(font)
        path = QtGui.QPainterPath()
        path.addText(cx - fm.horizontalAdvance(text) / 2, cy + (fm.ascent() - fm.descent()) / 2, font, text)
        pen = QtGui.QPen(outline, width)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawPath(path)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(fill)
        p.drawPath(path)

    def _draw_dots(self, p, cx, cy, n, total):
        """진행 점: 끝난 것 = 초록, 지금 것 = 주황 테두리, 남은 것 = 흰 점."""
        r, gap = 11, 38
        x0 = cx - gap * (total - 1) / 2
        for i in range(total):
            c = QtCore.QPointF(x0 + i * gap, cy)
            if i < n - 1:
                p.setPen(QtGui.QPen(theme.INK, 2.5))
                p.setBrush(theme.GREEN)
            elif i == n - 1:
                p.setPen(QtGui.QPen(theme.HIGHLIGHT, 4))
                p.setBrush(QtGui.QColor(255, 255, 255))
            else:
                p.setPen(QtGui.QPen(theme.INK, 2.5))
                p.setBrush(QtGui.QColor(255, 255, 255))
            p.drawEllipse(c, r, r)

    def _draw_caption(self, p, s, now):
        n, total = s["n"], s["total"]
        text = {
            "grid": "두더지의 얼굴을 쳐다봐 주세요!",
            "pursuit": "땅속 두더지를 눈으로만 따라가 주세요!",
            "pose": "두더지를 보면서 고개를 천천히 움직여 주세요!",
            "validate": "새로 나온 두더지를 쳐다봐 주세요!",
        }[s["kind"]]
        tp = self._title_px()
        top = self._caption_top(s)
        cx = self.width() / 2
        self._outlined_text(p, cx, top + tp * 0.6, text, theme.title_font(tp),
                            QtGui.QColor(255, 255, 255), theme.INK, 7)
        y = top + tp * 1.2
        if s["kind"] != "pursuit":                               # 따라 보기는 한 번뿐이라 점 없음
            self._draw_dots(p, cx, y + 14, n, total)
            y += 34
        if not self.mouse_mode and now - self.last_face_t > FACE_LOST_WARN_SEC:
            self._outlined_text(p, cx, y + tp * 0.5, "얼굴이 안 보여요! 카메라를 봐주세요",
                                theme.title_font(tp * 0.8), theme.RED, QtGui.QColor(255, 255, 255), 6)
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
