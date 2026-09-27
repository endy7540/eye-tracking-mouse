"""
gaze_mapper.py — 매핑 담당 모듈.

책임 범위:
  1) 웹캠에서 프레임을 읽는다 (목표 30fps — 웹캠이 30fps 이상을 지원하면 30으로 맞추고,
     그보다 낮은 웹캠이면 그 웹캠이 낼 수 있는 최대 fps를 그대로 사용한다).
  2) 프레임에서 홍채(눈동자) 위치를 계산한다.
  3) 그 값을 모니터 화면 좌표(x, y) 픽셀 값까지 변환해서 반환한다.

캘리브레이션은 이 모듈의 책임이 아니다. 다만 캘리브레이션 담당 모듈이 나중에
실제 계수(또는 변환 함수)를 넘겨주면 set_calibration()으로 반영할 수 있도록
훅을 열어뒀다 — 넘겨주기 전까지는 대충 잡은 기본값으로 동작한다.
"""
import cv2
import mediapipe as mp
import numpy as np
import pyautogui

# (이미지 기준) 왼쪽 눈꼬리, 오른쪽 눈꼬리, 윗눈꺼풀, 아랫눈꺼풀, 홍채 중심+경계점
EYE_R = (33, 133, 159, 145, (468, 469, 470, 471, 472))    # 사용자의 오른쪽 눈
EYE_L = (362, 263, 386, 374, (473, 474, 475, 476, 477))   # 사용자의 왼쪽 눈

TARGET_FPS = 30   # 목표 fps — 웹캠이 이보다 낮은 fps만 지원하면 그 한도를 그대로 사용


def _eye_feature(lm, w, h, idx):
    """랜드마크에서 (수평 홍채 위치 hx, 수직 홍채 위치 vy)를 계산."""
    left, right, top, bottom, iris_idxs = idx
    pt = lambda i: np.array([lm[i].x * w, lm[i].y * h])
    p_l, p_r = pt(left), pt(right)
    p_i = np.mean([pt(i) for i in iris_idxs], axis=0)   # 홍채 중심+경계점 평균 (노이즈 감소)

    axis = p_r - p_l
    width = np.linalg.norm(axis)
    u = axis / width
    normal = np.array([-u[1], u[0]])

    hx = np.dot(p_i - p_l, u) / width - 0.5              # 대략 -0.5 ~ 0.5
    vy = np.dot(p_i - (p_l + p_r) / 2, normal) / width   # 눈 중앙선 기준 offset
    return hx, vy


class GazeResult:
    """read()가 반환하는 결과 하나. x, y는 모니터 픽셀 좌표(정수)."""
    __slots__ = ("x", "y", "hx", "vy", "frame")

    def __init__(self, x, y, hx, vy, frame):
        self.x, self.y, self.hx, self.vy, self.frame = x, y, hx, vy, frame

    def __repr__(self):
        return f"GazeResult(x={self.x}, y={self.y}, hx={self.hx:.3f}, vy={self.vy:.3f})"


