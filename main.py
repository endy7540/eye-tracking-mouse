import cv2
import mediapipe as mp
import pyautogui

# 화면 해상도
screen_w, screen_h = pyautogui.size()

# MediaPipe FaceMesh 설정 (refine_landmarks=True 해야 홍채 랜드마크 나옴)
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    refine_landmarks=True,
    max_num_faces=1,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

cam = cv2.VideoCapture(0)

while True:
    success, frame = cam.read()
    if not success:
        break

    frame = cv2.flip(frame, 1)  # 좌우 반전 (거울 모드)
    frame_h, frame_w, _ = frame.shape
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb_frame)

    if results.multi_face_landmarks:
        landmarks = results.multi_face_landmarks[0].landmark

        # 오른쪽 눈동자(iris) 랜드마크 인덱스: 468~472
        for id, lm in enumerate(landmarks[468:472]):
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