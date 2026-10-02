import math
import random
import cv2
import numpy as np
from collections import deque
from filtertest import GazeStabilizer, OneEuroFilter1D, LowPassFilter

# 전역 마우스 위치 및 상태 변수
current_mouse_x, current_mouse_y = 640, 360

def mouse_handler(event, x, y, flags, param):
    global current_mouse_x, current_mouse_y
    if event == cv2.EVENT_MOUSEMOVE:
        current_mouse_x, current_mouse_y = x, y

# ==========================================
# 1. 노이즈 만들기 파트
# ==========================================
# 기존 함수를 아래 내용으로 교체하세요.
def generate_noisy_sensor(mouse_x, mouse_y, center_x, center_y, noise_level=15.0):
    """기본 떨림 외에 눈 깜빡임이나 자세 변경으로 인한 극단적인 휨(Outlier) 노이즈를 주입합니다."""
    sensor_raw_x = mouse_x - center_x
    sensor_raw_y = mouse_y - center_y

    # 1. 평소의 잔잔한 고주파 떨림
    noisy_x = sensor_raw_x + random.uniform(-noise_level, noise_level)
    noisy_y = sensor_raw_y + random.uniform(-noise_level, noise_level)

    # 2. 극단적 노이즈 (약 3% 확률로 시선이 갑자기 훅 튀는 현상 모사)
    # 노이즈 레벨이 높을수록 튀는 폭도 커지도록 설정합니다.
    if random.random() < 0.03: 
        jump_scale = random.uniform(3.0, 7.0) * (noise_level / 15.0)
        direction = random.choice([-1, 1])
        noisy_x += noise_level * jump_scale * direction
        noisy_y += noise_level * jump_scale * direction

    return noisy_x, noisy_y

# ==========================================
# 2. 필터 적용 파트
# ==========================================
def apply_gaze_filter(stabilizer, noisy_x, noisy_y):
    """GazeStabilizer를 통해 노이즈가 낀 좌표를 안정화된 좌표로 변환합니다."""
    filtered_x, filtered_y = stabilizer.update(noisy_x, noisy_y)
    return filtered_x, filtered_y

# ==========================================
# 3. 화면 표시 파트
# ==========================================
def draw_simulation_canvas(canvas, width, height, center_x, center_y, 
                           noisy_x, noisy_y, filtered_x, filtered_y, 
                           raw_trail, filtered_trail, stabilizer):
    """캔버스를 초기화하고 기준선, 궤적, 현재 위치 점, HUD 정보를 렌더링합니다."""
    canvas.fill(30)

    # 십자가 기준선
    cv2.line(canvas, (int(center_x), 0), (int(center_x), height), (50, 50, 50), 1)
    cv2.line(canvas, (0, int(center_y)), (width, int(center_y)), (50, 50, 50), 1)

    # 궤적 선(Trail) 그리기
    for i in range(1, len(raw_trail)):
        cv2.line(canvas, raw_trail[i-1], raw_trail[i], (0, 0, 100), 1)
    for i in range(1, len(filtered_trail)):
        cv2.line(canvas, filtered_trail[i-1], filtered_trail[i], (0, 200, 0), 2)

    # 렌더링 좌표 계산 (중앙 원점 -> 화면 픽셀 좌표)
    render_raw_x = noisy_x + center_x
    render_raw_y = noisy_y + center_y

    if filtered_x is not None and filtered_y is not None:
        render_filtered_x = filtered_x + center_x
        render_filtered_y = filtered_y + center_y
    else:
        render_filtered_x, render_filtered_y = render_raw_x, render_raw_y

    # 현재 위치 점 그리기 (빨강: 노이즈 원본 / 초록: 필터 적용 결과)
    cv2.circle(canvas, (int(render_raw_x), int(render_raw_y)), 5, (0, 0, 255), -1)
    cv2.circle(canvas, (int(render_filtered_x), int(render_filtered_y)), 8, (0, 255, 0), -1)
    cv2.circle(canvas, (int(render_filtered_x), int(render_filtered_y)), 12, (255, 255, 255), 1)

    # HUD 정보 텍스트 오버레이
    hud_texts = [
        f"EMA Alpha (+/-): {stabilizer.ema_alpha:.2f}",
        f"Euro Beta (W/S): {stabilizer.euro_x.beta:.4f}",
        f"Outlier Count: {stabilizer.outlier_count} / {stabilizer.max_outlier_frames}",
        "Controls: [SPACE] Teleport | [+/-] Alpha | [W/S] Beta | [Q] Quit"
    ]
    
    for idx, text in enumerate(hud_texts):
        cv2.putText(canvas, text, (20, 30 + (idx * 25)), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1, cv2.LINE_AA)


def nothing(x):
    pass

