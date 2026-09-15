# media-pipe 최신 버전용 코드 (2024.06.12 기준)
# mediapipe 라이브러리(v0.10.31 이상)에서는 기존의 레거시 API인
# mp.solutions 지원이 중단되어 해당 에러가 발생합니다.

# face_landmarker.task 모델을 사용하여 눈동자 위치를 추적하고, 이를 기반으로 마우스 커서를 이동시키는 예제 코드입니다.

import os
import time
import cv2
import mediapipe as mp
import pyautogui

# 화면 해상도
screen_w, screen_h = pyautogui.size()

# 현재 스크립트(main.py)가 위치한 폴더를 자동으로 파악해서 모델 경로 지정
current_dir = os.path.dirname(os.path.abspath(__file__))
model_path = os.path.join(current_dir, 'face_landmarker.task')

# 1. 최신 Tasks API 모듈 설정
BaseOptions = mp.tasks.BaseOptions
FaceLandmarker = mp.tasks.vision.FaceLandmarker
FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

# 2. 최신 FaceLandmarker 옵션 설정
options = FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=model_path),
    running_mode=VisionRunningMode.VIDEO,  # 실시간 비디오/웹캠 모드
    num_faces=1,
    min_face_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# 3. 객체 생성 및 실행
with FaceLandmarker.create_from_options(options) as face_landmarker:
    cam = cv2.VideoCapture(0)

    while cam.isOpened():
        success, frame = cam.read()
        if not success:
            break

        frame = cv2.flip(frame, 1)  # 좌우 반전 (거울 모드)
        frame_h, frame_w, _ = frame.shape
        
        # OpenCV 이미지를 MediaPipe 전용 이미지로 변환
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        # 비디오 모드용 타임스탬프(밀리초) 생성 후 탐지 실행
        timestamp_ms = int(time.time() * 1000)
        results = face_landmarker.detect_for_video(mp_image, timestamp_ms)

        # 결과 처리
        if results.face_landmarks:
            landmarks = results.face_landmarks[0]  # 첫 번째 얼굴의 랜드마크 리스트

            # 오른쪽 눈동자(iris) 랜드마크 인덱스: 468~471 (총 4개)
            for id, idx in enumerate(range(468, 472)):
                lm = landmarks[idx]
                x = int(lm.x * frame_w)
                y = int(lm.y * frame_h)
                cv2.circle(frame, (x, y), 3, (0, 255, 0), -1)

                if id == 1:  # 홍채 중심점 하나만 사용해 마우스 이동
                    screen_x = screen_w * lm.x
                    screen_y = screen_h * lm.y
                    pyautogui.moveTo(screen_x, screen_y)

        cv2.imshow("Eye Tracking Mouse", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cam.release()
    cv2.destroyAllWindows()