class GazeMapper:
    """
    웹캠 → 홍채(hx, vy) 계산 → 화면 좌표(x, y) 변환까지 담당하는 클래스.

    사용법:
        mapper = GazeMapper(camera_index=0)
        while True:
            result = mapper.read()
            if result is not None:
                x, y = result.x, result.y   # 모니터 픽셀 좌표 — 여기까지가 매핑 담당의 출력
            ...
        mapper.close()

    다른 팀원 연동:
        - 캘리브레이션 담당: mapper.set_calibration(...)으로 실제 계수/변환 함수를 넘기면
          이후 read()의 x, y 계산에 그게 반영된다. 안 넘기면 기본(고정) 범위로 동작한다.
        - 제어 담당: result.x, result.y (그리고 필요하면 result.hx, result.vy)만 받아쓰면 된다.
    """

    def __init__(self, camera_index=0, screen_size=None, backend=cv2.CAP_DSHOW):
        self.cap = cv2.VideoCapture(camera_index, backend)

        # 프레임 속도 협상: 30fps를 요청해보고, 웹캠이 실제로 그보다 낮은 fps만
        # 낼 수 있다고 응답하면 그 한도에 맞춘다 (일부 웹캠/드라이버는 0을 보고하기도
        # 하는데, 그 경우엔 30 요청값을 그대로 신뢰한다).
        self.cap.set(cv2.CAP_PROP_FPS, TARGET_FPS)
        reported_fps = self.cap.get(cv2.CAP_PROP_FPS)
        if reported_fps <= 0 or reported_fps >= TARGET_FPS:
            self.fps = TARGET_FPS
        else:
            self.fps = reported_fps
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)

        self.screen_w, self.screen_h = screen_size or pyautogui.size()

        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1, refine_landmarks=True,
            min_detection_confidence=0.5, min_tracking_confidence=0.5)

        # 캘리브레이션 계수가 아직 없을 때 쓰는 기본(고정) 매핑 범위 — 사람마다 실제
        # hx/vy 움직임 폭이 달라 정확하지 않다. 캘리브레이션 담당이 set_calibration()으로
        # 실제 값을 넘기면 그걸로 대체된다.
        self._hx_range = 0.28
        self._vy_range = 0.14
        self._transform = None
        self.calibrated = False

    def set_calibration(self, hx_range=None, vy_range=None, transform=None):
        """
        캘리브레이션 담당이 계산한 값을 매핑에 반영한다.
        - hx_range, vy_range: 이 사람의 실제 눈동자 움직임 폭 (기본 고정값을 대체)
        - transform: (hx, vy) -> (x, y) 를 직접 계산하는 콜러블. 지정하면 hx_range/vy_range
          대신 이 함수가 우선 사용된다 (다항 회귀 등 더 정교한 모델을 쓰고 싶을 때).
        """
        if hx_range is not None:
            self._hx_range = hx_range
        if vy_range is not None:
            self._vy_range = vy_range
        self._transform = transform
        self.calibrated = True

    def read(self):
        """
        웹캠에서 한 프레임을 읽어 처리한다.
        반환: GazeResult (x, y는 화면 픽셀 좌표) — 얼굴을 못 찾거나 프레임을 못 읽으면 None.
        """
        ok, frame = self.cap.read()
        if not ok:
            return None
        h, w = frame.shape[:2]
        result = self.face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if not result.multi_face_landmarks:
            return None

        lm = result.multi_face_landmarks[0].landmark
        r = _eye_feature(lm, w, h, EYE_R)
        l = _eye_feature(lm, w, h, EYE_L)
        hx = (r[0] + l[0]) / 2
        vy = (r[1] + l[1]) / 2

        if self._transform is not None:
            x, y = self._transform(hx, vy)
        else:
            nx = np.clip((hx / self._hx_range + 1) / 2, 0, 1)
            ny = np.clip((vy / self._vy_range + 1) / 2, 0, 1)
            x, y = nx * self.screen_w, ny * self.screen_h

        return GazeResult(x=int(x), y=int(y), hx=hx, vy=vy, frame=frame)

    def close(self):
        self.cap.release()
        self.face_mesh.close()


# ---- 단독 실행 시: 미리보기 창으로 동작 확인 --------------------------
if __name__ == "__main__":
    mapper = GazeMapper()
    print(f"카메라 fps: {mapper.fps:.0f}  (Q 또는 ESC로 종료)")
    try:
        while True:
            result = mapper.read()
            preview = None
            if result is not None:
                preview = cv2.flip(result.frame, 1)
                cv2.putText(preview, f"hx {result.hx:+.3f}  vy {result.vy:+.3f}",
                            (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                cv2.putText(preview, f"screen ({result.x}, {result.y})",
                            (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                print(f"\r{result}", end="", flush=True)
            else:
                print("\rNo face detected" + " " * 30, end="", flush=True)
                ok, frame = mapper.cap.read()
                preview = cv2.flip(frame, 1) if ok else None
            if preview is not None:
                cv2.imshow("gaze_mapper preview (Q/ESC to quit)", preview)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break
    finally:
        print()
        mapper.close()
        cv2.destroyAllWindows()
