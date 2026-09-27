"""
run_with_mouse_control.py
--------------------------
팀원이 만든 gaze_tracker.py(캘리브레이션 / 시선추적 / 윙크감지)는 단 한 글자도
수정하지 않고, 그 파일이 내부에서 호출하는 pyautogui.moveTo / pyautogui.click /
pyautogui.doubleClick 호출만 가로채서(monkey-patch) 우리 mouse_controller.py의
MouseController를 거치도록 만드는 "실행 스크립트"입니다.

동작 원리:
    파이썬에서 pyautogui.moveTo 같은 건 그냥 "pyautogui 모듈이 들고 있는 함수 객체"예요.
    gaze_tracker.py는 실행되는 매 순간마다 "지금 pyautogui.moveTo가 뭘 가리키고 있나"를
    찾아서 호출하기 때문에, 우리가 이 스크립트에서 그 이름표를 다른 함수로 바꿔치기해두면
    gaze_tracker.py의 소스코드는 그대로인데 실제로는 우리 코드가 대신 실행됩니다.

사용법:
    python run_with_mouse_control.py
    (인자를 넘기면 gaze_tracker.py의 main()에 그대로 전달됩니다. 예:
     python run_with_mouse_control.py --recalibrate)

전제 조건:
    - 이 파일, mouse_controller.py, gaze_tracker.py(팀원 원본, 무수정)가
      전부 같은 폴더에 있어야 합니다.
    - 아래 "5) 팀원 원본 코드 import" 부분의 파일명이 실제 팀원 파일명과
      다르면 그 줄만 바꿔주세요.
    - mediapipe==0.10.21 (팀 결정 버전)이 설치되어 있어야 합니다.

한계 (소스를 안 건드려서 생기는 제약):
    - 웹캠이 끊기면 gaze_tracker.py 자체의 while 루프가 `break`로 완전히 종료돼요.
      이 스크립트는 "끊긴 순간 마우스 제어를 즉시 막는 것"까지는 하지만,
      끊긴 뒤 재시도하며 기다리는 동작은 gaze_tracker.py 쪽 코드를 직접
      고쳐야 가능합니다 (그건 저희 담당 범위를 벗어나는 수정이라 손대지 않았어요).
"""

import logging
import os
import sys

import cv2
import pyautogui

from mouse_controller import MouseController, ClickType

# ---------------------------------------------------------------------
# 1) 윙크/클릭 이벤트 로깅 설정
#    (gaze_tracker.py가 호출하는 pyautogui.click을 가로채는 지점에서 함께 기록)
# ---------------------------------------------------------------------
logger = logging.getLogger("gaze_tracker")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wink_events.log")
    _file_handler = logging.FileHandler(_log_path, encoding="utf-8")
    _file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_file_handler)

# ---------------------------------------------------------------------
# 2) 마우스 제어 로직 (담당 모듈) - 실제로 이동/클릭을 처리할 객체
# ---------------------------------------------------------------------
controller = MouseController()

# ---------------------------------------------------------------------
# 3) pyautogui 함수를 가로채서(monkey-patch) MouseController를 거치게 함
#    -> gaze_tracker.py 소스 코드는 전혀 건드리지 않음
# ---------------------------------------------------------------------
def _patched_move_to(x=None, y=None, *args, **kwargs):
    if x is not None and y is not None:
        controller.update_position(x, y)


def _patched_click(x=None, y=None, *args, **kwargs):
    button = kwargs.get("button", "left")
    if x is not None and y is not None:
        controller.update_position(x, y)
    fired = controller.trigger_click(button if button in ClickType.ALL else ClickType.LEFT)
    logger.info("클릭 가로챔: pos=(%s, %s) button=%s executed=%s", x, y, button, fired)
    return fired


def _patched_double_click(*args, **kwargs):
    fired = controller.trigger_click(ClickType.DOUBLE)
    logger.info("더블클릭 가로챔: executed=%s", fired)
    return fired


pyautogui.moveTo = _patched_move_to
pyautogui.click = _patched_click
pyautogui.doubleClick = _patched_double_click

# ---------------------------------------------------------------------
# 4) 웹캠 연결 해제 감지 (MR-10) - cv2.VideoCapture.read()를 가로채서 연결 상태를 추적.
#    gaze_tracker.py 안의 모든 cap.read() 호출(메인 루프 + 캘리브레이션 단계 전부)에
#    자동으로 적용됨 - 소스를 안 건드려도 똑같이 동작.
# ---------------------------------------------------------------------
_real_video_read = cv2.VideoCapture.read


def _patched_video_read(self, *args, **kwargs):
    ok, frame = _real_video_read(self, *args, **kwargs)
    if ok:
        if not controller.is_camera_connected():
            controller.set_camera_connected(True)
    else:
        controller.set_camera_connected(False)
    return ok, frame


cv2.VideoCapture.read = _patched_video_read

# ---------------------------------------------------------------------
# 5) 팀원 원본 코드 import (패치를 끝낸 "뒤"에 import해야 함)
#    ↓↓↓ 실제 팀원 파일명이 다르면 이 줄만 바꿔주세요 (예: gaze_tracker24) ↓↓↓
# ---------------------------------------------------------------------
import gaze_tracker as teammate_gaze  # noqa: E402

if __name__ == "__main__":
    print("[안내] 팀원 코드(gaze_tracker.py)는 수정 없이 그대로 실행하며,")
    print("       마우스 이동/클릭만 mouse_controller.py를 거치도록 연결했습니다.")
    teammate_gaze.main()
