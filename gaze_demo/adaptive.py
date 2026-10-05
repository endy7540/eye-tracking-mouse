# -*- coding: utf-8 -*-
"""
adaptive.py — 쓰면 쓸수록 정확해지는 "자동 보정"

두더지 캘리브레이션은 그 1~2분 동안의 자세만 담고 있어서, 기대거나 고개를 숙이면 금방 틀어집니다.
그래서 평소에 사용하다가 "지금 어디를 보고 있었는지 확실히 아는 순간"마다 데이터를 하나씩 모아
몇 개 쌓일 때마다 다시 학습합니다. 시간이 지날수록 여러 자세의 데이터가 쌓여서 자세 변화에 강해집니다.

정답을 아는 순간 두 가지
    1) 응시 클릭 성공: 버튼을 바라봐서 눌렀다면 그동안 그 버튼을 보고 있었던 것 → 버튼 위치가 정답
       (마우스를 못 쓰는 사용자도 쓰면 쓸수록 저절로 보정됨)
    2) 실제 마우스 클릭: 마우스를 움직여 목표에 멈춘 뒤 클릭했다면 대부분 그곳을 보고 있음 → 클릭 위치가 정답

잘못된 데이터 거르기
    - 클릭 직전 눈동자가 흔들렸으면(다른 곳을 보다가 클릭) 버림
    - 지금 예측 위치와 클릭 위치가 화면 대각선의 30% 이상 떨어져 있으면 일단 "안 보고 클릭"으로 보고 보류
      단, 보류된 클릭들이 매번 "같은 방향·같은 거리"로 어긋나 있으면(예: 늘 실제보다 위로 튐)
      그건 안 보고 누른 게 아니라 보정이 크게 틀어진 것 → 보류했던 것들을 한꺼번에 받아들여 바로 다시 학습
    - 다시 학습한 결과가 두더지 캘리브레이션 데이터에서 크게 나빠지면 그 학습 결과는 적용하지 않음

다시 학습할 때 섞는 비율
    - 두더지 데이터(화면 전체를 고르게 덮음)는 기준점으로 항상 일부 비중을 유지
    - 사용 중 모은 데이터는 최근 것일수록, 그리고 클릭이 몰리지 않은 화면 구역일수록 비중을 높게
      (클릭은 브라우저 탭·주소창처럼 특정 구역에 몰리기 때문)

저장되는 것은 눈 특징값 숫자와 클릭 좌표뿐이고, 카메라 영상은 저장하지 않습니다.
Qt와 무관한 파일입니다 (마우스 버튼 상태 읽기만 윈도우 함수 사용).
"""
import ctypes
import sys
from collections import deque

import numpy as np

from gaze_core import (STABLE_HX_TOL, STABLE_VY_TOL, fit, predict_norm, feature_ranges,
                       clip_feature)

FRAME_KEEP_SEC = 2.0          # 최근 이만큼의 눈 데이터를 보관 (클릭 직전 구간을 꺼내 쓰기 위해)
DWELL_WINDOW = (0.70, 0.05)   # 응시 클릭: 클릭 0.7초 전 ~ 0.05초 전 (버튼을 바라보던 구간)
MOUSE_WINDOW = (0.35, 0.05)   # 마우스 클릭: 클릭 0.35초 전 ~ 0.05초 전 (목표에 도착해서 보던 구간)
MIN_FRAMES = 3                # 그 구간에 눈 뜬 프레임이 이만큼은 있어야 사용
MIN_GAP_SEC = 0.8             # 샘플 사이 최소 간격 (연속 입력 키가 같은 자리 데이터를 몰아넣지 않게)
OUTLIER_FRAC = 0.30           # 예측과 클릭 위치가 화면 대각선의 이 비율 이상 떨어지면 버림

ONLINE_MAX = 1500             # 사용 중 모은 샘플은 최근 이만큼만 유지 (하루치 정도의 여러 자세를 기억, 오래된 건 밀려남)
REFIT_EVERY = 5               # 새 샘플이 이만큼 모일 때마다 다시 학습
ONLINE_SHARE_MAX = 0.65       # 다시 학습할 때 사용 중 데이터의 최대 비중 (나머지는 두더지 데이터)
ONLINE_FULL_AT = 20           # 샘플이 이만큼 모이면 최대 비중까지 반영 (처음 몇 개로 확 바뀌지 않게)
RECENCY_HALF = 450            # 450개 전 샘플은 가장 최근 샘플의 절반 비중 (보관량을 늘린 만큼 같이 늘림)
BINS = 4                      # 화면을 4x4 구역으로 나눠 구역마다 비중을 고르게
GUARD_RATIO = 2.0             # 두더지 데이터 오차가 처음보다 이 배 이상 나빠지면 적용 안 함
GUARD_FLOOR = 0.05            # ... 단, 대각선의 5% 이내면 나빠져도 허용 (처음 오차가 아주 작을 때 대비)

