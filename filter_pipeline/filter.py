# -*- coding: utf-8 -*-
"""
filter.py — 시선 필터 모듈. 프로젝트의 모든 스무딩/필터는 이 파일에서 관리한다.

══════════ 이어서 작업하는 사람 / AI 를 위한 안내 ══════════

1) 이 파일에 있는 필터 (클래스 5개)
   ┌──────────────────┬────────────────────────────────┬─────────────────────────────────────┬────────┐
   │ 이름             │ 역할                           │ 쓰이는 곳                           │ 상태   │
   ├──────────────────┼────────────────────────────────┼─────────────────────────────────────┼────────┤
   │ LowPassFilter    │ 지수평활 한 단계 (부품)        │ OneEuroFilter1D 안에서              │ 사용   │
   │ OneEuroFilter1D  │ 숫자 하나를 속도에 따라 다듬음 │ GazeStabilizer 안에서               │ 사용   │
   │ GazeStabilizer   │ 화면 좌표: 이상치 제거 →       │ vision/gaze_core.py                 │ 주력   │
   │                  │ One Euro → EMA                 │   GazeSession.process()             │        │
   │ Smoother         │ 화면 좌표: 속도 적응형 EMA     │ GazeSession.process()               │ 예비용 │
   │                  │ (기존 방식)                    │   DEFAULT_PARAMS["enabled"]=False   │        │
   │                  │                                │   일 때만 사용                      │        │
   │ FeatureSmoother  │ 머리 위치 특징값(nx,ny,pitch,  │ GazeSession.process()               │ 사용   │
   │                  │ yaw)만 EMA                     │                                     │        │
   └──────────────────┴────────────────────────────────┴─────────────────────────────────────┴────────┘

2) 한 프레임이 지나가는 순서 (vision/gaze_core.py 의 GazeSession.process)
     카메라 → extract_features → feat
       → [FeatureSmoother]  머리 위치만 EMA (hx, vy 는 건드리지 않음)
       → 좌표 매핑 predict_px (캘리브레이션에서 학습한 W)  → raw (화면 픽셀 좌표)
       → [GazeStabilizer]   이상치 제거 → One Euro → EMA
            (enabled=False 이면 위 대신 [Smoother] = 예전 방식)
       → main.py 가 확대 팬 계산을 거쳐 커서에 표시
   main.py 에는 필터 코드가 없다. 필터는 GazeSession 이 소유하고 스스로 호출한다.

3) 가중치와 켜기/끄기는 아래 DEFAULT_PARAMS 에서만 바꾼다.
   main.py / gaze_core.py 에 가중치 숫자를 따로 쓰지 말 것 (같은 값이 두 곳에 있으면
   어느 쪽이 적용되는지 헷갈린다). 실행 중 임시로 바꾸려면 session.stabilizer.set_parameters(...).

4) 지켜야 할 규칙
   - 의존 방향: gaze_core → filter.py. 이 파일은 gaze_core / PyQt / cv2 를 import 하지 않는다.
     (순환 import 방지 + 카메라·화면 없이 테스트 가능. numpy 와 math 만 사용)
   - 좌표 단위: GazeStabilizer, Smoother 는 '화면 픽셀 좌표' 전용이다. 특징값(0.0x 단위)에
     쓰면 안 된다 (beta 와 이상치 거리가 px 기준이라 엉뚱하게 동작).
   - hx, vy(실제 시선 신호)에는 스무딩을 걸지 말 것. 세로(vy) 신호는 가로보다 진폭이 작아서
     이중 스무딩에 특히 취약하다 (FeatureSmoother 주석 참고).
   - 캘리브레이션(calibration/)은 필터를 거치지 않은 원본 특징값을 모아 '안정 구간의 중앙값'으로
     W 를 학습한다. 학습용 특징값에 필터를 새로 걸려면 ① 실행 때도 같은 필터를 걸어야 하고
     ② gaze_core.PURSUIT_LAG_SEC(지연 보정)을 다시 맞춰야 하고 ③ 특징값 단위용 가중치가
     따로 필요하다. 그 전에는 건드리지 말 것.
   - 상태가 있는 필터다. 재캘리브레이션 때는 GazeSession 이 새로 만들어지면서 필터도 새로
     만들어져 자동 초기화된다. 필터 객체를 따로 재사용한다면 reset() 을 직접 불러야 한다.
   - GazeStabilizer.update(x, y, t) 의 t 는 카메라 스레드가 준 프레임 시각(초). 프레임 간격을
     실제 시각으로 계산하므로 카메라 fps 가 달라도 가중치를 다시 맞출 필요가 없다.

5) 튜닝 기록 (동영상 분석, 30fps / 1920x1080 기준)
   - max_outlier_frames 2 → 4: 3프레임 이상 이어지는 튐(300px)이 출력에 그대로 실리던 문제를
     0px 로 차단. 대가: 110px 넘는 큰 시선 이동의 반영이 약 67ms 늦어짐.
   - min_cutoff / ema_alpha 를 낮추는 조정은 시뮬레이션에서 정지 떨림 개선이 거의 없고
     반응만 느려져서 적용하지 않았다.
   - 위 수치는 가정한 잡음으로 만든 시뮬레이션이다. 원본(필터 입력) 좌표를 기록해서 다시 맞출 것.
   - 영상에서 가장 컸던 문제(세로 방향 매핑 붕괴, 가로 범위 압축)는 필터가 아니라
     캘리브레이션/좌표 매핑 쪽 문제다. 필터 가중치로는 해결되지 않는다.

6) 원본 필터 코드 대비 고친 점 (GazeStabilizer 쪽)
   min_cutoff 이름 통일(예전엔 슬라이더가 무효였음) / 이상치가 이동으로 확정될 때 내부 상태까지
   초기화(커서가 되돌아가던 문제) / 프레임 간격을 실제 시각으로 계산 / 이상치 거리를 화면 대각선
   비율로 지정 / 붙잡는 프레임 수 off-by-one 수정 / 속도 계산을 표준(직전 원본값 기준)으로 수정 /
   입력이 끊기면 자동 초기화.
"""
import math

