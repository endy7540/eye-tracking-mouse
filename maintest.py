"""
gaze_tracker.py — 웹캠 기반 실시간 홍채(시선) 추적 → 모니터 좌표 출력 + 좌/우 윙크 구분

설치:   pip install opencv-python mediapipe numpy pyautogui
실행:   python gaze_tracker.py                 (처음 실행 시 자동으로 캘리브레이션)
        python gaze_tracker.py --recalibrate   (캘리브레이션 다시 하기)

조작키: M = 실제 마우스 제어 ON/OFF,  C = 재캘리브레이션,  Q / ESC = 종료
윙크:   왼쪽 눈만 감으면 LEFT, 오른쪽 눈만 감으면 RIGHT 이벤트 발생 ('왼쪽/오른쪽'은 사용자 본인 기준)
        M이 ON이면 각각 왼쪽 클릭 / 오른쪽 클릭까지 실행. 자연스러운 깜빡임(양쪽 동시)은 무시.

캘리브레이션 중에는 전체화면 검은 창이 뜨지만, 끝나면 화면 좌상단의 작은 상태창으로 줄어들어
그 아래에 있는 실제 프로그램(브라우저 등)을 그대로 보고 조작할 수 있습니다.
"""
import argparse
import time
from collections import deque
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
import pyautogui
from PIL import Image, ImageDraw, ImageFont
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QColor
from PyQt5.QtWidgets import QApplication, QWidget

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

SCREEN_W, SCREEN_H = pyautogui.size()
CALIB_FILE = Path("calibration.npz")
WIN = "gaze"
DEBUG_W, DEBUG_H = 380, 230   # 실사용 중 표시할 작은 상태창 크기


def set_window_fullscreen():
    """캘리브레이션용: 화면 전체를 덮는 창으로 전환."""
    cv2.setWindowProperty(WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)


def set_window_debug():
    """실사용 중: 다른 프로그램(브라우저 등)을 조작할 수 있도록 작은 상태창으로 전환."""
    cv2.setWindowProperty(WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, DEBUG_W, DEBUG_H)
    cv2.moveWindow(WIN, 20, 20)
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
GRID_COLS, GRID_ROWS = 5, 5   # 캘리브레이션 점 개수 (5x5 = 25점) — 위아래 해상도를 좌우와 동일하게
MARGIN = 0.07                 # 화면 가장자리 여백 비율
SETTLE_SEC = 0.8              # 점을 보고 시선이 안정될 때까지 대기
COLLECT_SEC = 1.2             # 샘플 수집 시간
BLINK_THRESHOLD = 0.18        # 캘리브레이션 중 눈 높이/너비 비율이 이보다 작은 프레임은 버림

PURSUIT_SEG_SEC = 0.9         # 부드러운 추적(smooth pursuit) 단계에서 한 구간 이동 시간
CORNER_MARGIN = 0.025         # 코너 강화 포인트의 여백 비율 (MARGIN보다 훨씬 가장자리)
VALID_SETTLE_SEC = 0.5        # 검증(홀드아웃) 단계는 좀 더 짧게 진행
VALID_COLLECT_SEC = 0.5

# 윙크 판정 (각 눈의 '평소 뜬 상태 대비 개폐 비율' 기준)
CLOSE_RATIO = 0.50            # 이보다 작아지면 그 눈은 "감김"
OPEN_RATIO = 0.70             # 이보다 커지면 그 눈은 "뜸" (히스테리시스로 떨림 방지)
WINK_MIN_SEC = 0.25           # 한쪽 눈만 이 시간 이상 감고 있어야 윙크로 인정
WINK_COOLDOWN = 0.6           # 윙크 이벤트 사이 최소 간격
SWAP_LR = False               # 왼쪽/오른쪽이 반대로 인식되면 True (거울 모드 웹캠 등)

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


def extract_features(frame, face_mesh):
    """
    프레임 → ([홍채 x, 홍채 y, 코 x, 코 y, 눈꺼풀 벌어짐], [왼눈 개폐, 오른눈 개폐]).
    얼굴이 없으면 (None, None).
    눈꺼풀이 벌어진 정도(openness)는 사람이 위/아래를 볼 때 무의식적으로 같이 변하는
    경향이 있어, 위아래 시선 추정에 도움이 되는 보조 신호로 함께 사용한다.
    """
    h, w = frame.shape[:2]
    result = face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    if not result.multi_face_landmarks:
        return None, None
    lm = result.multi_face_landmarks[0].landmark
    right = eye_feature(lm, w, h, EYE_R)
    left = eye_feature(lm, w, h, EYE_L)
    feat = np.array([(right[0] + left[0]) / 2, (right[1] + left[1]) / 2,
                     lm[NOSE].x, lm[NOSE].y, (right[2] + left[2]) / 2])
    opens = np.array([left[2], right[2]])
    if SWAP_LR:
        opens = opens[::-1].copy()
    return feat, opens


