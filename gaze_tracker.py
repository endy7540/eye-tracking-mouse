"""
gaze_tracker.py — 웹캠 기반 실시간 홍채(시선) 추적 → 모니터 좌표 출력 + 좌/우 윙크 구분

설치:   pip install opencv-python mediapipe numpy pyautogui
실행:   python gaze_tracker.py                 (처음 실행 시 자동으로 캘리브레이션)
        python gaze_tracker.py --recalibrate   (캘리브레이션 다시 하기)

조작키: M = 실제 마우스 제어 ON/OFF,  C = 재캘리브레이션,  Q / ESC = 종료
윙크:   왼쪽 눈만 감으면 LEFT, 오른쪽 눈만 감으면 RIGHT 이벤트 발생 ('왼쪽/오른쪽'은 사용자 본인 기준)
        M이 ON이면 각각 왼쪽 클릭 / 오른쪽 클릭까지 실행. 자연스러운 깜빡임(양쪽 동시)은 무시.

캘리브레이션: 점을 볼 때 바깥 원은 빨간색 — 3초 이상 흔들림 없이 안정적으로 봐야 초록색으로
바뀌며 그 점이 확정된다 (중간에 흔들리면 처음부터 다시). 확정 순간의 안정 구간 데이터를
중앙값(median) 하나로 고정해서 사용해, 눈동자의 미세한 떨림이 학습 데이터에 그대로 섞이지
않게 한다.

캘리브레이션 중에는 전체화면 검은 창이 뜨지만, 끝나면 화면 좌상단의 작은 상태창으로 줄어들어
그 아래에 있는 실제 프로그램(브라우저 등)을 그대로 보고 조작할 수 있습니다.

한 곳을 일정 시간(기본 0.45초) 이상 안정적으로 보고 있어야 실제 마우스 커서가 그 위치로
이동합니다(M이 ON일 때) — 계속 따라다니지 않아 떨림의 영향을 덜 받습니다.
"""
import argparse
import math
import time
from collections import deque
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
import pyautogui
from PIL import Image, ImageDraw, ImageFont

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

SCREEN_W, SCREEN_H = pyautogui.size()
CALIB_FILE = Path("calibration.npz")
WIN = "gaze"
DEBUG_W, DEBUG_H = 460, 230   # 실사용 중 표시할 작은 상태창 크기


def set_window_fullscreen():
    """캘리브레이션용: 화면 전체를 덮는 창으로 전환. 창을 새로 만들어서 전환 실패를 방지한다."""
    cv2.destroyWindow(WIN)
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.waitKey(1)   # 창 전환이 실제로 반영되도록 이벤트 루프 한 번 처리


def set_window_debug():
    """
    실사용 중: 다른 프로그램(브라우저 등)을 조작할 수 있도록 작은 상태창으로 전환.
    일부 환경에서는 fullscreen → normal 전환이 안 먹혀 화면이 새까맣게 남는 문제가 있어,
    같은 이름의 창을 완전히 닫고 새로 작은 창으로 만든다 (더 확실하게 동작).
    """
    cv2.destroyWindow(WIN)
    cv2.waitKey(1)
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, DEBUG_W, DEBUG_H)
    cv2.moveWindow(WIN, 20, 20)
    cv2.waitKey(1)
    try:  # Windows에서 항상 위에 뜨도록 (실패해도 무시)
        import ctypes
        hwnd = ctypes.windll.user32.FindWindowW(None, WIN)
        if hwnd:
            HWND_TOPMOST, SWP_NOMOVE, SWP_NOSIZE = -1, 0x0002, 0x0001
            ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
    except Exception:
        pass


_KR_FONT_CACHE = {}
_KR_FONT_CANDIDATES = [
    "C:/Windows/Fonts/malgun.ttf",   # 맑은 고딕 (Windows 기본 한글 폰트)
    "C:/Windows/Fonts/malgunbd.ttf",
    "malgun.ttf",
]


def _get_kr_font(size):
    if size not in _KR_FONT_CACHE:
        font = None
        for path in _KR_FONT_CANDIDATES:
            try:
                font = ImageFont.truetype(path, size)
                break
            except Exception:
                continue
        if font is None:                        # 폰트를 못 찾으면 각진 기본 폰트로라도 표시
            font = ImageFont.load_default()
        _KR_FONT_CACHE[size] = font
    return _KR_FONT_CACHE[size]