import numpy as np


# ════════════════════════════════════════════════════════════════
#  [부품] 다른 필터 안에서 쓰이는 작은 도구들
# ════════════════════════════════════════════════════════════════
class LowPassFilter:
    """지수평활(EMA) 한 단계. alpha가 클수록 새 값을 많이 반영."""

    def __init__(self):
        self.s = None

    def filter(self, value, alpha):
        if self.s is None:
            self.s = value
        else:
            self.s = alpha * value + (1.0 - alpha) * self.s
        return self.s

    def reset(self, value=None):
        self.s = value


class OneEuroFilter1D:
    """
    One Euro 필터 (1차원). 입력 변화가 작으면 강하게, 크면 약하게 평활화.
        min_cutoff : 가만히 있을 때의 떨림 억제 (낮을수록 강하게 잡음, 대신 반응이 느려짐)
        beta       : 움직일 때 지연 감소 (높을수록 빠르게 따라감, 대신 떨림이 늘어남)
        dcutoff    : 속도 추정에 쓰는 컷오프 (보통 1.0 고정)
    """

    def __init__(self, freq=30.0, min_cutoff=1.0, beta=0.0, dcutoff=1.0):
        self.freq = float(freq)              # 시각 t를 못 받았을 때만 쓰는 기본 프레임 속도
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.dcutoff = float(dcutoff)
        self.x_prev = None                   # 직전 '원본' 입력 (속도 계산용)
        self.lpf = LowPassFilter()           # 위치 평활
        self.d_lpf = LowPassFilter()         # 속도 평활

    # 예전 코드(mincutoff)와의 호환용 별칭
    @property
    def mincutoff(self):
        return self.min_cutoff

    @mincutoff.setter
    def mincutoff(self, v):
        self.min_cutoff = float(v)

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2.0 * math.pi * max(cutoff, 1e-6))
        return 1.0 / (1.0 + tau / dt)

    def update(self, x, dt=None):
        dt = (1.0 / self.freq) if (dt is None or dt <= 0) else dt
        if self.x_prev is None:              # 첫 값: 그대로 통과
            self.x_prev = x
            self.lpf.reset(x)
            self.d_lpf.reset(0.0)
            return x
        dx = (x - self.x_prev) / dt          # 원본 기준 속도 (px/초)
        self.x_prev = x
        edx = self.d_lpf.filter(dx, self._alpha(self.dcutoff, dt))
        cutoff = self.min_cutoff + self.beta * abs(edx)
        return self.lpf.filter(x, self._alpha(cutoff, dt))

    def reset(self, value=None):
        """value가 있으면 그 위치에서 다시 시작 (이전 위치로 끌려가지 않음)."""
        self.x_prev = value
        self.lpf.reset(value)
        self.d_lpf.reset(0.0 if value is not None else None)


