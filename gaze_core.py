# -*- coding: utf-8 -*-
"""
gaze_core.py — 원본 gaze_tracker.py 중 "캘리브레이션 + 시선 좌표 계산" 부분만 옮긴 파일

데모 버전은 원본 기능 중 캘리브레이션만 사용합니다. 그래서 이 파일에는
    프레임 → 특징값(홍채 위치, 고개 각도 등) → 화면 좌표
로 가는 계산과, 캘리브레이션 판정에 쓰는 설정값만 있습니다.
윙크 클릭(WinkDetector), 실제 마우스 이동(pyautogui, DwellTracker)은 데모에서 쓰지 않아 뺐습니다.

원본과 달라진 점은 딱 하나입니다.
    원본: SCREEN_W, SCREEN_H = pyautogui.size() 로 화면 크기를 고정
    데모: predict_norm()이 0~1 비율 좌표를 돌려주고, 화면 크기는 Qt 쪽에서 곱합니다.
pyautogui를 import하면 Windows에서 프로그램 전체의 화면 배율(DPI) 처리 방식이 바뀌어
PyQt 창들의 좌표가 어긋날 수 있어서, 데모에서는 pyautogui를 아예 쓰지 않습니다.
나머지 함수(eye_feature, estimate_head_pose, extract_features, design, fit,
FeatureSmoother, Smoother)는 원본 그대로입니다.
"""
import math
from pathlib import Path

import cv2
import numpy as np

CALIB_FILE = Path("calibration.npz")

# ---- 설정 (원본과 동일) ---------------------------------------------------
GRID_COLS, GRID_ROWS = 3, 3   # 캘리브레이션 점 개수 (3x3 = 9점)
MARGIN = 0.07                 # 화면 가장자리 여백 비율
BLINK_THRESHOLD = 0.18        # 캘리브레이션 중 눈 높이/너비 비율이 이보다 작은 프레임은 버림

VALID_SETTLE_SEC = 0.3        # 검증(홀드아웃) 단계는 훨씬 짧게 진행
VALID_COLLECT_SEC = 0.3

OPEN_RATIO = 0.70             # 평소 대비 이 비율보다 크게 떠 있어야 '눈 뜬 상태' (깜빡임 중 커서 고정용)
SWAP_LR = False               # 왼쪽/오른쪽이 반대로 인식되면 True (거울 모드 웹캠 등)

# 캘리브레이션 점 확정(빨강→초록) 기준 — 눈동자는 어차피 계속 미세하게 떨리므로,
# 일정 시간 흔들림 없이 안정된 경우에만 그 구간의 중앙값(median) 하나로 고정해 사용한다.
STABLE_SEC = 2.0              # 이 시간 이상 연속으로 안정돼야 확정 ("두더지를 2초동안" 문구에 맞춰 2초)
STABLE_WINDOW_SEC = 0.4       # 순간 흔들림을 판단하는 슬라이딩 윈도우 길이
STABLE_MIN_SAMPLES = 2        # 윈도우 안에 최소 이 프레임 수는 있어야 판단 (저프레임 웹캠 대응)
STABLE_HX_TOL = 0.06          # 이 폭 안에서만 hx가 움직여야 "안정"으로 판단
STABLE_VY_TOL = 0.045         # vy 허용 폭
MAX_WAIT_SEC = 12.0           # 이 시간 안에 확정 안 되면 지금까지 데이터로 강제 진행 (무한 대기 방지)

POSE_SEC = 1.5                # 고개 자세 변화 단계: 한 점당 진행 시간 (원본 sec=1.5)
POSE_SETTLE_SEC = 0.3         # 점이 나온 직후 반응 지연 구간은 수집하지 않음 (원본 elapsed > 0.3)