def put_text_kr(canvas, text, org, font_size=32, color=(200, 200, 200)):
    """
    cv2.putText는 한글(유니코드)을 지원하지 않아 물음표로 깨진다.
    PIL로 한글을 그려서 canvas(BGR numpy 배열)에 합성한다. org는 텍스트의 좌상단 좌표.
    """
    pil_img = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    b, g, r = color                              # 기존 코드와 동일하게 BGR 순서로 색을 받는다
    draw.text(org, text, font=_get_kr_font(font_size), fill=(r, g, b))
    canvas[:] = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    return canvas

# ---- 설정 -------------------------------------------------------------
GRID_COLS, GRID_ROWS = 3, 3   # 캘리브레이션 점 개수 (3x3 = 9점) — 우선 기본적인 캘리브레이션
MARGIN = 0.07                 # 화면 가장자리 여백 비율
BLINK_THRESHOLD = 0.18        # 캘리브레이션 중 눈 높이/너비 비율이 이보다 작은 프레임은 버림

VALID_SETTLE_SEC = 0.3        # 검증(홀드아웃) 단계는 훨씬 짧게 진행
VALID_COLLECT_SEC = 0.3

# 윙크 판정 (각 눈의 '평소 뜬 상태 대비 개폐 비율' 기준)
CLOSE_RATIO = 0.50            # 이보다 작아지면 그 눈은 "감김"
OPEN_RATIO = 0.70             # 이보다 커지면 그 눈은 "뜸" (히스테리시스로 떨림 방지)
WINK_MIN_SEC = 0.25           # 한쪽 눈만 이 시간 이상 감고 있어야 윙크로 인정
WINK_COOLDOWN = 0.6           # 윙크 이벤트 사이 최소 간격
SWAP_LR = False               # 왼쪽/오른쪽이 반대로 인식되면 True (거울 모드 웹캠 등)

# 응시(dwell) 기반 커서 이동 — 계속 따라다니지 않고, 한 곳을 일정 시간 이상 안정적으로
# 보고 있을 때만 실제 마우스 커서를 그쪽으로 이동시켜 떨림의 영향을 줄인다.
DWELL_RADIUS_PX = 45.0        # 이 반경 안에 머물면 '같은 곳을 계속 보고 있다'고 판단
DWELL_TIME_SEC = 0.45         # 이 시간 이상 머물러야 커서가 실제로 이동

# 캘리브레이션 점 확정(빨강→초록) 기준 — 눈동자는 어차피 계속 미세하게 떨리므로,
# 일정 시간 흔들림 없이 안정된 경우에만 그 구간의 중앙값(median) 하나로 고정해 사용한다.
STABLE_SEC = 1.5              # 이 시간 이상 연속으로 안정돼야 확정(초록색)
STABLE_WINDOW_SEC = 0.4       # 순간 흔들림을 판단하는 슬라이딩 윈도우 길이
STABLE_MIN_SAMPLES = 2        # 윈도우 안에 최소 이 프레임 수는 있어야 판단 (저프레임 웹캠 대응)
STABLE_HX_TOL = 0.06          # 이 폭 안에서만 hx가 움직여야 "안정"으로 판단
STABLE_VY_TOL = 0.045         # vy 허용 폭
MAX_WAIT_SEC = 12.0           # 이 시간 안에 확정 안 되면 지금까지 데이터로 강제 진행 (무한 대기 방지)

# MediaPipe FaceMesh 랜드마크 (refine_landmarks=True일 때 468~477이 홍채)
# (이미지 기준 왼쪽 눈꼬리, 오른쪽 눈꼬리, 윗눈꺼풀, 아랫눈꺼풀, 홍채 중심+경계점들)
EYE_R = (33, 133, 159, 145, (468, 469, 470, 471, 472))    # 사용자의 오른쪽 눈 (원본 영상에서는 화면 왼쪽에 보임)
EYE_L = (362, 263, 386, 374, (473, 474, 475, 476, 477))   # 사용자의 왼쪽 눈
NOSE = 1


# ---- 특징 추출 --------------------------------------------------------
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


# ---- 머리 자세(피치/요) 추정 -------------------------------------------
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
    A = np.array([design(f) for f in features])
    reg = lam * np.eye(A.shape[1])
    reg[0, 0] = 0
    return np.linalg.solve(A.T @ A + reg, A.T @ np.array(targets))


def predict(W, f):
    return design(f) @ W * np.array([SCREEN_W, SCREEN_H])


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



