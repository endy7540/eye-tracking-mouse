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

# 실행한 폴더(cmd 위치)가 아니라 이 파이썬 파일이 있는 폴더에 저장/불러오기 → 어디서 실행해도 같은 파일 사용
CALIB_FILE = Path(__file__).resolve().parent / "calibration.npz"

# ---- 설정 (원본과 동일) ---------------------------------------------------
GRID_COLS, GRID_ROWS = 4, 4   # 캘리브레이션 점 개수 (4x4 = 16점). 시간이 너무 길면 3, 3으로 (9점)
MARGIN = 0.07                 # 화면 가장자리 여백 비율
BLINK_THRESHOLD = 0.18        # 캘리브레이션 중 눈 높이/너비 비율이 이보다 작은 프레임은 버림

VALID_SETTLE_SEC = 0.4        # 검증(홀드아웃): 두더지가 나온 뒤 눈이 옮겨갈 시간
VALID_COLLECT_SEC = 0.5       # 검증 데이터 모으는 시간 (조금 늘려서 오차 측정이 덜 흔들리게)

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

POSE_SEC = 2.0                # 고개 자세 변화 단계: 한 점당 진행 시간 (원본 1.5 → 점이 늘어 2.0)
POSE_SETTLE_SEC = 0.3         # 점이 나온 직후 반응 지연 구간은 수집하지 않음 (원본 elapsed > 0.3)

# [추가] 따라 보기(스무스 퍼슛) 단계 — 두더지가 화면을 8자 모양으로 천천히 돌아다니고, 눈으로 따라가는 동안
# 매 프레임을 "그 순간 두더지 위치"로 학습. 격자 점 사이사이 빈 곳까지 데이터가 촘촘히 채워짐.
PURSUIT_SEC = 14.0            # 따라 보기 전체 시간 (8자 한 바퀴)
PURSUIT_SETTLE_SEC = 1.0      # 처음 이 시간은 눈이 두더지를 잡는 중이라 수집하지 않음
PURSUIT_LAG_SEC = 0.10        # 카메라·눈의 반응 지연 보정: 프레임 시각보다 이만큼 앞선 두더지 위치를 정답으로 사용
PURSUIT_SEGMENT_SEC = 1.0     # 가중치 계산 단위: 1초 구간 하나를 두더지 한 마리처럼 취급

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
    """고개 자세 변화 5곳 — 중앙/위/아래/왼쪽/오른쪽.
    [수정] 예전엔 3곳이 모두 가운데 세로줄(x=0.5)이라 고개를 좌우로 돌린 상태의 데이터가 부족했음."""
    return [(0.5, 0.5), (0.5, MARGIN), (0.5, 1 - MARGIN), (MARGIN, 0.5), (1 - MARGIN, 0.5)]


def pursuit_pos(elapsed):
    """따라 보기 단계에서 elapsed초 시점의 두더지 위치 (0~1 비율 좌표).
    가로 1번·세로 2번 왕복하는 8자(리사주) 곡선 — 가운데에서 출발해 화면 네 귀퉁이 근처를 모두 지나감."""
    e = min(max(elapsed, 0.0), PURSUIT_SEC)
    w = 2 * math.pi * e / PURSUIT_SEC
    a = 0.5 - MARGIN
    return 0.5 + a * math.sin(w), 0.5 + a * math.sin(2 * w)


def validation_targets():
    """홀드아웃 검증 4곳 — 격자 사이의 새 지점, 화면 네 방향 (학습에는 사용하지 않음).
    [수정] 2곳(대각선 두 끝)만 재면 한쪽 방향의 오차를 놓칠 수 있어 4곳으로 늘림."""
    xs = np.linspace(MARGIN, 1 - MARGIN, GRID_COLS)
    ys = np.linspace(MARGIN, 1 - MARGIN, GRID_ROWS)
    vx0, vx1 = float((xs[0] + xs[1]) / 2), float((xs[-2] + xs[-1]) / 2)
    vy0, vy1 = float((ys[0] + ys[1]) / 2), float((ys[-2] + ys[-1]) / 2)
    return [(vx0, vy0), (vx1, vy0), (vx1, vy1), (vx0, vy1)]


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
    # [수정] 3D 모델은 y가 위쪽, 영상은 y가 아래쪽이라 정면을 볼 때 pitch가 0이 아니라 ±π(180도) 근처로 나옴.
    # 그대로 두면 고개를 1도만 끄덕여도 +3.12 ↔ -3.12로 값이 뒤집혀서 학습/스무딩이 망가짐.
    # → 180도를 빼서 정면 = 0 근처가 되도록 다시 감쌈 (고개 숙이면 +, 들면 -).
    pitch = (pitch + 2 * math.pi) % (2 * math.pi) - math.pi
    yaw = math.atan2(-rmat[2, 0], sy)
    return pitch, yaw   # 라디안 단위 (다른 특징값들과 스케일을 맞추기 위해 도(度) 변환하지 않음)