# MediaPipe FaceMesh 랜드마크 (refine_landmarks=True일 때 468~477이 홍채)
# (이미지 기준 왼쪽 눈꼬리, 오른쪽 눈꼬리, 윗눈꺼풀, 아랫눈꺼풀, 홍채 중심+경계점들)
EYE_R = (33, 133, 159, 145, (468, 469, 470, 471, 472))    # 사용자의 오른쪽 눈 (원본 영상에서는 화면 왼쪽에 보임)
EYE_L = (362, 263, 386, 374, (473, 474, 475, 476, 477))   # 사용자의 왼쪽 눈
NOSE = 1


# ---- 캘리브레이션 지점 (원본 calibrate()와 같은 위치·순서) -----------------
def grid_targets():
    """격자 9점 — 지그재그 순서로 시선 이동 최소화."""
    xs = np.linspace(MARGIN, 1 - MARGIN, GRID_COLS)
    ys = np.linspace(MARGIN, 1 - MARGIN, GRID_ROWS)
    targets = []
    for r, y in enumerate(ys):
        row = xs if r % 2 == 0 else xs[::-1]
        targets += [(float(x), float(y)) for x in row]
    return targets


def pose_targets():
    """고개 자세 변화 3곳 — 중앙/위/아래 (위아래를 우선)."""
    return [(0.5, 0.5), (0.5, MARGIN), (0.5, 1 - MARGIN)]


def validation_targets():
    """홀드아웃 검증 2곳 — 격자 사이의 새 지점 (학습에는 사용하지 않음)."""
    xs = np.linspace(MARGIN, 1 - MARGIN, GRID_COLS)
    ys = np.linspace(MARGIN, 1 - MARGIN, GRID_ROWS)
    val_xs = (xs[:-1] + xs[1:]) / 2
    val_ys = (ys[:-1] + ys[1:]) / 2
    return [(float(val_xs[0]), float(val_ys[0])), (float(val_xs[-1]), float(val_ys[-1]))]


# ---- 특징 추출 (원본 그대로) ------------------------------------------------
def eye_feature(lm, w, h, idx):
    """눈 하나에서 (수평 홍채 위치, 수직 홍채 위치, 눈 개폐 비율) 계산."""
    left, right, top, bottom, iris_idxs = idx
    pt = lambda i: np.array([lm[i].x * w, lm[i].y * h])
    p_l, p_r, p_t, p_b = map(pt, (left, right, top, bottom))
    p_i = np.mean([pt(i) for i in iris_idxs], axis=0)   # 중심점 하나 대신 경계점까지 평균 → 노이즈 감소

    axis = p_r - p_l
    width = np.linalg.norm(axis)
    u = axis / width                      # 눈꼬리 방향 단위벡터
    normal = np.array([-u[1], u[0]])      # 그에 수직인 벡터 (아래쪽)

    hx = np.dot(p_i - p_l, u) / width - 0.5                  # 약 -0.5 ~ 0.5
    vy = np.dot(p_i - (p_l + p_r) / 2, normal) / width       # 눈 중앙선 기준 offset
    openness = np.linalg.norm(p_t - p_b) / width
    return hx, vy, openness


# ---- 머리 자세(피치/요) 추정 (원본 그대로) ----------------------------------
# 일반적인 정면 얼굴의 3D 근사 모델 (임의 단위) — 코끝을 원점으로 둔 표준적인 값
_HEAD_MODEL_3D = np.array([
    (0.0, 0.0, 0.0),          # 코끝 (landmark 1)
    (0.0, -330.0, -65.0),     # 턱 (landmark 152)
    (-225.0, 170.0, -135.0),  # 왼쪽 눈꼬리 (landmark 33)
    (225.0, 170.0, -135.0),   # 오른쪽 눈꼬리 (landmark 263)
    (-150.0, -150.0, -125.0),  # 입 왼쪽 끝 (landmark 61)
    (150.0, -150.0, -125.0),   # 입 오른쪽 끝 (landmark 291)
], dtype=np.float64)
_HEAD_LM_IDX = (1, 152, 33, 263, 61, 291)


