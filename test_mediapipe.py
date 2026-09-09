"""
MediaPipe FaceMesh 웹캠 인식 테스트 스크립트
----------------------------------------
목적: 웹캠 영상에서 MediaPipe가 얼굴/눈동자(iris)를 제대로 인식하는지 확인.

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

# 왼쪽/오른쪽 눈동자 중심 랜드마크 인덱스 (refine_landmarks=True일 때)
LEFT_IRIS_CENTER = 473
RIGHT_IRIS_CENTER = 468

# ---------- 웹캠 열기 ----------
cam = cv2.VideoCapture(0)

if not cam.isOpened():
    print("[오류] 웹캠을 열 수 없습니다. 다른 프로그램이 웹캠을 쓰고 있는지, 카메라 권한이 켜져있는지 확인하세요.")
    exit()

print("[안내] 웹캠 인식 테스트 시작. 'q' 눌러서 종료, 's' 눌러서 스크린샷 저장.")

# ---------- 통계용 변수 ----------
total_frames = 0
detected_frames = 0
prev_time = time.time()
detection_rate = 0.0

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

    # ---------- FPS 계산 ----------
    curr_time = time.time()
    fps = 1 / (curr_time - prev_time) if curr_time != prev_time else 0
    prev_time = curr_time

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

        # 양쪽 눈동자 중심에 큰 점 찍기 (실제 추적에 쓸 좌표)
        for idx, color, label in [
            (LEFT_IRIS_CENTER, (0, 255, 0), "L"),
            (RIGHT_IRIS_CENTER, (0, 200, 255), "R"),
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
    cv2.putText(frame, f"FPS: {fps:.1f}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(frame, f"Detection rate: {detection_rate:.1f}%", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(frame, "q: quit  s: screenshot", (10, frame_h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

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