def extract_features(frame, face_mesh, return_points=False):
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
        return (None, None, None) if return_points else (None, None)
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
    if return_points:   # [추가] 상태 확인 창의 카메라 미리보기에 그릴 눈 점들 (눈꼬리·눈꺼풀 = 테두리, 홍채 = 가운데)
        pts = {"eye": [(lm[i].x * w, lm[i].y * h) for e in (EYE_R, EYE_L) for i in e[:4]],
               "iris": [(lm[i].x * w, lm[i].y * h) for e in (EYE_R, EYE_L) for i in e[4]]}
        return feat, opens, pts
    return feat, opens


# ---- 특징 → 화면 좌표 매핑 (2차 다항 + 머리 위치/눈꺼풀/머리각도 보정, 릿지 회귀) ----------
DESIGN_LEN = 16   # design() 벡터 길이 — 캘리브레이션 파일 호환성 검사에 사용
CALIB_VERSION = 3  # 3: 계산식에서 고개 제곱항을 뺌 + 자동 보정 데이터 저장. 예전 파일은 다시 캘리브레이션해야 함
RANGE_PAD = 0.3    # 학습 때 본 눈동자 값 범위를 이 비율만큼 넓힌 곳까지만 허용 (그 밖은 잘라냄)


def design(f):
    hx, vy, nx, ny, op, pitch, yaw = f
    # nx, ny(고개/코 위치)와 hx, vy(눈동자 방향)의 교차항: 고개 위치 변화에 따른 패럴랙스 보정
    # op(눈꺼풀 벌어짐)과 vy의 교차항: 위아래 시선과 함께 변하는 눈꺼풀 정보를 추가 신호로 활용
    # pitch(고개 상하 각도)·yaw(고개 좌우 각도)와 vy/hx의 교차항: 눈+고개 동시 움직임 보정
    # [수정] nx², ny², op² 제거: 제곱항은 학습 때 없던 자세가 들어오면 곡선을 따라 값이 폭주해서
    #        "자세가 조금만 틀어져도 커서가 튀는" 주원인이었음. 고개 관련 항은 모두 1차(직선)로만 둠.
    return np.array([
        1.0, hx, vy, hx * hx, vy * vy, hx * vy,
        nx, ny,
        hx * nx, vy * ny,
        op, op * vy,
        pitch, yaw, pitch * vy, yaw * hx,
    ])


def feature_ranges(features, pad=RANGE_PAD):
    """학습 데이터의 특징값 범위 (lo, hi). 범위 폭의 pad배만큼 양쪽으로 여유를 줌."""
    F = np.asarray(features, dtype=float)
    lo, hi = F.min(axis=0), F.max(axis=0)
    span = np.maximum(hi - lo, 1e-3)
    return lo - pad * span, hi + pad * span


def clip_feature(f, ranges):
    """[추가] 눈동자 값(hx, vy)이 학습 때 본 범위를 크게 벗어나면 범위 끝으로 잘라냄.
    hx², vy² 같은 제곱항은 범위 밖에서 곡선이 꺾여 커서가 엉뚱한 쪽으로 튈 수 있어서.
    고개 값(nx, ny, pitch, yaw)은 자르지 않음 — 이제 고개 항은 모두 직선(1차)이라 범위 밖에서도
    자연스럽게 이어지고, 잘라버리면 오히려 기댄 자세의 보정이 멈춰서 더 나빠짐 (가상 데이터로 확인).
    범위는 자동 보정으로 새 데이터가 쌓이면 같이 넓어짐."""
    if ranges is None:
        return f
    out = np.array(f, dtype=float)
    out[:2] = np.clip(out[:2], ranges[0][:2], ranges[1][:2])
    return out


