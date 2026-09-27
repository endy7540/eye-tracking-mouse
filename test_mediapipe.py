"""
MediaPipe FaceMesh 웹캠 인식 테스트 스크립트
----------------------------------------
목적: 웹캠 영상에서 MediaPipe가 얼굴/눈동자(iris)를 제대로 인식하는지 확인.
(팀 결정에 따라 mediapipe==0.10.21 레거시 API 기준으로 되돌린 버전입니다.)

확인하는 것:
1. 웹캠이 정상적으로 열리는지
2. 얼굴이 인식되는지 (인식 안 되면 화면에 경고 표시)
3. 눈동자(iris) 랜드마크가 정확히 잡히는지 (초록/주황 점으로 표시)
4. FPS(초당 프레임)와 인식 성공률을 화면에 실시간으로 표시

조작법:
- q : 종료
- s : 현재 프레임 스크린샷 저장 (recognition_test.png)
"""

import cv2
import mediapipe as mp
import time
from collections import deque

# ---------- MediaPipe 설정 ----------
mp_face_mesh = mp.solutions.face_mesh
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

face_mesh = mp_face_mesh.FaceMesh(
    refine_landmarks=True,       # True로 해야 홍채(iris) 랜드마크가 나옴 (468~477번)
    max_num_faces=1,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)

# 화면(거울모드)에 보이는 위치 기준 라벨.
# MediaPipe 인덱스 468은 인체 기준 "오른쪽 눈"이지만, 거울모드로 좌우 반전하면
# 화면에는 왼쪽에 나타난다 (gaze_tracker.py의 EYE_R 주석 참고). 여기서는
# 화면을 보는 사람이 헷갈리지 않도록 "화면에 보이는 위치" 기준으로 L/R을 붙인다.
SCREEN_LEFT_IRIS = 468   # 화면 왼쪽에 표시됨 (인체 기준 오른쪽 눈)
SCREEN_RIGHT_IRIS = 473  # 화면 오른쪽에 표시됨 (인체 기준 왼쪽 눈)

# ---------- 웹캠 열기 ----------
cam = cv2.VideoCapture(0)

if not cam.isOpened():
    print("[오류] 웹캠을 열 수 없습니다. 다른 프로그램이 웹캠을 쓰고 있는지, 카메라 권한이 켜져있는지 확인하세요.")
    exit()

# 카메라에 높은 FPS를 요청 (카메라/드라이버가 지원하는 한도 내에서만 적용됨)
cam.set(cv2.CAP_PROP_FPS, 120)
# 일부 웹캠은 MJPG 코덱으로 바꿔야 고FPS가 열림 (기본 YUY2는 고FPS에서 대역폭 부족한 경우가 많음)
cam.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

reported_fps = cam.get(cv2.CAP_PROP_FPS)
print(f"[안내] 카메라가 보고하는 설정 FPS: {reported_fps:.0f} (실제 측정치는 화면의 FPS 표시를 참고하세요)")
print("[안내] 웹캠 인식 테스트 시작. 'q' 눌러서 종료, 's' 눌러서 스크린샷 저장.")

# ---------- 통계용 변수 ----------
total_frames = 0
detected_frames = 0
prev_time = time.time()
detection_rate = 0.0

fps_history = deque(maxlen=15)
smoothed_fps = 0

while True:
    success, frame = cam.read()
    if not success:
        print("[오류] 프레임을 읽어올 수 없습니다.")
        break

    total_frames += 1
    frame = cv2.flip(frame, 1)  # 거울 모드
    frame_h, frame_w, _ = frame.shape

    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb_frame)

    # ---------- FPS 계산 (최근 프레임 이동평균으로 안정화) ----------
    curr_time = time.time()
    instant_fps = 1 / (curr_time - prev_time) if curr_time != prev_time else 0
    prev_time = curr_time
    fps_history.append(instant_fps)
    smoothed_fps = sum(fps_history) / len(fps_history)

    face_detected = results.multi_face_landmarks is not None

    if face_detected:
        detected_frames += 1
        landmarks = results.multi_face_landmarks[0].landmark

        # 얼굴 전체 메쉬(그물망) 그리기 - 인식이 잘 되는지 시각적으로 확인
        mp_drawing.draw_landmarks(
            image=frame,
            landmark_list=results.multi_face_landmarks[0],
            connections=mp_face_mesh.FACEMESH_TESSELATION,
            landmark_drawing_spec=None,
            connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_tesselation_style(),
        )

        # 양쪽 눈동자 중심에 큰 점 찍기 (화면에 보이는 위치 기준 L/R)
        for idx, color, label in [
            (SCREEN_LEFT_IRIS, (0, 255, 0), "L"),
            (SCREEN_RIGHT_IRIS, (0, 200, 255), "R"),
        ]:
            lm = landmarks[idx]
            x, y = int(lm.x * frame_w), int(lm.y * frame_h)
            cv2.circle(frame, (x, y), 5, color, -1)
            cv2.putText(frame, label, (x + 8, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        status_text = "FACE DETECTED"
        status_color = (0, 255, 0)
    else:
        status_text = "NO FACE DETECTED - 얼굴을 화면 중앙에, 밝은 곳에서 비춰보세요"
        status_color = (0, 0, 255)

    # ---------- 화면에 정보 표시 ----------
    detection_rate = (detected_frames / total_frames) * 100 if total_frames > 0 else 0

    cv2.putText(frame, status_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
    cv2.putText(frame, f"Detection rate: {detection_rate:.1f}%", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(frame, "q: quit  s: screenshot", (10, frame_h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    # ---------- FPS 표시 (우측 상단, 크게, 상태에 따라 색상 변경) ----------
    if smoothed_fps >= 25:
        fps_color = (0, 255, 0)      # 초록: 원활함
    elif smoothed_fps >= 15:
        fps_color = (0, 255, 255)    # 노랑: 다소 느림
    else:
        fps_color = (0, 0, 255)      # 빨강: 너무 느림

    fps_text = f"{smoothed_fps:.0f} FPS"
    (text_w, text_h), _ = cv2.getTextSize(fps_text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)
    cv2.putText(frame, fps_text, (frame_w - text_w - 15, text_h + 15),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, fps_color, 2)

    cv2.imshow("MediaPipe Recognition Test", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('s'):
        cv2.imwrite("recognition_test.png", frame)
        print("[안내] recognition_test.png 로 저장했습니다.")

cam.release()
cv2.destroyAllWindows()

# ---------- 최종 결과 출력 ----------
print("\n===== 테스트 결과 =====")
print(f"총 프레임 수      : {total_frames}")
print(f"얼굴 인식된 프레임 : {detected_frames}")
print(f"인식 성공률       : {detection_rate:.1f}%")

if detection_rate < 70:
    print("[참고] 인식률이 낮습니다. 조명을 밝게 하거나, 얼굴이 화면 중앙에 오도록, 웹캠과의 거리를 조절해보세요.")
else:
    print("[참고] 인식이 안정적으로 되고 있습니다. 본 프로젝트 코드로 넘어가도 좋습니다.")