class DwellTracker:
    """
    시선이 반경 DWELL_RADIUS_PX 안에서 DWELL_TIME_SEC 이상 머무르면 그 위치를
    '확정된 커서 위치'로 반환한다. 계속 따라다니는 대신, 안정적으로 응시했을 때만
    실제 마우스 커서를 이동시켜 미세한 떨림이 커서에 그대로 전달되지 않게 한다.
    """

    def __init__(self, radius=DWELL_RADIUS_PX, dwell_sec=DWELL_TIME_SEC):
        self.radius, self.dwell_sec = radius, dwell_sec
        self.anchor = None
        self.start = None
        self.committed = False

    def update(self, pos, now):
        """새 시선 위치를 반영하고, 방금 새로 확정된 위치가 있으면 반환 (없으면 None)."""
        if self.anchor is None:
            self.anchor, self.start, self.committed = pos.copy(), now, False
            return None
        d = np.linalg.norm(pos - self.anchor)
        if d > self.radius:                       # 다른 곳으로 시선 이동 → 새로 응시 시작
            self.anchor, self.start, self.committed = pos.copy(), now, False
            return None
        self.anchor = self.anchor * 0.9 + pos * 0.1   # 반경 안에서는 앵커를 살짝만 갱신
        if not self.committed and now - self.start >= self.dwell_sec:
            self.committed = True
            return self.anchor.copy()
        return self.anchor.copy() if self.committed else None

    def progress(self, now):
        """0~1 — 다음 커서 이동까지 얼마나 남았는지 (디버그 표시용)."""
        if self.anchor is None:
            return 0.0
        if self.committed:
            return 1.0
        return min((now - self.start) / self.dwell_sec, 1.0)


class Smoother:
    """
    움직임이 작을 땐 강하게, 클 땐 약하게 평활화 (떨림 억제 + 빠른 추종).
    화면 가로/세로 크기로 정규화한 거리를 사용 — 세로가 가로보다 짧다는 이유만으로
    위아래 움직임이 상대적으로 더 강하게 뭉개지는 것을 방지한다.
    """

    def __init__(self, min_a=0.05, max_a=0.55, dist=0.065):
        self.min_a, self.max_a, self.dist = min_a, max_a, dist
        self.prev = None
        self.scale = np.array([SCREEN_W, SCREEN_H], dtype=float)

    def __call__(self, p):
        if self.prev is None:
            self.prev = p
            return p
        d = np.linalg.norm((p - self.prev) / self.scale)   # 0~1 정규화 거리
        a = self.min_a + (self.max_a - self.min_a) * min(d / self.dist, 1.0)
        self.prev = self.prev + a * (p - self.prev)
        return self.prev


# ---- 윙크 감지 --------------------------------------------------------
class WinkDetector:
    """
    양쪽 눈의 개폐 비율(평소 대비)로 왼쪽/오른쪽 윙크를 구분한다.
    - 한쪽만 감기고 다른 쪽은 떠 있는 상태가 WINK_MIN_SEC 이상 유지되면 "left" / "right" 반환
    - 양쪽이 같이 감기는 일반 깜빡임은 상태가 'both'가 되어 무시됨
    - 한 번 발생한 윙크는 눈을 뜰 때까지 다시 발생하지 않음
    """

    def __init__(self):
        self.reset()
        self.last_fire = -1e9

    def reset(self):
        self.closed = [False, False]      # [왼눈, 오른눈]
        self.side, self.since, self.fired = None, 0.0, False

    def update(self, ratio, now):
        for i in range(2):
            if ratio[i] < CLOSE_RATIO:
                self.closed[i] = True
            elif ratio[i] > OPEN_RATIO:
                self.closed[i] = False

        left_closed, right_closed = self.closed
        side = None
        if left_closed and not right_closed:
            side = "left"
        elif right_closed and not left_closed:
            side = "right"

        if side != self.side:             # 상태가 바뀌면 타이머 리셋
            self.side, self.since, self.fired = side, now, False
            return None
        if (side and not self.fired and now - self.since >= WINK_MIN_SEC
                and now - self.last_fire >= WINK_COOLDOWN):
            self.fired, self.last_fire = True, now
            return side
        return None