# ---- 특징 → 화면 좌표 매핑 (2차 다항 + 머리 위치/눈꺼풀 보정, 릿지 회귀) ----------
DESIGN_LEN = 15   # design() 벡터 길이 — 캘리브레이션 파일 호환성 검사에 사용


def design(f):
    hx, vy, nx, ny, op = f
    # nx, ny(고개/코 위치)와 hx, vy(눈동자 방향)의 교차항: 고개 위치 변화에 따른 패럴랙스 보정
    # op(눈꺼풀 벌어짐)과 vy의 교차항: 위아래 시선과 함께 변하는 눈꺼풀 정보를 추가 신호로 활용
    return np.array([
        1.0, hx, vy, hx * hx, vy * vy, hx * vy,
        nx, ny, nx * nx, ny * ny,
        hx * nx, vy * ny,
        op, op * op, op * vy,
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
        hx, vy, nx, ny, op = f
        head = np.array([nx, ny])
        if self.prev_head is None:
            self.prev_head = head.copy()
        else:
            self.prev_head = self.prev_head + self.alpha * (head - self.prev_head)
        return np.array([hx, vy, self.prev_head[0], self.prev_head[1], op])


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
    samples, t0 = [], time.time()
    center = (int(tx * SCREEN_W), int(ty * SCREEN_H))
    fail_count = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            fail_count += 1
            if fail_count > 60:   # 약 2초 이상 연속 실패해야만 진짜 오류로 판단
                raise RuntimeError("웹캠에서 프레임을 읽지 못했습니다.")
            time.sleep(0.03)
            continue
        fail_count = 0
        elapsed = time.time() - t0

        canvas = np.zeros((SCREEN_H, SCREEN_W, 3), np.uint8)
        cv2.circle(canvas, center, 22, (255, 255, 255), 2)
        cv2.circle(canvas, center, 5, (0, 0, 255), -1)
        put_text_kr(canvas, f"점을 계속 봐주세요  ({label})  ESC: 취소",
                    (30, 25), 30, (200, 200, 200))
        cv2.imshow(WIN, canvas)
        if cv2.waitKey(1) & 0xFF == 27:
            return None

        if elapsed >= SETTLE_SEC:
            f, opens = extract_features(frame, face_mesh)
            if f is not None and opens.min() > BLINK_THRESHOLD:
                samples.append((f, opens))
        if elapsed >= SETTLE_SEC + COLLECT_SEC:
            return samples


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


def run_pursuit(cap, face_mesh, waypoints):
    """
    점이 각 웨이포인트 사이를 부드럽게 이동하는 동안 계속 눈으로 따라가게 하여
    격자점 '사이' 공간까지 촘촘하게(연속적으로) 샘플을 모은다.
    """
    if not show_message(["이제 점이 부드럽게 움직입니다"],
                         "눈으로 점을 계속 따라가 주세요 — 아무 키나 눌러 시작 (ESC: 취소)"):
        return None

    collected = []
    path = list(waypoints) + [waypoints[0]]   # 마지막에 시작점으로 되돌아와 자연스럽게 마무리
    fail_count = 0
    for a, b in zip(path[:-1], path[1:]):
        t0 = time.time()
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
            frac = min(elapsed / PURSUIT_SEG_SEC, 1.0)
            tx = a[0] + (b[0] - a[0]) * frac
            ty = a[1] + (b[1] - a[1]) * frac
            center = (int(tx * SCREEN_W), int(ty * SCREEN_H))

            canvas = np.zeros((SCREEN_H, SCREEN_W, 3), np.uint8)
            cv2.circle(canvas, center, 12, (0, 255, 255), -1)
            put_text_kr(canvas, "점을 부드럽게 눈으로 따라가 주세요 (추적)  ESC: 취소",
                        (30, 25), 30, (200, 200, 200))
            cv2.imshow(WIN, canvas)
            if cv2.waitKey(1) & 0xFF == 27:
                return None

            if elapsed > 0.15:                      # 구간 시작 직후 약간의 반응 지연은 건너뜀
                f, opens = extract_features(frame, face_mesh)
                if f is not None and opens.min() > BLINK_THRESHOLD:
                    collected.append((f, (tx, ty), opens))
            if frac >= 1.0:
                break
    return collected


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


def calibrate(cap, face_mesh, passes=2):
    """
    시선 매핑 W와, 각 눈의 '평소 뜬 상태' 개폐 비율 base를 함께 구한다.

    구성:
      1) 격자 점(5x3) — passes(기본 2)회 반복, 회차 사이 자세 변경 유도
      2) 코너 강화 포인트 — 가장 오차가 크기 쉬운 화면 네 귀퉁이를 추가로 학습
      3) 부드러운 추적(pursuit) — 점이 이동하는 동안 계속 추적, 격자 '사이' 공간까지 촘촘히 커버
      4) 고개 자세 변화 — 중앙 점을 보며 고개를 움직여 자세 변화 보정력 강화
      5) 홀드아웃 검증 — 학습에 쓰지 않은 새 점들로 실제 정확도(px)를 측정해 표시
    """
    xs = np.linspace(MARGIN, 1 - MARGIN, GRID_COLS)
    ys = np.linspace(MARGIN, 1 - MARGIN, GRID_ROWS)
    grid_targets = []
    for r, y in enumerate(ys):                       # 지그재그 순서로 시선 이동 최소화
        row = xs if r % 2 == 0 else xs[::-1]
        grid_targets += [(x, y) for x in row]

    feats, labels, opens_all = [], [], []

    # 1) 격자 다회차 수집
    for p in range(1, passes + 1):
        if p > 1:
            if not show_pass_break(p - 1, passes):
                return None
        order = grid_targets if p % 2 == 1 else grid_targets[::-1]
        for i, (tx, ty) in enumerate(order, 1):
            while True:
                label = f"{i}/{len(order)}  회차 {p}/{passes}"
                samples = collect_point(cap, face_mesh, tx, ty, label)
                if samples is None:
                    return None
                if len(samples) >= 10:                   # 얼굴이 잘 안 잡히면 같은 점 재시도
                    break
            for f, o in samples:
                feats.append(f)
                labels.append((tx, ty))
                opens_all.append(o)

    # 2) 코너 강화 포인트 (화면 네 귀퉁이는 오차가 크기 쉬워 별도로 보강)
    if not show_message(["코너 보강 단계"], "화면 네 귀퉁이 점을 차례로 봐주세요 — 아무 키나 눌러 시작"):
        return None
    corner_targets = [(CORNER_MARGIN, CORNER_MARGIN), (1 - CORNER_MARGIN, CORNER_MARGIN),
                       (CORNER_MARGIN, 1 - CORNER_MARGIN), (1 - CORNER_MARGIN, 1 - CORNER_MARGIN)]
    for i, (tx, ty) in enumerate(corner_targets, 1):
        while True:
            samples = collect_point(cap, face_mesh, tx, ty, f"코너 {i}/{len(corner_targets)}")
            if samples is None:
                return None
            if len(samples) >= 10:
                break
        for f, o in samples:
            feats.append(f)
            labels.append((tx, ty))
            opens_all.append(o)

    # 3) 부드러운 추적 — 격자점들을 잇는 경로를 눈으로 계속 따라가며 연속 수집
    pursuit_samples = run_pursuit(cap, face_mesh, grid_targets)
    if pursuit_samples is None:
        return None
    for f, label, o in pursuit_samples:
        feats.append(f)
        labels.append(label)
        opens_all.append(o)

    # 4) 고개 자세 변화 — 화면 5곳(중앙+네 모서리)을 보며 고개를 움직여, 화면 전체에 걸쳐
    #    '시선+고개 동시 움직임'에 대한 보정력을 학습 (실생활에서는 고개도 같이 움직이므로)
    if not show_message(["자세 변화 단계 (5곳)"],
                         "각 점을 계속 보며 고개를 움직여 주세요 — 아무 키나 눌러 시작"):
        return None
    pose_points = [(0.5, 0.5)] + corner_targets
    for i, (tx, ty) in enumerate(pose_points, 1):
        pose_samples = run_head_pose_variation(cap, face_mesh, tx, ty, sec=2.2,
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

    # 5) 홀드아웃 검증 — 격자 사이의 새 지점들로 실제 정확도 측정 (학습에는 사용하지 않음)
    val_xs = (xs[:-1] + xs[1:]) / 2
    val_ys = (ys[:-1] + ys[1:]) / 2
    val_targets = [(val_xs[0], val_ys[0]), (val_xs[-1], val_ys[0]),
                   (val_xs[0], val_ys[-1]), (val_xs[-1], val_ys[-1])]
    if not show_message(["정확도 검증 단계"], "새로운 점 4개를 봐주세요 — 아무 키나 눌러 시작"):
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
class GazeOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.gaze_pos = None  # (x, y) 시선 좌표
        
        # 창 속성 설정: 투명함, 프레임 없음, 항상 위에 표시
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint | 
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        
        # 윈도우가 마우스 클릭을 가로채지 않고 밑으로 통과시키도록 설정 (Windows API)
        try:
            import ctypes
            hwnd = int(self.winId())
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, ex_style | 0x00080000 | 0x00000020)
        except Exception:
            pass

        self.setGeometry(0, 0, SCREEN_W, SCREEN_H)
        self.show()

    def update_gaze(self, pos):
        self.gaze_pos = pos
        self.update()

    def paintEvent(self, event):
        if self.gaze_pos is not None:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)  # 부드러운 원
            
            # 연한 파란색 테두리, 반투명한 내부 채우기
            painter.setPen(QColor(0, 150, 255, 180))
            painter.setBrush(QColor(0, 150, 255, 80))
            
            x, y = int(self.gaze_pos[0]), int(self.gaze_pos[1])
            radius = 25  # 화면에 표시될 원의 반지름 크기
            
            painter.drawEllipse(x - radius, y - radius, radius * 2, radius * 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--recalibrate", action="store_true")
    args = ap.parse_args()

    # PyQt 애플리케이션 및 투명 오버레이 창 초기화
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    overlay = GazeOverlay()

    cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    # 카메라 워밍업: 열자마자 바로 읽으면 실패하는 경우가 있어 잠깐 대기 후 몇 프레임 버린다.
    for _ in range(30):
        ok, _ = cap.read()
        if ok:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("웹캠을 초기화하지 못했습니다. 카메라가 다른 프로그램에서 사용 중인지 확인하세요.")

    face_mesh = mp.solutions.face_mesh.FaceMesh(
        max_num_faces=1, refine_landmarks=True,
        min_detection_confidence=0.5, min_tracking_confidence=0.5)

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
            overlay.close()
            return
        W, base = result
        np.savez(CALIB_FILE, W=W, base=base)

    set_window_debug()   # 캘리브레이션 끝났으니 이제 다른 프로그램을 조작할 수 있게 작은 창으로 전환

    smoother, winker = Smoother(), WinkDetector()
    feat_smoother = FeatureSmoother()
    hold = deque(maxlen=8)                # 최근 '두 눈 다 뜬' 프레임의 시선 위치 (윙크 직전 위치 복원용)
    pos, mouse_on = None, False
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
                hold.append(pos.copy())
                
                # [추가] 오버레이 창에 현재 시선 좌표 전달
                overlay.update_gaze(pos)
                
                x, y = int(pos[0]), int(pos[1])
                print(f"\rgaze: ({x:4d}, {y:4d})", end="", flush=True)
                if mouse_on:
                    pyautogui.moveTo(x, y)

            if event and pos is not None:
                cx, cy = (int(v) for v in (hold[0] if hold else pos))   # 눈 감기 직전 위치
                print(f"\n{event.upper()} WINK at ({cx}, {cy})")
                flash_name, flash_t = event, now
                if mouse_on:
                    pyautogui.click(x=cx, y=cy, button=event)
        else:
            winker.reset()
            # [추가] 얼굴이 감지되지 않으면 오버레이 원 숨기기
            overlay.update_gaze(None)

        fps = 0.9 * fps + 0.1 / max(now - prev_t, 1e-6)
        prev_t = now

        canvas = np.zeros((DEBUG_H, DEBUG_W, 3), np.uint8)
        coord = f"({int(pos[0])}, {int(pos[1])})" if pos is not None else "-"
        cv2.putText(canvas, f"gaze {coord}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
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
        if now - flash_t < 0.6:
            cv2.putText(canvas, f"{flash_name.upper()} WINK", (10, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        preview = cv2.resize(cv2.flip(frame, 1), (DEBUG_W - 20, 110))
        canvas[DEBUG_H - 120:DEBUG_H - 10, 10:DEBUG_W - 10] = preview
        cv2.imshow(WIN, canvas)

        key = cv2.waitKey(1) & 0xFF
        # [추가] PyQt 창이 응답 없음 상태가 되지 않도록 이벤트 루프 처리
        app.processEvents()

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
                hold.clear()
            set_window_debug()

    print()
    overlay.close()  # 종료 시 투명 오버레이 창 닫기
    cap.release()
    face_mesh.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