# ════════════════════════════════════════════════════════════════
#  기본 가중치 — 필터 설정은 여기 한 곳에서만 관리합니다.
#  main.py는 이 값을 그대로 쓰고, 바꾸고 싶은 항목만 set_parameters()로 넘깁니다.
# ════════════════════════════════════════════════════════════════
DEFAULT_PARAMS = {
    "enabled":            True,   # False면 GazeStabilizer 대신 예비용 Smoother(이 파일 아래)를 사용 (전후 비교용)
    "min_cutoff":         0.5,    # [정지 떨림] 낮을수록 가만히 볼 때 꽉 잡아줌 (대신 시작 반응이 느려짐)
    "beta":               0.004,  # [움직임 반응] 높을수록 빠르게 볼 때 지연이 줄어듦 (대신 움직일 때 떨림 증가)
    "ema_alpha":          0.85,   # [최종 블렌딩] 높을수록 최신 값 반영, 낮을수록 부드러움 (0~1]
    "max_jump_ratio":     0.05,   # [이상치 거리] 화면 대각선 대비 이 비율보다 멀리 튀면 이상치로 의심
    "max_outlier_frames": 4,      # [이상치 유지] 튄 값이면 이 프레임 수만큼 이전 위치 유지, 그래도 계속 멀면 진짜 이동으로 확정
                                  #   ※ 영상 분석(3프레임 이상 이어지는 튐이 통과함) 반영: 2 → 4. 대가: 큰 시선 이동 반영이 약 67ms 늦어짐 (30fps)
    "dcutoff":            1.0,    # 속도 추정용 컷오프 (보통 건드리지 않음)
    "gap_reset_sec":      0.5,    # 입력이 이 시간 이상 끊기면 처음부터 다시 시작
}
FALLBACK_JUMP_PX = 250.0          # set_screen_size()를 부르기 전에만 쓰는 이상치 거리(px)


