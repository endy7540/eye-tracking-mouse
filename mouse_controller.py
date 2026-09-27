"""
mouse_controller.py
--------------------
담당 모듈: 마우스 이동 및 클릭 제어 로직
관련 문서: 요구사양서_검증설계서.xlsx / SRS_TC_Matrix.xlsx (팀 공식본 기준 ID로 정렬)

책임 범위:
    - 좌표 변환/노이즈 보정 모듈(팀원 담당)로부터 "최종 화면 좌표"를 전달받아
      실제 마우스 포인터를 이동시킨다. (좌표 계산 로직 자체는 이 모듈 책임이 아님)
    - UI/클릭모드 모듈(팀원 담당)로부터 "클릭 트리거 신호"를 전달받아
      실제 클릭 동작을 실행한다. (윙크/응시시간 등 클릭 판단 로직은 이 모듈 책임이 아님)
    - 웹캠 연결 해제 알림을 받으면 즉시 제어를 해제하고(MR-10), 화면 해상도가
      바뀌어도 매 호출마다 최신 해상도를 반영해 좌표를 clamp한다(MR-11).

각 메서드 docstring의 [MR-xx], [NFR-xx] 표기는 팀 공식 요구사양서의 ID와 매핑됩니다.
"""

import logging
import math
import threading
import time

import pyautogui

pyautogui.PAUSE = 0
pyautogui.FAILSAFE = True

# 다른 실행 스크립트가 나중에 pyautogui.moveTo/click을 가로챌(monkey-patch) 수도 있으므로,
# 이 모듈이 실제로 마우스를 움직일 때 쓸 "진짜" 함수 객체를 import 시점에 미리 캡처해둔다.
# (이렇게 안 하면, 누군가 pyautogui.moveTo를 이 클래스로 연결했을 때
#  update_position() -> pyautogui.moveTo(패치됨) -> update_position() -> ... 무한 재귀에 빠진다.)
_real_move_to = pyautogui.moveTo
_real_click = pyautogui.click
_real_double_click = pyautogui.doubleClick

logger = logging.getLogger("mouse_controller")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")


class ClickType:
    """UI 모듈과 합의할 클릭 이벤트 종류 (MR-04 인터페이스 스펙)."""
    LEFT = "left"
    RIGHT = "right"
    DOUBLE = "double"

    ALL = (LEFT, RIGHT, DOUBLE)