def estimate_head_pose(lm, w, h):
    """
    solvePnP로 머리의 실제 회전 각도(피치=상하 끄덕임, 요=좌우 회전)를 추정한다.
    코 랜드마크 하나의 위치(nx, ny)만으로는 머리가 '어디 있는지'만 알 수 있고
    '어느 각도로 기울었는지'는 알 수 없는데, 실제로 화면 위/아래를 볼 때는
    고개도 같이 끄덕이듯 움직이므로 이 각도 정보를 시선 보정에 함께 사용한다.
    실패하면 (0.0, 0.0)을 반환한다.
    """
    image_points = np.array([(lm[i].x * w, lm[i].y * h) for i in _HEAD_LM_IDX], dtype=np.float64)
    focal_length = w
    center = (w / 2, h / 2)
    camera_matrix = np.array([
        [focal_length, 0, center[0]],
        [0, focal_length, center[1]],
        [0, 0, 1],
    ], dtype=np.float64)
    dist_coeffs = np.zeros((4, 1))

    ok, rvec, _ = cv2.solvePnP(_HEAD_MODEL_3D, image_points, camera_matrix, dist_coeffs,
                               flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        return 0.0, 0.0

    rmat, _ = cv2.Rodrigues(rvec)
    sy = math.sqrt(rmat[0, 0] ** 2 + rmat[1, 0] ** 2)
    singular = sy < 1e-6
    pitch = math.atan2(rmat[2, 1], rmat[2, 2]) if not singular else math.atan2(-rmat[1, 2], rmat[1, 1])
    yaw = math.atan2(-rmat[2, 0], sy)
    return pitch, yaw   # 라디안 단위 (다른 특징값들과 스케일을 맞추기 위해 도(度) 변환하지 않음)


def extract_features(frame, face_mesh):
    """
    프레임 → ([홍채 x, 홍채 y, 코 x, 코 y, 눈꺼풀 벌어짐, 머리 피치, 머리 요],
              [왼눈 개폐, 오른눈 개폐]). 얼굴이 없으면 (None, None).
    눈꺼풀이 벌어진 정도(openness)는 사람이 위/아래를 볼 때 무의식적으로 같이 변하는
    경향이 있어, 위아래 시선 추정에 도움이 되는 보조 신호로 함께 사용한다.
    머리 피치/요는 코 위치(위치 정보)와 별개로 '고개가 실제로 얼마나 회전했는지'를
    직접 알려줘, 눈+고개가 같이 움직이는 실생활 상황을 더 잘 보정하게 해준다.
    """
    h, w = frame.shape[:2]
    result = face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    if not result.multi_face_landmarks:
        return None, None
    lm = result.multi_face_landmarks[0].landmark
    right = eye_feature(lm, w, h, EYE_R)
    left = eye_feature(lm, w, h, EYE_L)
    pitch, yaw = estimate_head_pose(lm, w, h)
    feat = np.array([(right[0] + left[0]) / 2, (right[1] + left[1]) / 2,
                     lm[NOSE].x, lm[NOSE].y, (right[2] + left[2]) / 2,
                     pitch, yaw])
    opens = np.array([left[2], right[2]])
    if SWAP_LR:
        opens = opens[::-1].copy()
    return feat, opens


# ---- 특징 → 화면 좌표 매핑 (2차 다항 + 머리 위치/눈꺼풀/머리각도 보정, 릿지 회귀) ----------
DESIGN_LEN = 19   # design() 벡터 길이 — 캘리브레이션 파일 호환성 검사에 사용


def design(f):
    hx, vy, nx, ny, op, pitch, yaw = f
    # nx, ny(고개/코 위치)와 hx, vy(눈동자 방향)의 교차항: 고개 위치 변화에 따른 패럴랙스 보정
    # op(눈꺼풀 벌어짐)과 vy의 교차항: 위아래 시선과 함께 변하는 눈꺼풀 정보를 추가 신호로 활용
    # pitch(고개 상하 각도)·yaw(고개 좌우 각도)와 vy/hx의 교차항: 눈+고개 동시 움직임 보정
    return np.array([
        1.0, hx, vy, hx * hx, vy * vy, hx * vy,
        nx, ny, nx * nx, ny * ny,
        hx * nx, vy * ny,
        op, op * op, op * vy,
        pitch, yaw, pitch * vy, yaw * hx,
    ])


def fit(features, targets, lam=1e-3):
    """[원본 그대로] targets는 0~1 비율 좌표 (tx, ty)."""
    A = np.array([design(f) for f in features])
    reg = lam * np.eye(A.shape[1])
    reg[0, 0] = 0
    return np.linalg.solve(A.T @ A + reg, A.T @ np.array(targets))


def predict_norm(W, f):
    """특징값 → 0~1 비율 좌표. (원본 predict()에서 화면 크기를 곱하기 직전 값)"""
    return design(f) @ W


def predict_px(W, f, screen_w, screen_h):
    """특징값 → 화면 픽셀 좌표. 원본 predict()와 같은 계산 (화면 크기만 인자로 받음)."""
    return predict_norm(W, f) * np.array([screen_w, screen_h])


class FeatureSmoother:
    """
    고개 위치(nx, ny)만 지수평활(EMA)로 부드럽게 만들고, 실제 시선 신호(hx, vy)는
    그대로 통과시킨다. hx/vy까지 여기서 스무딩하면 화면 좌표 단계의 Smoother와
    이중으로 감쇠되는데, 위아래(vy)는 원래 좌우(hx)보다 신호 진폭이 작아서
    이중 스무딩에 특히 취약하다 (좌우는 멀쩡한데 위아래만 둔해지는 원인이었음).
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


class Smoother:
    """
    움직임이 작을 땐 강하게, 클 땐 약하게 평활화 (떨림 억제 + 빠른 추종).
    화면 가로/세로 크기로 정규화한 거리를 사용 — 세로가 가로보다 짧다는 이유만으로
    위아래 움직임이 상대적으로 더 강하게 뭉개지는 것을 방지한다.
    (원본은 SCREEN_W/H를 직접 썼고, 데모는 화면 크기를 인자로 받는다)
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


class GazeSession:
    """
    [원본: main()의 while 루프 중 '시선 좌표 계산' 부분만]
    캘리브레이션 결과(W, base)로 매 프레임 화면 좌표를 계산한다.
    두 눈이 충분히 떠 있을 때만 갱신 → 깜빡임 중에는 None을 돌려줘서 커서가 튀지 않고 그 자리에 고정.
    """

    def __init__(self, W, base, screen_w, screen_h):
        self.W, self.base = W, base
        self.screen_w, self.screen_h = screen_w, screen_h
        self.feat_smoother = FeatureSmoother()
        self.smoother = Smoother(screen_w, screen_h)

    def process(self, feat, opens):
        if feat is None:
            return None
        ratio = opens / self.base
        if not (ratio > OPEN_RATIO).all():
            return None
        smoothed_feat = self.feat_smoother(feat)
        raw = np.clip(predict_px(self.W, smoothed_feat, self.screen_w, self.screen_h),
                      [0, 0], [self.screen_w - 1, self.screen_h - 1])
        return self.smoother(raw)


def save_calibration(W, base):
    np.savez(CALIB_FILE, W=W, base=base)


def load_calibration():
    """저장된 calibration.npz가 있고 지금 코드와 구조가 맞으면 (W, base), 아니면 None."""
    if not CALIB_FILE.exists():
        return None
    try:
        data = np.load(CALIB_FILE)
        if "base" in data.files and data["W"].shape[0] == DESIGN_LEN:
            return data["W"], data["base"]
    except Exception:
        pass
    return None