def main():
    global current_mouse_x, current_mouse_y
    width, height = 1280, 720
    center_x, center_y = width / 2, height / 2
    canvas = np.zeros((height, width, 3), dtype=np.uint8)

    cv2.namedWindow("Gaze Filter Modular Studio")
    cv2.setMouseCallback("Gaze Filter Modular Studio", mouse_handler)

    # ==========================================
    # 실시간 조절을 위한 OpenCV 트랙바 생성
    # ==========================================
    cv2.createTrackbar("Noise Level", "Gaze Filter Modular Studio", 15, 100, nothing)
    cv2.createTrackbar("Min Cutoff (x10)", "Gaze Filter Modular Studio", 5, 50, nothing)
    cv2.createTrackbar("Beta (x10000)", "Gaze Filter Modular Studio", 70, 500, nothing)
    cv2.createTrackbar("EMA Alpha (x100)", "Gaze Filter Modular Studio", 80, 99, nothing)

    stabilizer = GazeStabilizer(fps=60.0)

    raw_trail = deque(maxlen=30)
    filtered_trail = deque(maxlen=30)

    print("=== Gaze Filter Modular Studio (슬라이드바 연동) 실행 ===")

    while True:
        # 키 입력 및 제어 처리
        key = cv2.waitKey(16) & 0xFF
        if key == ord('q'):
            break
        elif key == ord(' '):
            if current_mouse_x < center_x:
                current_mouse_x, current_mouse_y = width - 150, height - 150
            else:
                current_mouse_x, current_mouse_y = 150, 150

        # ==========================================
        # 트랙바 위치 값을 먼저 읽어와서 변수에 할당
        # ==========================================
        t_noise = cv2.getTrackbarPos("Noise Level", "Gaze Filter Modular Studio")
        t_cutoff = cv2.getTrackbarPos("Min Cutoff (x10)", "Gaze Filter Modular Studio") / 10.0
        t_beta = cv2.getTrackbarPos("Beta (x10000)", "Gaze Filter Modular Studio") / 10000.0
        t_alpha = cv2.getTrackbarPos("EMA Alpha (x100)", "Gaze Filter Modular Studio") / 100.0

        # 최소값 보정 방어 코드
        t_cutoff = max(0.01, t_cutoff)
        t_alpha = max(0.01, min(0.99, t_alpha))

        # 가중치 적용
        stabilizer.ema_alpha = t_alpha
        if hasattr(stabilizer, 'euro_x') and hasattr(stabilizer, 'euro_y'):
            stabilizer.euro_x.min_cutoff = t_cutoff
            stabilizer.euro_y.min_cutoff = t_cutoff
            stabilizer.euro_x.beta = t_beta
            stabilizer.euro_y.beta = t_beta

        # 1. 노이즈 만들기 (정의된 t_noise 값을 정상적으로 전달)
        noisy_x, noisy_y = generate_noisy_sensor(current_mouse_x, current_mouse_y, center_x, center_y, noise_level=float(t_noise))

        # 2. 필터 적용
        filtered_x, filtered_y = apply_gaze_filter(stabilizer, noisy_x, noisy_y)

        # 궤적 저장을 위한 픽셀 좌표 변환
        raw_trail.append((int(noisy_x + center_x), int(noisy_y + center_y)))
        if filtered_x is not None and filtered_y is not None:
            filtered_trail.append((int(filtered_x + center_x), int(filtered_y + center_y)))
        else:
            filtered_trail.append((int(noisy_x + center_x), int(noisy_y + center_y)))

        # 3. 화면 표시
        draw_simulation_canvas(canvas, width, height, center_x, center_y,
                               noisy_x, noisy_y, filtered_x, filtered_y,
                               raw_trail, filtered_trail, stabilizer)

        cv2.imshow("Gaze Filter Modular Studio", canvas)

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()

# 필터 사용 법

# # 센서의 노이즈 낀 좌표를 필터에 전달하여 정제된 좌표 획득
# filtered_x, filtered_y = stabilizer.update(noisy_x, noisy_y)


# # 1. 현재 설정된 가중치 값 확인하기 (조회)
# print(f"현재 min_cutoff: {stabilizer.euro_x.min_cutoff}")
# print(f"현재 beta (속도 감응): {stabilizer.euro_x.beta}")



# # 2. 가중치 값 실시간으로 수정하기 (예: 키보드 입력이나 설정 창 연동)
# new_min_cutoff = 0.8  # 값이 낮을수록 가만히 있을 때 떨림을 꽉 잡아줌 (기본 추천: 0.5 ~ 1.0)
# new_beta = 0.007      # 값이 높을수록 빠르게 시선을 움직일 때 지연(Lag)이 줄어듦

# stabilizer.euro_x.min_cutoff = new_min_cutoff
# stabilizer.euro_y.min_cutoff = new_min_cutoff

# stabilizer.euro_x.beta = new_beta
# stabilizer.euro_y.beta = new_beta


# # 1. 현재 alpha 값 조회
# print(f"현재 EMA Alpha: {stabilizer.ema_alpha}")

# # 2. alpha 값 수정하기 (보통 0.3 ~ 0.9 사이로 조절)
# stabilizer.ema_alpha = 0.75 



# # 예시: 메인문에서 키보드 '+' / '-' 입력으로 실시간 조절할 때
# # stabilizer.ema_alpha = min(0.99, stabilizer.ema_alpha + 0.05)
# # stabilizer.ema_alpha = max(0.1, stabilizer.ema_alpha - 0.05)


# # 휨 판정 최대 허용 거리 수정
# stabilizer.max_jump_distance = 50.0  # 이 픽셀 이상 갑자기 튀면 노이즈로 간주

# # 이상치로 판정된 점을 몇 프레임 동안 붙잡아둘 것인지 수정
# stabilizer.max_outlier_frames = 3


# # 외부 설정값(예: 사용자가 UI 슬라이더로 조절한 값)
# user_cutoff = 0.8        # 0.1 ~ 1.0 (가장 추천하는 기본값: 0.5 전후)
# user_beta = 0.01         # 0.001 ~ 0.02 (가장 추천하는 기본값: 0.007 전후)
# user_alpha = 0.85        # 0.1 ~ 0.99 (가장 추천하는 기본값: 0.75 전후)

# # 함수에 변수 형태로 한 번에 전달
# stabilizer.set_parameters(
#     min_cutoff=user_cutoff,
#     beta=user_beta, 
#     ema_alpha=user_alpha
# )