class MouseController:
    """
    마우스 이동 및 클릭 제어를 담당하는 클래스.

    사용 예:
        controller = MouseController()
        controller.update_position(960, 540)      # 좌표 모듈이 매 프레임 호출 (MR-01, MR-02)
        controller.trigger_click(ClickType.LEFT)   # UI 모듈이 클릭 판단 시 호출 (MR-04, MR-05)
        controller.set_camera_connected(False)     # 비전 모듈이 웹캠 분리를 감지했을 때 호출 (MR-10)
    """

    def __init__(self, screen_size=None, debounce_ms=300, input_timeout_ms=2000):
        """
        Args:
            screen_size: (width, height) 튜플을 명시하면 그 값으로 고정하고,
                None이면 [MR-11]에 따라 호출마다 pyautogui.size()로 실시간 해상도를 반영한다.
            debounce_ms: 클릭 디바운스 시간 (MR-06 확정값: 300ms)
            input_timeout_ms: 입력 두절 판단 기준 시간 (MR-08 확정값: 2000ms)
        """
        self._fixed_screen_size = screen_size
        self.screen_w, self.screen_h = screen_size or pyautogui.size()

        self.debounce_sec = debounce_ms / 1000.0
        self.input_timeout_sec = input_timeout_ms / 1000.0

        self._last_click_time = 0.0
        self._last_input_time = 0.0
        self._last_position = (self.screen_w // 2, self.screen_h // 2)

        self._camera_connected = True  # [MR-10]

        self._lock = threading.Lock()

        self.stats = {
            "moves_ok": 0,
            "moves_rejected_invalid": 0,
            "moves_rejected_camera_disconnected": 0,
            "moves_clamped": 0,
            "clicks_ok": 0,
            "clicks_rejected_debounce": 0,
            "clicks_rejected_input_timeout": 0,
            "clicks_rejected_camera_disconnected": 0,
            "exceptions_handled": 0,
            "camera_disconnect_events": 0,
            "resolution_changes_detected": 0,
        }

        logger.info(
            "MouseController 초기화 완료 - 화면 해상도: %sx%s (%s), 디바운스: %sms, 입력두절 기준: %sms",
            self.screen_w, self.screen_h,
            "고정" if screen_size else "실시간 감지",
            debounce_ms, input_timeout_ms,
        )

    # -----------------------------------------------------------------
    # 웹캠 연결 상태 (MR-10)
    # -----------------------------------------------------------------
    def set_camera_connected(self, connected):
        """
        [MR-10] 웹캠 물리적 분리/연결 끊김 알림 수신.

        웹캠 연결 여부 자체를 감지하는 것은 영상 캡처(비전) 모듈의 책임이며,
        이 메서드는 그 알림을 받아 "마우스 제어를 즉시 해제"하는 반응만 담당한다.
        False로 호출되면 이후의 update_position()/trigger_click() 호출은 전부 즉시 거부되고,
        True로 복귀하면 입력 두절 타이머가 리셋되어 다음 정상 좌표부터 바로 제어가 재개된다.
        """
        with self._lock:
            was_connected = self._camera_connected
            self._camera_connected = connected
            if was_connected and not connected:
                self.stats["camera_disconnect_events"] += 1
                logger.warning("웹캠 연결 해제 감지 - 마우스 제어를 즉시 해제합니다.")
            elif not was_connected and connected:
                self._last_input_time = 0.0
                logger.info("웹캠 재연결 감지 - 마우스 제어를 재개할 준비가 되었습니다.")

    def is_camera_connected(self):
        """현재 웹캠 연결 상태로 간주 중인지 반환 (테스트/모니터링용)."""
        with self._lock:
            return self._camera_connected

    # -----------------------------------------------------------------
    # 해상도 조회 (MR-11)
    # -----------------------------------------------------------------
    def _current_screen_size(self):
        """
        [MR-11] 화면 해상도/비율 변경 대응.

        생성자에 screen_size를 명시하지 않았다면, 호출할 때마다 pyautogui.size()로
        실제 OS 해상도를 다시 조회해 캐시를 갱신한다. 그래야 사용 중 해상도가
        바뀌어도(예: 1920x1080 -> 1280x720) 다음 좌표 이동부터 바로 새 경계값으로 clamp된다.
        고정 해상도가 필요한 테스트 상황을 위해 screen_size를 넘긴 경우엔 그 값을 그대로 쓴다.
        """
        if self._fixed_screen_size is not None:
            return self._fixed_screen_size
        try:
            w, h = pyautogui.size()
        except Exception:
            logger.exception("화면 해상도 조회 실패 - 이전 값을 유지합니다.")
            return self.screen_w, self.screen_h
        if (w, h) != (self.screen_w, self.screen_h):
            self.stats["resolution_changes_detected"] += 1
            logger.info("해상도 변경 감지: %sx%s -> %sx%s", self.screen_w, self.screen_h, w, h)
            self.screen_w, self.screen_h = w, h
        return w, h

    # -----------------------------------------------------------------
    # 좌표 수신 / 이동 (MR-01, MR-02, MR-03, MR-10, MR-11, NFR-01, NFR-03)
    # -----------------------------------------------------------------
    def update_position(self, x, y):
        """
        [MR-01] 좌표 수신 인터페이스.
        [MR-02] 화면 범위를 벗어나는 좌표는 경계값으로 보정.
        [MR-03] None/NaN 등 비정상 값은 이동을 skip.
        [MR-10] 웹캠 연결이 끊긴 상태면 이동을 거부.
        [MR-11] 매 호출마다 최신 화면 해상도를 반영해 clamp 기준을 갱신.
        [NFR-01] 수신~이동 완료까지 지연 50ms 이내를 목표로, 불필요한 연산 없이 즉시 처리.
        [NFR-03] 상위 모듈이 30fps로 호출해도 누락 없이 처리 가능해야 하므로 매 호출을 경량 처리.

        Returns:
            bool: 이동이 정상적으로 수행되었으면 True, skip/거부되었으면 False.
        """
        if not self.is_camera_connected():
            self.stats["moves_rejected_camera_disconnected"] += 1
            logger.debug("좌표 이동 거부: 웹캠 연결 해제 상태")
            return False

        if x is None or y is None:
            self.stats["moves_rejected_invalid"] += 1
            logger.debug("좌표 이동 skip: x 또는 y가 None (x=%s, y=%s)", x, y)
            return False
        try:
            x = float(x)
            y = float(y)
        except (TypeError, ValueError):
            self.stats["moves_rejected_invalid"] += 1
            logger.debug("좌표 이동 skip: 숫자로 변환 불가 (x=%r, y=%r)", x, y)
            return False
        if math.isnan(x) or math.isnan(y) or math.isinf(x) or math.isinf(y):
            self.stats["moves_rejected_invalid"] += 1
            logger.debug("좌표 이동 skip: NaN/Inf 값 (x=%s, y=%s)", x, y)
            return False

        screen_w, screen_h = self._current_screen_size()

        clamped_x = min(max(x, 0), screen_w - 1)
        clamped_y = min(max(y, 0), screen_h - 1)
        if (clamped_x, clamped_y) != (x, y):
            self.stats["moves_clamped"] += 1
            logger.debug("좌표 clamp 적용: (%.1f, %.1f) -> (%.1f, %.1f)", x, y, clamped_x, clamped_y)

        with self._lock:
            self._last_position = (clamped_x, clamped_y)
            self._last_input_time = time.time()

        try:
            _real_move_to(clamped_x, clamped_y, duration=0)
        except Exception:
            self.stats["exceptions_handled"] += 1
            logger.exception("마우스 이동 중 예외 발생 (좌표: %.1f, %.1f)", clamped_x, clamped_y)
            return False

        self.stats["moves_ok"] += 1
        return True

    # -----------------------------------------------------------------
    # 클릭 수신 / 실행 (MR-04, MR-05, MR-06, MR-07, MR-08, MR-10, NFR-02)
    # -----------------------------------------------------------------
    def trigger_click(self, click_type=ClickType.LEFT):
        """
        [MR-04] 클릭 트리거 수신 인터페이스.
        [MR-05] 수신된 이벤트 종류에 맞는 클릭 동작 실행.
        [MR-06] 300ms 이내 중복 클릭 신호는 무시(디바운스).
        [MR-07] 좌표를 별도로 넘기지 않고 pyautogui.click()을 인자 없이 호출함으로써
                "가장 최근에 이동시킨 위치"에서 클릭이 실행되도록 보장.
        [MR-08] 좌표 입력이 2000ms 이상 끊긴 상태(input stale)면 클릭을 실행하지 않음.
        [MR-10] 웹캠 연결이 끊긴 상태면 클릭을 거부.
        [NFR-02] 신호 수신~클릭 실행까지 지연 100ms 이내를 목표로 경량 처리.

        Returns:
            bool: 클릭이 실제로 실행되었으면 True, 거부(디바운스/입력두절/웹캠끊김/예외)되었으면 False.
        """
        if click_type not in ClickType.ALL:
            logger.warning("알 수 없는 클릭 타입: %r", click_type)
            return False

        if not self.is_camera_connected():
            self.stats["clicks_rejected_camera_disconnected"] += 1
            logger.debug("클릭 거부: 웹캠 연결 해제 상태")
            return False

        now = time.time()

        with self._lock:
            time_since_last_input = now - self._last_input_time
        if self._last_input_time == 0.0 or time_since_last_input > self.input_timeout_sec:
            self.stats["clicks_rejected_input_timeout"] += 1
            logger.debug(
                "클릭 무시: 입력 두절 상태 (마지막 좌표 입력 %.2f초 전, 기준 %.2f초)",
                time_since_last_input, self.input_timeout_sec,
            )
            return False

        with self._lock:
            if now - self._last_click_time < self.debounce_sec:
                self.stats["clicks_rejected_debounce"] += 1
                logger.debug("클릭 무시: 디바운스 구간 (%.0fms 이내 중복 신호)", self.debounce_sec * 1000)
                return False
            self._last_click_time = now

        try:
            if click_type == ClickType.LEFT:
                _real_click(button="left")
            elif click_type == ClickType.RIGHT:
                _real_click(button="right")
            elif click_type == ClickType.DOUBLE:
                _real_double_click()
        except Exception:
            self.stats["exceptions_handled"] += 1
            logger.exception("클릭 실행 중 예외 발생 (click_type=%s)", click_type)
            return False

        self.stats["clicks_ok"] += 1
        logger.info("클릭 실행됨: %s (위치: %s)", click_type, self._last_position)
        return True

    # -----------------------------------------------------------------
    # 상태 조회 (디버깅 / 모니터링 / 테스트용)
    # -----------------------------------------------------------------
    def is_input_alive(self):
        """현재 입력이 살아있는 상태인지(=2000ms 이내에 좌표가 갱신되었는지) 반환."""
        if self._last_input_time == 0.0:
            return False
        return (time.time() - self._last_input_time) <= self.input_timeout_sec

    def get_last_position(self):
        """가장 최근에 이동시킨 좌표를 반환 (테스트/디버깅용)."""
        with self._lock:
            return self._last_position

    def get_stats(self):
        """누적 통계를 반환 (검증설계서 TC 수행 시 결과 확인용)."""
        return dict(self.stats)


# ===========================================================================
# 수동 통합 테스트 (SRS_TC_Matrix.xlsx의 TC-01~13 + MR-10/11 신규 항목 간이 점검)
# 실제 좌표/클릭 모듈이 준비되기 전, 이 파일만으로 동작을 눈으로 확인하기 위한 용도.
# 실행하면 마우스가 실제로 움직이고 클릭도 발생하니, 중요한 작업 창을 닫고 실행할 것.
# ===========================================================================
if __name__ == "__main__":
    print("mouse_controller.py 수동 테스트를 시작합니다. 5초 후 마우스가 움직입니다...")
    time.sleep(5)

    controller = MouseController()

    print("[TC-01/02] 화면 중앙으로 이동")
    controller.update_position(controller.screen_w // 2, controller.screen_h // 2)
    time.sleep(1)

    print("[TC-03] 화면 밖 좌표(-500, -500) 전송 -> clamp 확인")
    controller.update_position(-500, -500)
    print("  clamp 결과 위치:", controller.get_last_position())
    time.sleep(1)

    print("[TC-04] None / NaN 좌표 전송 -> 이동 skip 확인")
    controller.update_position(None, None)
    controller.update_position(float("nan"), 100)

    print("[TC-05/06] 좌클릭 실행")
    controller.update_position(controller.screen_w // 2, controller.screen_h // 2)
    controller.trigger_click(ClickType.LEFT)

    print("[TC-07] 100ms 간격으로 3회 연속 클릭 시도 -> 1회만 실행되어야 함")
    for _ in range(3):
        controller.trigger_click(ClickType.LEFT)
        time.sleep(0.1)
    time.sleep(1)

    print("[TC-09] 2.5초간 좌표 입력 없이 대기 후 클릭 시도 -> 무시되어야 함")
    time.sleep(2.5)
    result = controller.trigger_click(ClickType.LEFT)
    print("  입력 두절 상태에서의 클릭 결과 (False가 정상):", result)

    print("\n[MR-10] 웹캠 연결 해제 시뮬레이션")
    controller.update_position(controller.screen_w // 2, controller.screen_h // 2)
    controller.set_camera_connected(False)
    move_result = controller.update_position(100, 100)
    click_result = controller.trigger_click(ClickType.LEFT)
    print("  연결 해제 상태에서의 이동/클릭 결과 (둘 다 False가 정상):", move_result, click_result)
    controller.set_camera_connected(True)
    print("  재연결 완료 - 다음 정상 좌표부터 제어 재개됨")

    print("\n[MR-11] 현재 해상도 조회:", controller._current_screen_size())
    print("  (OS 해상도를 바꾼 뒤 다시 update_position을 호출하면 새 해상도로 clamp됩니다)")

    print("\n===== 누적 통계 =====")
    for k, v in controller.get_stats().items():
        print(f"  {k}: {v}")