# ════════════════════════════════════════════════════════════════
#  [주력] 화면 좌표 안정화 — GazeSession.process() 가 매 프레임 호출
#  입력: 화면 픽셀 좌표(raw_x, raw_y)와 프레임 시각 t  /  출력: 안정화된 화면 픽셀 좌표
# ════════════════════════════════════════════════════════════════
class GazeStabilizer:
    """이상치 제거 + One Euro + EMA를 묶은 시선 안정화기. 기본 가중치는 DEFAULT_PARAMS."""

    def __init__(self, fps=30.0, **overrides):
        self.fps = float(fps)                 # t를 못 받았을 때만 쓰는 기본값 (웹캠 기준 30)
        p = dict(DEFAULT_PARAMS)
        unknown = set(overrides) - set(p)
        if unknown:
            raise TypeError("알 수 없는 필터 설정: %s (가능: %s)" % (sorted(unknown), sorted(p)))
        p.update(overrides)

        self.enabled = bool(p["enabled"])

        # 1단계: 이상치
        self.max_jump_ratio = p["max_jump_ratio"]
        self.max_jump_distance = FALLBACK_JUMP_PX      # px — set_screen_size 후에는 비율로 계산됨
        self.max_outlier_frames = p["max_outlier_frames"]
        self.outlier_count = 0
        self.prev_valid_x = None
        self.prev_valid_y = None

        # 2단계: One Euro
        self.euro_x = OneEuroFilter1D(freq=fps, min_cutoff=p["min_cutoff"], beta=p["beta"], dcutoff=p["dcutoff"])
        self.euro_y = OneEuroFilter1D(freq=fps, min_cutoff=p["min_cutoff"], beta=p["beta"], dcutoff=p["dcutoff"])

        # 3단계: 최종 EMA
        self.ema_alpha = p["ema_alpha"]
        self.final_x = None
        self.final_y = None

        # 시간 처리
        self.gap_reset_sec = p["gap_reset_sec"]
        self._last_t = None
        self._screen = None                   # (w, h) — reset_parameters()에서 이상치 거리를 다시 계산할 때 사용

    # ── 설정 ──────────────────────────────────────────────────────
    def set_screen_size(self, w, h):
        """이상치 허용 거리를 화면 대각선 × max_jump_ratio로 맞춤 (해상도가 바뀌어도 같은 느낌)."""
        self._screen = (w, h)
        self.max_jump_distance = self.max_jump_ratio * math.hypot(w, h)

    def set_parameters(self, min_cutoff=None, beta=None, ema_alpha=None, max_jump_ratio=None,
                       max_outlier_frames=None, max_jump_distance=None, dcutoff=None,
                       gap_reset_sec=None, screen_size=None, enabled=None):
        """
        바꾸고 싶은 항목만 넘기면 됨 (None이면 현재 값 유지). 의미는 DEFAULT_PARAMS 주석 참고.
            max_jump_distance: px로 직접 지정 (비율 설정보다 우선)
            screen_size=(w, h): max_jump_ratio를 바꿀 때 px 거리를 함께 다시 계산
        예)  stab.set_parameters(beta=0.006)
             stab.set_parameters(max_outlier_frames=4, max_jump_ratio=0.08)
        """
        if enabled is not None:
            self.enabled = bool(enabled)
        if min_cutoff is not None:
            self.euro_x.min_cutoff = self.euro_y.min_cutoff = max(0.01, float(min_cutoff))
        if beta is not None:
            self.euro_x.beta = self.euro_y.beta = max(0.0, float(beta))
        if dcutoff is not None:
            self.euro_x.dcutoff = self.euro_y.dcutoff = max(0.01, float(dcutoff))
        if ema_alpha is not None:
            self.ema_alpha = max(0.01, min(1.0, float(ema_alpha)))
        if max_outlier_frames is not None:
            self.max_outlier_frames = max(0, int(max_outlier_frames))
        if gap_reset_sec is not None:
            self.gap_reset_sec = max(0.05, float(gap_reset_sec))
        if max_jump_ratio is not None:
            self.max_jump_ratio = float(max_jump_ratio)
            size = screen_size or self._screen
            if size is not None:
                self.set_screen_size(*size)
        if max_jump_distance is not None:
            self.max_jump_distance = float(max_jump_distance)

    def get_parameters(self):
        """현재 적용 중인 가중치를 dict로 돌려줌 (상태창 표시·로그 기록용)."""
        return {
            "enabled": self.enabled,
            "min_cutoff": self.euro_x.min_cutoff,
            "beta": self.euro_x.beta,
            "ema_alpha": self.ema_alpha,
            "max_jump_ratio": self.max_jump_ratio,
            "max_jump_distance": self.max_jump_distance,
            "max_outlier_frames": self.max_outlier_frames,
            "dcutoff": self.euro_x.dcutoff,
            "gap_reset_sec": self.gap_reset_sec,
        }

    def reset_parameters(self):
        """가중치를 DEFAULT_PARAMS로 되돌림 (필터 상태는 그대로)."""
        self.set_parameters(**{k: v for k, v in DEFAULT_PARAMS.items()})
        if self._screen is None:
            self.max_jump_distance = FALLBACK_JUMP_PX

    # ── 상태 ──────────────────────────────────────────────────────
    def reset(self):
        """모든 상태 초기화. 재캘리브레이션 / 일시정지 해제 / 눈을 오래 놓친 뒤에 호출."""
        self.prev_valid_x = self.prev_valid_y = None
        self.outlier_count = 0
        self.euro_x.reset()
        self.euro_y.reset()
        self.final_x = self.final_y = None
        self._last_t = None

    def _restart_at(self, x, y):
        """x, y 위치에서 필터를 새로 시작 (내부 저장값까지 전부 그 위치로)."""
        self.prev_valid_x, self.prev_valid_y = x, y
        self.outlier_count = 0
        self.euro_x.reset(x)
        self.euro_y.reset(y)
        self.final_x, self.final_y = x, y
        return x, y

    # ── 본체 ──────────────────────────────────────────────────────
    def update(self, raw_x, raw_y, t=None):
        """
        raw 좌표(px)와 그 프레임의 시각 t(초)를 넣으면 안정화된 좌표를 돌려줌.
        raw가 None이면 필터를 건드리지 않고 마지막 결과를 그대로 돌려줌 (첫 값 전에는 None).
        """
        if not self.enabled:                   # 필터 끔 → 입력을 그대로 돌려줌
            return raw_x, raw_y
        if raw_x is None or raw_y is None:
            return self.final_x, self.final_y

        # 프레임 간격: 실제 시각이 있으면 그걸로, 없으면 fps로
        if t is None:
            dt = 1.0 / self.fps
            t_now = None if self._last_t is None else self._last_t + dt
        else:
            dt = (t - self._last_t) if self._last_t is not None else 1.0 / self.fps
            t_now = t
        if t is not None and self._last_t is not None and dt > self.gap_reset_sec:
            self.reset()                       # 오랫동안 입력이 끊김 → 옛 위치로 끌려가지 않게 새로 시작
            dt = 1.0 / self.fps
        if dt <= 0:                            # 시각이 거꾸로/같은 값이면 기본 간격 사용
            dt = 1.0 / self.fps
        self._last_t = t_now if t_now is not None else self._last_t

        # 1단계: 이상치
        if self.prev_valid_x is not None:
            dist_sq = (raw_x - self.prev_valid_x) ** 2 + (raw_y - self.prev_valid_y) ** 2
            if dist_sq > self.max_jump_distance ** 2:
                self.outlier_count += 1
                if self.outlier_count <= self.max_outlier_frames:
                    return self.final_x, self.final_y        # 튄 값으로 보고 이전 위치 유지
                return self._restart_at(raw_x, raw_y)        # 계속 거기 있음 = 진짜 이동 → 그 위치에서 재시작
            self.outlier_count = 0
        self.prev_valid_x, self.prev_valid_y = raw_x, raw_y

        # 2단계: One Euro
        f_x = self.euro_x.update(raw_x, dt)
        f_y = self.euro_y.update(raw_y, dt)

        # 3단계: 최종 EMA
        if self.final_x is None:
            self.final_x, self.final_y = f_x, f_y
        else:
            a = self.ema_alpha
            self.final_x = a * f_x + (1.0 - a) * self.final_x
            self.final_y = a * f_y + (1.0 - a) * self.final_y
        return self.final_x, self.final_y