def fit(features, targets, lam=1e-2, weights=None):
    """targets는 0~1 비율 좌표 (tx, ty). 결과 W는 예전과 똑같이 design(f) @ W 로 사용.

    [수정 1] weights: 샘플마다 중요도. 캘리브레이션 점(두더지)마다 모인 프레임 수가 크게 달라서
             (격자 1개 vs 자세변화 수십 개) 그대로 학습하면 프레임이 많은 점이 결과를 독차지함.
             → 두더지 한 마리당 합이 같아지도록 가중치를 줌.
    [수정 2] 표준화: 특징값마다 크기가 제각각이라(hx²≈0.01, pitch≈0.1 …) 릿지(lam)가
             어떤 항은 거의 안 누르고 어떤 항은 과하게 누름. 평균 0, 표준편차 1로 맞춘 뒤 풀고,
             마지막에 원래 단위로 되돌려서 W 모양/사용법은 그대로 유지."""
    A = np.array([design(f) for f in features])
    Y = np.array(targets, dtype=float)
    w = np.ones(len(A)) if weights is None else np.asarray(weights, dtype=float)
    w = w / w.sum()

    X = A[:, 1:]                                  # 상수항(1.0) 제외
    mu = w @ X
    sd = np.sqrt(w @ (X - mu) ** 2)
    sd[sd < 1e-9] = 1.0                           # 변화가 없는 항은 그대로
    Z = np.hstack([np.ones((len(A), 1)), (X - mu) / sd])

    Zw = Z * w[:, None]
    reg = lam * np.eye(Z.shape[1])
    reg[0, 0] = 0
    Ws = np.linalg.solve(Z.T @ Zw + reg, Zw.T @ Y)

    W = np.empty_like(Ws)                         # 표준화 전 단위로 되돌림
    W[1:] = Ws[1:] / sd[:, None]
    W[0] = Ws[0] - (mu / sd) @ Ws[1:]
    return W


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

    def __init__(self, W, base, screen_w, screen_h, ranges=None, adaptive=None):
        self.W, self.base = W, base
        self.ranges = ranges          # 특징값 허용 범위 (clip_feature)
        self.adaptive = adaptive      # 자동 보정기 (adaptive.py) — 눈 뜬 프레임을 계속 넘겨줌
        self.screen_w, self.screen_h = screen_w, screen_h
        self.feat_smoother = FeatureSmoother()
        self.smoother = Smoother(screen_w, screen_h)

    def set_model(self, W, ranges):
        """자동 보정으로 새로 학습된 W와 범위로 교체 (커서 위치는 Smoother가 부드럽게 이어줌)."""
        self.W, self.ranges = W, ranges

    def process(self, feat, opens, t=None):
        if feat is None:
            return None
        ratio = opens / self.base
        if not (ratio > OPEN_RATIO).all():
            return None
        if self.adaptive is not None and t is not None:
            self.adaptive.add_frame(t, feat)      # 클릭 순간 "직전에 어디를 보고 있었는지" 찾을 수 있도록 보관
        smoothed_feat = clip_feature(self.feat_smoother(feat), self.ranges)
        raw = np.clip(predict_px(self.W, smoothed_feat, self.screen_w, self.screen_h),
                      [0, 0], [self.screen_w - 1, self.screen_h - 1])
        return self.smoother(raw)


def save_calibration(W, base, extra=None):
    """extra: 자동 보정용 데이터 (두더지 캘리브레이션 원본 + 사용 중 모은 샘플). adaptive.to_arrays() 결과."""
    np.savez(CALIB_FILE, W=W, base=base, ver=CALIB_VERSION, **(extra or {}))


def load_calibration():
    """저장된 calibration.npz가 있고 지금 코드와 구조가 맞으면 {이름: 배열} 딕셔너리, 아니면 None."""
    # 못 쓰는 경우 이유를 터미널에 알려줌 (--skip-calib인데 캘리브레이션이 시작되는 이유를 알 수 있게)
    if not CALIB_FILE.exists():
        print(f"[캘리브레이션] 저장된 파일이 없어요: {CALIB_FILE}")
        return None
    try:
        data = np.load(CALIB_FILE)
        ver = int(data["ver"]) if "ver" in data.files else 0
        if ver != CALIB_VERSION:
            print(f"[캘리브레이션] 예전 버전 파일이라 쓸 수 없어요 (파일 {ver} / 지금 {CALIB_VERSION}) — 한 번 새로 해주세요")
            return None
        if data["W"].shape[0] != DESIGN_LEN or "anchor_feats" not in data.files or "base" not in data.files:
            print("[캘리브레이션] 파일 구조가 지금 코드와 달라요 — 한 번 새로 해주세요")
            return None
        return {k: data[k] for k in data.files}
    except Exception as e:
        print(f"[캘리브레이션] 파일을 읽지 못했어요: {e}")
        return None
