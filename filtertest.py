import math
import random
import cv2
import numpy as np

# 가중치 평균필터
class LowPassFilter:
    def __init__(self):
        self.y = self.s = None

    def filter(self, value, alpha):
        if self.s is None:
            self.s = value
        else:
            s = alpha * value + (1.0 - alpha) * self.s
        self.y = value
        self.s = s
        return s

# 원유로 필터 입력값의 변화량에 따라 컷오프 주파수를 조절
class OneEuroFilter1D:
    def __init__(self, freq, mincutoff=1.0, beta=0.0, dcutoff=1.0):
        self.freq = float(freq)
        self.mincutoff = float(mincutoff)
        self.beta = float(beta)
        self.dcutoff = float(dcutoff)
        self.x_prev = None
        self.lpf = LowPassFilter()
        self.d_lpf = LowPassFilter()

    def _alpha(self, cutoff):
        te = 1.0 / self.freq
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / te)

    def update(self, x):
        if self.x_prev is None:
            self.x_prev = x
            return x
        dx = (x - self.x_prev) * self.freq
        edx = self.d_lpf.filter(dx, self._alpha(self.dcutoff))
        cutoff = self.mincutoff + self.beta * abs(edx)
        filtered_x = self.lpf.filter(x, self._alpha(cutoff))
        self.x_prev = filtered_x
        return filtered_x

    def reset(self, value):
        self.x_prev = value
        self.lpf.s = None
        self.d_lpf.s = None

# 이상치 제거 + 원유로 필터 + EMA 필터를 결합한 시선 안정화 클래스
class GazeStabilizer:
    def __init__(self, fps=60.0):
        self.max_jump_distance = 250.0  # 허용 거리
        self.prev_valid_x = None
        self.prev_valid_y = None

        self.outlier_count = 0
        self.max_outlier_frames = 3

        # 원유로 필터 (떨림 제어 + 지연 방지)
        self.euro_x = OneEuroFilter1D(freq=fps, mincutoff=0.8, beta=0.008)
        self.euro_y = OneEuroFilter1D(freq=fps, mincutoff=0.8, beta=0.008)

        # 최종 EMA 필터
        self.ema_alpha = 0.85
        self.final_x = None
        self.final_y = None

    # 메인문에서 한 번에 가중치 설정을 일괄 변경하는 메서드
    def set_parameters(self, min_cutoff, beta, ema_alpha, max_jump_distance=None, max_outlier_frames=None):
        """
        필터의 주요 가중치들을 한 번에 일괄 셋팅합니다.
        """
        # 1. 원유로 필터 min_cutoff 설정 (가로/세로 동시 적용)
        self.euro_x.min_cutoff = float(min_cutoff)
        self.euro_y.min_cutoff = float(min_cutoff)

        # 2. 원유로 필터 beta 설정 (가로/세로 동시 적용)
        self.euro_x.beta = float(beta)
        self.euro_y.beta = float(beta)

        # 3. EMA Alpha 설정
        self.ema_alpha = float(ema_alpha)

        # 4. 선택적 인자 설정 (필요할 때만 변경)
        if max_jump_distance is not None:
            self.max_jump_distance = float(max_jump_distance)
        if max_outlier_frames is not None:
            self.max_outlier_frames = int(max_outlier_frames)

    def update(self, raw_x, raw_y):
        if raw_x is None or raw_y is None:
            return self.final_x, self.final_y

        # 1단계: 이상치(Outlier) 체크
        if self.prev_valid_x is not None:
            dist_sq = (raw_x - self.prev_valid_x) ** 2 + (raw_y - self.prev_valid_y) ** 2
            if dist_sq > self.max_jump_distance ** 2:
                self.outlier_count += 1

                if self.outlier_count < self.max_outlier_frames:
                    return self.final_x, self.final_y
                else:
                    self.prev_valid_x = raw_x
                    self.prev_valid_y = raw_y
                    self.outlier_count = 0
                    self.euro_x.x_prev = raw_x
                    self.euro_y.x_prev = raw_y
                    self.final_x = raw_x
                    self.final_y = raw_y
                    return self.final_x, self.final_y
            else:
                self.outlier_count = 0

        self.prev_valid_x, self.prev_valid_y = raw_x, raw_y

        # 2단계: 원유로 필터
        f_x = self.euro_x.update(raw_x)
        f_y = self.euro_y.update(raw_y)

        # 3단계: 최종 EMA
        if self.final_x is None:
            self.final_x, self.final_y = f_x, f_y
        else:
            self.final_x = self.ema_alpha * f_x + (1.0 - self.ema_alpha) * self.final_x
            self.final_y = self.ema_alpha * f_y + (1.0 - self.ema_alpha) * self.final_y

        return self.final_x, self.final_y