# ---- 캘리브레이션 -----------------------------------------------------
def collect_point(cap, face_mesh, tx, ty, label):
    """
    점을 STABLE_SEC(기본 3초) 이상 흔들림 없이 안정적으로 봐야 확정되는 방식.
    - 바깥 원: 안정화 전에는 빨간색. 안정 유지 중에는 노란 진행 호가 채워지고,
      STABLE_SEC를 다 채우면 초록색으로 바뀌며 확정.
    - 중간에 흔들리거나 눈을 감으면(깜빡임) 타이머가 처음부터 다시 시작된다.
    - 확정되는 순간, 최근 안정 구간(STABLE_WINDOW_SEC)의 중앙값(median) 하나로 고정해
      대표 샘플로 사용한다 — 눈동자의 미세한 떨림이 학습 데이터에 그대로 섞이지 않게 한다.
    반환: [(feat, opens)] (원소 1개짜리 리스트), 또는 ESC로 취소 시 None.
    """
    center = (int(tx * SCREEN_W), int(ty * SCREEN_H))
    recent = deque()          # (t, feat, opens) — 최근 STABLE_WINDOW_SEC 동안의 유효 프레임만 유지
    stable_since = None
    fail_count = 0
    t_start = time.time()

    while True:
        ok, frame = cap.read()
        if not ok:
            fail_count += 1
            if fail_count > 60:   # 약 2초 이상 연속 실패해야만 진짜 오류로 판단
                raise RuntimeError("웹캠에서 프레임을 읽지 못했습니다.")
            time.sleep(0.03)
            continue
        fail_count = 0
        t = time.time()

        f, opens = extract_features(frame, face_mesh)
        valid = f is not None and opens.min() > BLINK_THRESHOLD
        if valid:
            recent.append((t, f, opens))
        while recent and t - recent[0][0] > STABLE_WINDOW_SEC:
            recent.popleft()

        stable_now = False
        if valid and len(recent) >= STABLE_MIN_SAMPLES:
            hxs = [r[1][0] for r in recent]
            vys = [r[1][1] for r in recent]
            stable_now = (max(hxs) - min(hxs) <= STABLE_HX_TOL) and (max(vys) - min(vys) <= STABLE_VY_TOL)

        if stable_now:
            if stable_since is None:
                stable_since = t
        else:
            stable_since = None

        elapsed_stable = (t - stable_since) if stable_since is not None else 0.0
        timed_out = (t - t_start) >= MAX_WAIT_SEC and len(recent) > 0   # 너무 오래 걸리면 강제 진행
        confirmed = elapsed_stable >= STABLE_SEC or timed_out

        canvas = np.zeros((SCREEN_H, SCREEN_W, 3), np.uint8)
        ring_color = (0, 255, 0) if confirmed else (0, 0, 255)
        cv2.circle(canvas, center, 24, ring_color, 3)
        cv2.circle(canvas, center, 5, (0, 0, 255), -1)
        if stable_since is not None and not confirmed:      # 안정 유지 중 진행률을 노란 호로 표시
            frac = min(elapsed_stable / STABLE_SEC, 1.0)
            cv2.ellipse(canvas, center, (34, 34), -90, 0, int(360 * frac), (0, 255, 255), 3)
        put_text_kr(canvas, f"점을 {STABLE_SEC:.0f}초간 안정적으로 봐주세요  ({label})  ESC: 취소",
                    (30, 25), 28, (200, 200, 200))
        cv2.imshow(WIN, canvas)
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            return None

        if confirmed:
            feats_arr = np.array([r[1] for r in recent])
            opens_arr = np.array([r[2] for r in recent])
            f_med = np.median(feats_arr, axis=0)
            o_med = np.median(opens_arr, axis=0)
            cv2.imshow(WIN, canvas)      # 초록 원이 잠깐 보이도록
            cv2.waitKey(250)
            return [(f_med, o_med)]