# 크게 틀어진 상태 감지 — 멀리 어긋난 클릭이라도 "늘 같은 쪽으로 어긋나면" 받아들임
HOLD_KEEP_SEC = 300.0         # 보류한 클릭은 최근 5분 것만 비교
CONSISTENT_MIN = 4            # 보류한 클릭이 이만큼 모이면 일관성 검사
CONSISTENT_TOL = 0.10         # 어긋난 방향·거리의 흩어짐이 대각선의 10% 이내면 "일관되게 어긋남"으로 판단


class AdaptiveCalibrator:
    def __init__(self, W, anchor_feats, anchor_labels, anchor_weights, screen_w, screen_h,
                 online_feats=None, online_labels=None):
        self.W = np.asarray(W, dtype=float)
        self.A_f = np.asarray(anchor_feats, dtype=float)
        self.A_y = np.asarray(anchor_labels, dtype=float)
        aw = np.ones(len(self.A_f)) if anchor_weights is None else np.asarray(anchor_weights, dtype=float)
        self.A_w = aw / aw.sum()
        # 0~1 좌표 차이를 "화면 대각선 대비 비율"로 바꾸는 배율
        self.diag = float(np.hypot(screen_w, screen_h))
        self.aspect = np.array([screen_w, screen_h], dtype=float) / self.diag
        self.recent_err = deque(maxlen=20)        # 최근 마우스 클릭 때 예측이 얼마나 빗나갔는지(px) — 상태 확인 창 표시용

        self.frames = deque()                     # (시각, 특징값)
        self.online = deque(maxlen=ONLINE_MAX)    # (특징값, 정답 0~1 좌표)
        if online_feats is not None and len(online_feats):
            for f, y in zip(online_feats, online_labels):
                self.online.append((np.asarray(f, dtype=float), np.asarray(y, dtype=float)))
        self.pending = 0
        self.last_sample_t = 0.0
        self.held = deque()                       # 멀리 어긋나서 보류한 클릭 (시각, 특징값, 정답, 어긋난 양)
        self.big_fixes = 0                        # '크게 틀어짐'을 감지해서 고친 횟수 (확인용)
        self.base_anchor_err = self._error(self.W, self.A_f, self.A_y, self.A_w)
        self.ranges = self._ranges()
        if self.online:                           # 저장돼 있던 샘플이 있으면 시작할 때 한 번 반영
            self._refit()

    @property
    def count(self):
        return len(self.online)

    def recent_accuracy(self):
        """(클릭 수, 평균 오차 px) — 아직 기록이 없으면 None."""
        if not self.recent_err:
            return None
        return len(self.recent_err), float(np.mean(self.recent_err))

    # ── 데이터 입구 ───────────────────────────────────────────────
    def add_frame(self, t, feat):
        self.frames.append((t, np.asarray(feat, dtype=float)))
        while self.frames and t - self.frames[0][0] > FRAME_KEEP_SEC:
            self.frames.popleft()

    def add_click(self, t, label, kind):
        """t 시각에 label(0~1 화면 좌표)을 보고 클릭했다는 정보.
        kind: "dwell"(응시 클릭) 또는 "mouse"(실제 마우스 클릭).
        반환: "rejected"(버림) / "added"(모아둠) / "refit"(다시 학습해서 self.W 바뀜) / "kept"(학습했지만 적용 안 함)"""
        if t - self.last_sample_t < MIN_GAP_SEC:
            return "rejected"
        before, after = DWELL_WINDOW if kind == "dwell" else MOUSE_WINDOW
        win = [f for (ft, f) in self.frames if t - before <= ft <= t - after]
        if len(win) < MIN_FRAMES:
            return "rejected"
        win = np.array(win)
        if np.ptp(win[:, 0]) > STABLE_HX_TOL or np.ptp(win[:, 1]) > STABLE_VY_TOL:
            return "rejected"                     # 그 사이 눈동자가 움직임 = 한곳을 보고 있지 않았음
        f = np.median(win, axis=0)
        y = np.clip(np.asarray(label, dtype=float), 0.0, 1.0)
        pred = predict_norm(self.W, clip_feature(f, self.ranges))
        resid = (y - pred) * self.aspect          # 실제 클릭 위치 - 예측 위치 (대각선 비율 단위)
        self.last_sample_t = t
        if kind == "mouse":                       # 응시 클릭은 예측이 이미 버튼 안이라 정확도 지표로는 안 씀
            self.recent_err.append(float(np.linalg.norm(resid)) * self.diag)
        if np.linalg.norm(resid) > OUTLIER_FRAC:
            return self._hold(t, f, y, resid)     # 너무 멀다 → 일단 보류하고 같은 패턴이 반복되는지 봄

        self.online.append((f, y))
        self.pending += 1
        if self.pending >= REFIT_EVERY:
            self.pending = 0
            return "refit" if self._refit() else "kept"
        return "added"

    def _hold(self, t, f, y, resid):
        """멀리 어긋난 클릭을 보류. 최근 보류분이 늘 같은 방향·거리로 어긋나 있으면 보정이 틀어진 것으로 보고 반영."""
        self.held.append((t, f, y, resid))
        while self.held and t - self.held[0][0] > HOLD_KEEP_SEC:
            self.held.popleft()
        if len(self.held) < CONSISTENT_MIN:
            return "rejected"
        R = np.array([r for *_, r in self.held])
        spread = float(np.median(np.linalg.norm(R - np.median(R, axis=0), axis=1)))
        if spread > CONSISTENT_TOL:
            return "rejected"                     # 제각각 어긋남 = 정말 안 보고 누른 클릭들
        for _, hf, hy, _ in self.held:
            self.online.append((hf, hy))
        print(f"[자동 보정] 클릭 {len(self.held)}번이 늘 같은 쪽으로 어긋나서, 보정이 틀어진 걸로 보고 바로 고쳐요")
        self.held.clear()
        self.big_fixes += 1
        self.pending = 0
        return "refit" if self._refit(force=True) else "kept"

    # ── 다시 학습 ─────────────────────────────────────────────────
    def _refit(self, force=False):
        """force=True: '크게 틀어짐'이 확인된 경우라 두더지 데이터 기준 안전장치(GUARD)를 건너뜀.
        (두더지 데이터 자체가 지금 상태와 안 맞는 상황이므로 그 기준으로 막으면 영원히 못 고침)"""
        F_on = np.array([f for f, _ in self.online])
        Y_on = np.array([y for _, y in self.online])
        n = len(F_on)
        share = ONLINE_SHARE_MAX * min(1.0, n / ONLINE_FULL_AT)

        age = np.arange(n)[::-1]                              # 가장 최근 = 0
        w_recent = 0.5 ** (age / RECENCY_HALF)
        bx = np.clip((Y_on[:, 0] * BINS).astype(int), 0, BINS - 1)
        by = np.clip((Y_on[:, 1] * BINS).astype(int), 0, BINS - 1)
        cell = bx * BINS + by
        w_spread = 1.0 / np.bincount(cell, minlength=BINS * BINS)[cell]   # 몰린 구역일수록 하나하나 비중 ↓
        w_on = w_recent * w_spread
        w_on = w_on / w_on.sum() * share

        F = np.vstack([self.A_f, F_on])
        Y = np.vstack([self.A_y, Y_on])
        w = np.concatenate([self.A_w * (1.0 - share), w_on])
        try:
            W_new = fit(list(F), Y, weights=w)
        except Exception as e:
            print("[자동 보정] 학습 실패:", e)
            return False

        err = self._error(W_new, self.A_f, self.A_y, self.A_w)
        if not force and err > max(GUARD_RATIO * self.base_anchor_err, GUARD_FLOOR):
            print(f"[자동 보정] 새 결과가 기준 데이터에서 너무 나빠서 적용하지 않음 "
                  f"(대각선의 {err * 100:.1f}%)")
            return False
        self.W = W_new
        self.ranges = self._ranges()
        if force:   # 기준이 바뀐 것이므로 안전장치 기준도 새 상태에 맞춤 (안 그러면 이후 학습이 계속 막힘)
            self.base_anchor_err = max(self.base_anchor_err, err)
        return True

    def _ranges(self):
        feats = self.A_f if not self.online else np.vstack([self.A_f, [f for f, _ in self.online]])
        return feature_ranges(feats)

    def _error(self, W, F, Y, w):
        pred = np.array([predict_norm(W, f) for f in F])
        return float(np.average(np.linalg.norm((pred - Y) * self.aspect, axis=1), weights=w))

    def to_arrays(self):
        """calibration.npz에 같이 저장할 데이터."""
        return {
            "anchor_feats": self.A_f, "anchor_labels": self.A_y, "anchor_weights": self.A_w,
            "online_feats": np.array([f for f, _ in self.online]).reshape(-1, self.A_f.shape[1]),
            "online_labels": np.array([y for _, y in self.online]).reshape(-1, 2),
        }


# ── 실제 마우스 왼쪽 버튼 상태 (윈도우 전체, 다른 프로그램에서 누른 것까지) ──────────
def left_button_down():
    if sys.platform != "win32":
        return False
    return bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