# ════════════════════════════════════════════════════════════════
#  [예비용] 화면 좌표 스무딩 — 기존 방식 (gaze_core.py 에서 옮겨 옴, 로직은 원본 그대로)
#
#  지금은 DEFAULT_PARAMS["enabled"] = False 일 때만 GazeSession 이 사용한다.
#  GazeStabilizer 가 켜져 있으면 호출되지 않는다 (둘을 겹쳐 쓰면 지연만 늘어남).
#  남겨 둔 이유: 새 필터와 기존 방식을 같은 화면에서 번갈아 비교하기 위해.
#  새 필터가 충분히 검증되면 지워도 된다 (지울 때는 gaze_core.GazeSession 의
#  self.smoother 와 process() 의 else 분기도 함께 지울 것).
#
#  한계(왜 주력이 아닌가): 속도에 따라 강도를 바꾸는 방식이라 '큰 한 번의 튐'과 '빠른 시선 이동'을
#  구분하지 못한다. 100px 짜리 한 프레임 스파이크의 절반 가까이(약 45px)가 그대로 통과한다.
#  입력은 화면 픽셀 좌표(numpy 배열 [x, y]) 이고 출력도 같은 형태다. 시각 t 는 쓰지 않는다.
# ════════════════════════════════════════════════════════════════
class Smoother:
    """
    움직임이 작을 땐 강하게, 클 땐 약하게 평활화 (떨림 억제 + 빠른 추종).
    화면 가로/세로 크기로 정규화한 거리를 사용 — 세로가 가로보다 짧다는 이유만으로
    위아래 움직임이 상대적으로 더 강하게 뭉개지는 것을 방지한다.
    (원본은 SCREEN_W/H를 직접 썼고, 데모는 화면 크기를 인자로 받는다)

    min_a : 거의 안 움직일 때의 반영 비율 (작을수록 정지 시 꽉 잡아줌)
    max_a : 크게 움직일 때의 반영 비율 (클수록 빠르게 따라감)
    dist  : 화면 크기 대비 이 비율 이상 움직이면 max_a 를 적용
    """

    def __init__(self, screen_w, screen_h, min_a=0.05, max_a=0.55, dist=0.065):
        self.min_a, self.max_a, self.dist = min_a, max_a, dist
        self.prev = None
        self.scale = np.array([screen_w, screen_h], dtype=float)

    def __call__(self, p):
        if self.prev is None:
            self.prev = p
            return p
        d = np.linalg.norm((p - self.prev) / self.scale)   # 0~1 정규화 거리
        a = self.min_a + (self.max_a - self.min_a) * min(d / self.dist, 1.0)
        self.prev = self.prev + a * (p - self.prev)
        return self.prev


