# -*- coding: utf-8 -*-
"""
camera_worker.py — 카메라 읽기를 "별도 스레드"에서 계속 돌리는 부분

원본 gaze_tracker.py는 while True: 안에서 cap.read() → 계산 → cv2.imshow()를
한 몸처럼 반복했습니다. 그런데 PyQt도 자기만의 반복문(이벤트 루프)을 돌면서 창을 그리기 때문에,
둘을 한 스레드에 두면 카메라를 기다리는 동안 화면이 멈춥니다.

그래서 카메라 읽기는 QThread(부업 스레드)에서 돌리고, 한 프레임을 처리할 때마다
결과(feat, opens)를 frame_ready 신호로 화면 쪽에 던져줍니다. 이 파일은 지금이
캘리브레이션 중인지 실사용 중인지 모르고, 그 판단은 신호를 받는 main.py가 합니다.
"""
import time

import cv2
import mediapipe as mp
from PyQt5 import QtCore

from gaze_core import extract_features


class CameraWorker(QtCore.QThread):
    frame_ready = QtCore.pyqtSignal(object, object, float)   # (feat 또는 None, opens 또는 None, 시각)
    camera_error = QtCore.pyqtSignal(str)                     # 카메라를 열 수 없거나 계속 실패했을 때

    def __init__(self, camera_index=0, hd=False, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self.hd = hd
        self._running = False

    def stop(self):
        """메인 스레드에서 호출: 다음 반복에서 자연스럽게 끝나도록 플래그만 내림."""
        self._running = False

    def run(self):
        """start()를 부르면 이 메서드가 별도 스레드에서 실행됨."""
        try:
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)

            # [원본: main()] 기본 640x480, --hd일 때만 더 높은 해상도 시도
            res_candidates = [(1920, 1080), (1280, 720), (640, 480)] if self.hd else [(640, 480)]
            for w, h in res_candidates:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
                if int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) >= w * 0.9:
                    break

            # [원본: main()] 카메라 워밍업 — 열자마자 읽으면 실패하는 경우가 있어 잠깐 대기
            for _ in range(30):
                ok, _ = cap.read()
                if ok:
                    break
                time.sleep(0.05)
            else:
                self.camera_error.emit("웹캠을 초기화하지 못했습니다.\n카메라가 다른 프로그램에서 "
                                       "사용 중인지, 카메라 번호(--camera)가 맞는지 확인하세요.")
                cap.release()
                return

            face_mesh = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1, refine_landmarks=True,
                min_detection_confidence=0.5, min_tracking_confidence=0.5)

            fail_count = 0
            self._running = True
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    fail_count += 1
                    if fail_count > 60:   # 약 2초 이상 연속 실패해야만 진짜 오류로 판단 [원본 동일]
                        self.camera_error.emit("웹캠에서 프레임을 읽지 못했습니다.")
                        break
                    time.sleep(0.03)
                    continue
                fail_count = 0
                feat, opens = extract_features(frame, face_mesh)
                self.frame_ready.emit(feat, opens, time.time())

            cap.release()
            face_mesh.close()
        except Exception as e:     # 스레드 안의 오류가 조용히 묻히지 않도록 화면에 알림
            self.camera_error.emit(f"카메라 스레드 오류: {e}")