def show_pass_break(finished_pass, total_passes):
    """회차 사이에 자세를 바꾸도록 안내하는 대기 화면. 아무 키나 누르면 계속, ESC면 취소."""
    while True:
        canvas = np.zeros((SCREEN_H, SCREEN_W, 3), np.uint8)
        put_text_kr(canvas, f"{finished_pass}/{total_passes} 회차 완료!",
                    (60, SCREEN_H // 2 - 60), 46, (0, 255, 255))
        put_text_kr(canvas, "의자에 기대거나 고개를 살짝 움직인 뒤, 아무 키나 누르면 다음 회차 시작",
                    (60, SCREEN_H // 2 + 0), 30, (200, 200, 200))
        put_text_kr(canvas, "ESC: 취소", (60, SCREEN_H // 2 + 55), 26, (140, 140, 140))
        cv2.imshow(WIN, canvas)
        key = cv2.waitKey(30) & 0xFF
        if key == 27:
            return False
        if key != 255:
            return True


def show_message(lines, sub=None):
    """단순 안내 화면. 아무 키나 누르면 계속, ESC면 취소."""
    while True:
        canvas = np.zeros((SCREEN_H, SCREEN_W, 3), np.uint8)
        y = SCREEN_H // 2 - 20 * len(lines)
        for line in lines:
            put_text_kr(canvas, line, (60, y), 40, (0, 255, 255))
            y += 55
        if sub:
            put_text_kr(canvas, sub, (60, y + 15), 26, (140, 140, 140))
        cv2.imshow(WIN, canvas)
        key = cv2.waitKey(30) & 0xFF
        if key == 27:
            return False
        if key != 255:
            return True


def run_head_pose_variation(cap, face_mesh, tx=0.5, ty=0.5, sec=2.0, label=""):
    """
    화면의 한 점을 계속 보게 하면서 고개만 좌우/상하/앞뒤로 움직이게 해,
    '같은 시선 목표'에 대해 다양한 고개 위치의 데이터를 모은다.
    여러 화면 위치에서 반복 호출하면, 화면 전체에 걸쳐 '시선+고개 동시 움직임'에 대한
    보정력을 학습시킬 수 있다 (실생활에서는 고개를 완전히 고정한 채 눈만 움직이지 않으므로).
    """
    center = (int(tx * SCREEN_W), int(ty * SCREEN_H))
    collected, t0, fail_count = [], time.time(), 0
    while True:
        ok, frame = cap.read()
        if not ok:
            fail_count += 1
            if fail_count > 60:
                raise RuntimeError("웹캠에서 프레임을 읽지 못했습니다.")
            time.sleep(0.03)
            continue
        fail_count = 0
        elapsed = time.time() - t0

        canvas = np.zeros((SCREEN_H, SCREEN_W, 3), np.uint8)
        cv2.circle(canvas, center, 22, (255, 255, 255), 2)
        cv2.circle(canvas, center, 5, (0, 0, 255), -1)
        put_text_kr(canvas, f"점은 계속 보면서 고개를 좌우/상하/앞뒤로 움직여 주세요  ({label})",
                    (30, 25), 28, (200, 200, 200))
        put_text_kr(canvas, "ESC: 취소", (30, 65), 24, (140, 140, 140))
        cv2.imshow(WIN, canvas)
        if cv2.waitKey(1) & 0xFF == 27:
            return None

        if elapsed > 0.3:
            f, opens = extract_features(frame, face_mesh)
            if f is not None and opens.min() > BLINK_THRESHOLD:
                collected.append((f, (tx, ty), opens))
        if elapsed >= sec:
            return collected


def run_validation(cap, face_mesh, W, points):
    """학습에 쓰지 않은 새 점들로 실제 정확도(픽셀 오차)를 측정하는 홀드아웃 검증.
    반환값: (평균 오차 또는 None, 취소 여부)"""
    errs = []
    for i, (tx, ty) in enumerate(points, 1):
        samples, t0 = [], time.time()
        center = (int(tx * SCREEN_W), int(ty * SCREEN_H))
        fail_count = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                fail_count += 1
                if fail_count > 60:
                    raise RuntimeError("웹캠에서 프레임을 읽지 못했습니다.")
                time.sleep(0.03)
                continue
            fail_count = 0
            elapsed = time.time() - t0
            canvas = np.zeros((SCREEN_H, SCREEN_W, 3), np.uint8)
            cv2.circle(canvas, center, 18, (0, 200, 0), 2)
            cv2.circle(canvas, center, 4, (0, 200, 0), -1)
            put_text_kr(canvas, f"정확도 검증 중  ({i}/{len(points)})  ESC: 취소",
                        (30, 25), 30, (200, 200, 200))
            cv2.imshow(WIN, canvas)
            if cv2.waitKey(1) & 0xFF == 27:
                return None, True
            if elapsed >= VALID_SETTLE_SEC:
                f, opens = extract_features(frame, face_mesh)
                if f is not None and opens.min() > BLINK_THRESHOLD:
                    samples.append(f)
            if elapsed >= VALID_SETTLE_SEC + VALID_COLLECT_SEC:
                break
        if samples:
            pred = np.array([predict(W, f) for f in samples]).mean(axis=0)
            true = np.array([tx, ty]) * np.array([SCREEN_W, SCREEN_H])
            errs.append(np.linalg.norm(pred - true))
    return (float(np.mean(errs)) if errs else None), False


def show_summary(train_err, val_err):
    while True:
        canvas = np.zeros((SCREEN_H, SCREEN_W, 3), np.uint8)
        put_text_kr(canvas, "캘리브레이션 완료!", (60, SCREEN_H // 2 - 80), 46, (0, 255, 0))
        put_text_kr(canvas, f"학습 데이터 평균 오차: 약 {train_err:.0f}px",
                    (60, SCREEN_H // 2 - 20), 30, (200, 200, 200))
        if val_err is not None:
            put_text_kr(canvas, f"검증(홀드아웃) 평균 오차: 약 {val_err:.0f}px",
                        (60, SCREEN_H // 2 + 25), 30, (200, 200, 200))
        put_text_kr(canvas, "아무 키나 누르면 시작합니다", (60, SCREEN_H // 2 + 75), 26, (140, 140, 140))
        cv2.imshow(WIN, canvas)
        if cv2.waitKey(30) & 0xFF != 255:
            return


def calibrate(cap, face_mesh, passes=1):
    """
    시선 매핑 W와, 각 눈의 '평소 뜬 상태' 개폐 비율 base를 함께 구한다.

    구성:
      1) 격자 점(3x3) — 각 점을 STABLE_SEC(기본 1.5초) 이상 안정적으로 봐야 확정(빨강→초록),
         확정 시 그 구간 데이터를 중앙값 하나로 고정
      2) 고개 자세 변화 — 화면 3곳(중앙/위/아래)을 보며 고개를 움직여 자세 변화 보정력 강화
      3) 홀드아웃 검증 — 학습에 쓰지 않은 새 점 2개로 실제 정확도(px)를 측정해 표시
    """
    xs = np.linspace(MARGIN, 1 - MARGIN, GRID_COLS)
    ys = np.linspace(MARGIN, 1 - MARGIN, GRID_ROWS)
    grid_targets = []
    for r, y in enumerate(ys):                       # 지그재그 순서로 시선 이동 최소화
        row = xs if r % 2 == 0 else xs[::-1]
        grid_targets += [(x, y) for x in row]

    feats, labels, opens_all = [], [], []

    # 1) 격자 수집 — 각 점을 3초 이상 안정적으로 봐야 확정되고, 확정 순간의 중앙값 하나만 사용
    for p in range(1, passes + 1):
        if p > 1:
            if not show_pass_break(p - 1, passes):
                return None
        order = grid_targets if p % 2 == 1 else grid_targets[::-1]
        for i, (tx, ty) in enumerate(order, 1):
            label = f"{i}/{len(order)}" + (f"  회차 {p}/{passes}" if passes > 1 else "")
            samples = collect_point(cap, face_mesh, tx, ty, label)
            if samples is None:
                return None
            for f, o in samples:
                feats.append(f)
                labels.append((tx, ty))
                opens_all.append(o)

    # 2) 고개 자세 변화 — 화면 3곳(중앙/위/아래, 위아래를 우선)을 보며 고개를 움직여 보정력 강화
    if not show_message(["자세 변화 단계"], "각 점을 계속 보며 고개를 움직여 주세요 — 아무 키나 눌러 시작"):
        return None
    pose_points = [(0.5, 0.5), (0.5, MARGIN), (0.5, 1 - MARGIN)]
    for i, (tx, ty) in enumerate(pose_points, 1):
        pose_samples = run_head_pose_variation(cap, face_mesh, tx, ty, sec=1.5,
                                                label=f"{i}/{len(pose_points)}")
        if pose_samples is None:
            return None
        for f, label, o in pose_samples:
            feats.append(f)
            labels.append(label)
            opens_all.append(o)

    W = fit(feats, labels)
    base = np.median(np.array(opens_all), axis=0)    # [왼눈, 오른눈] 평소 개폐 비율

    pred = np.array([predict(W, f) for f in feats])
    true = np.array(labels) * np.array([SCREEN_W, SCREEN_H])
    train_err = np.linalg.norm(pred - true, axis=1).mean()

    # 3) 홀드아웃 검증 — 격자 사이의 새 지점 2개로 실제 정확도 측정 (학습에는 사용하지 않음)
    val_xs = (xs[:-1] + xs[1:]) / 2
    val_ys = (ys[:-1] + ys[1:]) / 2
    val_targets = [(val_xs[0], val_ys[0]), (val_xs[-1], val_ys[-1])]
    if not show_message(["정확도 검증"], "새로운 점 2개를 봐주세요 — 아무 키나 눌러 시작"):
        return None
    val_err, cancelled = run_validation(cap, face_mesh, W, val_targets)
    if cancelled:
        return None

    print(f"캘리브레이션 완료 — 학습 오차 약 {train_err:.0f}px"
          + (f", 검증 오차 약 {val_err:.0f}px" if val_err is not None else "")
          + f", 평소 눈 개폐 비율 L {base[0]:.2f} / R {base[1]:.2f}")
    show_summary(train_err, val_err)
    return W, base


# ---- 메인 -------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--recalibrate", action="store_true")
    ap.add_argument("--hd", action="store_true",
                     help="웹캠이 720p/1080p를 지원하면 더 높은 해상도로 시도 (기본은 640x480)")
    args = ap.parse_args()

    print("[1/5] 카메라를 여는 중...")
    cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)

    # 기본은 640x480으로 바로 고정 (저해상도 웹캠에서 더 높은 해상도를 반복 요청하면
    # 일부 드라이버가 응답하지 않고 멈추는 경우가 있어, 확실히 되는 값으로 바로 시작한다).
    # --hd 옵션을 주면 720p/1080p까지 순서대로 시도한다 (웹캠이 지원하는 게 확실할 때만 사용).
    res_candidates = [(1920, 1080), (1280, 720), (640, 480)] if args.hd else [(640, 480)]
    actual_w, actual_h = 640, 480
    for w, h in res_candidates:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if actual_w >= w * 0.9:          # 웹캠이 실제로 이 해상도를 받아들였으면 통과
            break
    print(f"[2/5] 카메라 해상도: {actual_w}x{actual_h}")

    # 카메라 워밍업: 열자마자 바로 읽으면 실패하는 경우가 있어 잠깐 대기 후 몇 프레임 버린다.
    for _ in range(30):
        ok, _ = cap.read()
        if ok:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("웹캠을 초기화하지 못했습니다. 카메라가 다른 프로그램에서 사용 중인지 확인하세요.")
    print("[3/5] 카메라 준비 완료")

    print("[4/5] 얼굴 인식 모델(MediaPipe) 로딩 중...")
    face_mesh = mp.solutions.face_mesh.FaceMesh(
        max_num_faces=1, refine_landmarks=True,
        min_detection_confidence=0.5, min_tracking_confidence=0.5)
    print("[5/5] 준비 완료 — 캘리브레이션을 시작합니다")

    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    set_window_fullscreen()

    W = base = None
    if CALIB_FILE.exists() and not args.recalibrate:
        data = np.load(CALIB_FILE)
        if "base" in data.files and data["W"].shape[0] == DESIGN_LEN:
            # 윙크 기준값이 없거나(예전 파일) 모델 구조가 바뀐 파일이면 다시 캘리브레이션
            W, base = data["W"], data["base"]
    if W is None:
        result = calibrate(cap, face_mesh)
        if result is None:
            print("캘리브레이션이 취소되었습니다.")
            return
        W, base = result
        np.savez(CALIB_FILE, W=W, base=base)

    print("메인 화면으로 전환 중...")
    set_window_debug()   # 캘리브레이션 끝났으니 이제 다른 프로그램을 조작할 수 있게 작은 창으로 전환

    smoother, winker = Smoother(), WinkDetector()
    feat_smoother = FeatureSmoother()
    dweller = DwellTracker()              # 응시 기반 커서 이동
    pos, cursor_pos, mouse_on = None, None, False
    flash_name, flash_t = "", 0.0
    fps, prev_t = 0.0, time.time()

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        now = time.time()

        feat, opens = extract_features(frame, face_mesh)
        face_found = feat is not None
        ratio = None
        if face_found:
            ratio = opens / base
            event = winker.update(ratio, now)

            # 두 눈이 충분히 떠 있을 때만 시선 갱신 → 윙크·깜빡임 중에는 커서가 튀지 않고 고정
            if (ratio > OPEN_RATIO).all():
                smoothed_feat = feat_smoother(feat)
                raw = np.clip(predict(W, smoothed_feat), [0, 0], [SCREEN_W - 1, SCREEN_H - 1])
                pos = smoother(raw)
                committed = dweller.update(pos, now)   # 일정 시간 이상 같은 곳을 봐야 '실제' 커서 위치 갱신
                if committed is not None:
                    cursor_pos = committed
                    if mouse_on:
                        pyautogui.moveTo(int(cursor_pos[0]), int(cursor_pos[1]))
                x, y = int(pos[0]), int(pos[1])
                print(f"\rgaze: ({x:4d}, {y:4d})", end="", flush=True)

            if event and pos is not None:
                cx, cy = int(pos[0]), int(pos[1])   # 지금 가리키는 바로 그 위치에서 클릭
                print(f"\n{event.upper()} WINK at ({cx}, {cy})")
                flash_name, flash_t = event, now
                if mouse_on:
                    pyautogui.click(x=cx, y=cy, button=event)
        else:
            winker.reset()

        fps = 0.9 * fps + 0.1 / max(now - prev_t, 1e-6)
        prev_t = now

        canvas = np.zeros((DEBUG_H, DEBUG_W, 3), np.uint8)
        coord = f"({int(cursor_pos[0])}, {int(cursor_pos[1])})" if cursor_pos is not None else "-"
        cv2.putText(canvas, f"cursor {coord}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        cv2.putText(canvas, f"FPS {fps:.0f}  mouse {'ON' if mouse_on else 'OFF'}",
                    (10, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        cv2.putText(canvas, "M: mouse  C: recalibrate  Q/ESC: quit",
                    (10, 71), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (140, 140, 140), 1)
        if ratio is not None:
            cv2.putText(canvas, f"eye open  L {ratio[0]:.2f}  R {ratio[1]:.2f}",
                        (10, 94), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (140, 140, 140), 1)
        else:
            cv2.putText(canvas, "No face detected", (10, 94),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 1)
        # 응시(dwell) 진행률 바 — 다음 커서 이동까지 얼마나 남았는지 표시
        prog = dweller.progress(now)
        bar_w = int((DEBUG_W - 20) * prog)
        cv2.rectangle(canvas, (10, 100), (DEBUG_W - 10, 106), (60, 60, 60), -1)
        cv2.rectangle(canvas, (10, 100), (10 + bar_w, 106), (0, 255, 0) if prog >= 1.0 else (0, 200, 255), -1)
        if now - flash_t < 0.6:
            cv2.putText(canvas, f"{flash_name.upper()} WINK", (10, 128),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        # 미니맵 — 전체 화면을 축소해 지금 시선(흰 점)·확정된 커서(초록 원) 위치를 보여준다.
        mini_x0, mini_y0, mini_w, mini_h = DEBUG_W - 140, 8, 130, 74
        cv2.rectangle(canvas, (mini_x0, mini_y0), (mini_x0 + mini_w, mini_y0 + mini_h), (90, 90, 90), 1)
        if pos is not None:
            mx = mini_x0 + int(np.clip(pos[0] / SCREEN_W, 0, 1) * mini_w)
            my = mini_y0 + int(np.clip(pos[1] / SCREEN_H, 0, 1) * mini_h)
            cv2.circle(canvas, (mx, my), 3, (255, 255, 255), -1)
        if cursor_pos is not None:
            cx2 = mini_x0 + int(np.clip(cursor_pos[0] / SCREEN_W, 0, 1) * mini_w)
            cy2 = mini_y0 + int(np.clip(cursor_pos[1] / SCREEN_H, 0, 1) * mini_h)
            cv2.circle(canvas, (cx2, cy2), 5, (0, 255, 0), 1)

        preview = cv2.resize(cv2.flip(frame, 1), (DEBUG_W - 20, 100))
        canvas[DEBUG_H - 110:DEBUG_H - 10, 10:DEBUG_W - 10] = preview
        cv2.imshow(WIN, canvas)

        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord("q")):
            break
        if key == ord("m"):
            mouse_on = not mouse_on
        if key == ord("c"):
            set_window_fullscreen()
            result = calibrate(cap, face_mesh)
            if result is not None:
                W, base = result
                np.savez(CALIB_FILE, W=W, base=base)
                smoother, winker = Smoother(), WinkDetector()
                feat_smoother = FeatureSmoother()
                dweller = DwellTracker()
            set_window_debug()

    print()
    cap.release()
    face_mesh.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