# ════════════════════════════════════════════════════════════════
#  [특징값용] 머리 위치 스무딩 — GazeSession.process() 가 좌표 매핑 전에 호출 (gaze_core.py 에서 옮겨 옴)
#
#  주의: 입력은 화면 좌표가 아니라 '특징값 벡터' f = [hx, vy, nx, ny, op, pitch, yaw] 이다.
#  GazeStabilizer / Smoother 와 단위가 달라서 서로 바꿔 쓸 수 없다.
#  로직은 원본 그대로. 시선 신호 hx, vy 는 일부러 건드리지 않는다.
# ════════════════════════════════════════════════════════════════
class FeatureSmoother:
    """
    고개 위치(nx, ny)만 지수평활(EMA)로 부드럽게 만들고, 실제 시선 신호(hx, vy)는
    그대로 통과시킨다. hx/vy까지 여기서 스무딩하면 화면 좌표 단계의 Smoother와
    이중으로 감쇠되는데, 위아래(vy)는 원래 좌우(hx)보다 신호 진폭이 작아서
    이중 스무딩에 특히 취약하다 (좌우는 멀쩡한데 위아래만 둔해지는 원인이었음).

    (참고) 캘리브레이션은 이 스무딩을 거치지 않은 원본 특징값으로 W 를 학습한다.
    실행 중에는 머리 위치(nx, ny, pitch, yaw)만 이 필터를 거친 값이 들어간다.
    머리는 천천히 움직여서 차이가 작지만, 알고 있어야 하는 불일치다.
    """

    def __init__(self, alpha=0.35):
        self.alpha = alpha
        self.prev_head = None

    def __call__(self, f):
        hx, vy, nx, ny, op, pitch, yaw = f
        head = np.array([nx, ny, pitch, yaw])
        if self.prev_head is None:
            self.prev_head = head.copy()
        else:
            self.prev_head = self.prev_head + self.alpha * (head - self.prev_head)
        nx_s, ny_s, pitch_s, yaw_s = self.prev_head
        return np.array([hx, vy, nx_s, ny_s, op, pitch_s, yaw_s])
