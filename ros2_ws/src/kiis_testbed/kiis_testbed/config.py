"""kiis_testbed 설정 — autodrive_skku config.py에서 이 패키지가 실제로 쓰는 값만 남겼다.

미션·비전·라이다·오도메트리 값은 가져오지 않았다(그 노드들이 없다).
"""
import os

# ---- 차량/패널 아두이노 (car_controller.ino, 9600 bps) ----
ARDUINO_PORT = None        # 예: "/dev/ttyACM0" — None이면 ports.autodetect_ports()
ARDUINO_BAUD = 9600
LOOP_HZ = 30               # 브리지가 /…/state·steering_pot·steering_angle을 발행하는 주기

# ---- Unity 디지털 트윈 (TwinFirmware.cs가 car_controller.ino 규약으로 응답) ----
# WSL2에서 윈도우 쪽 Unity로 붙을 때는 127.0.0.1 대신 윈도우 호스트 IP를 쓴다
# (launch가 /etc/resolv.conf의 nameserver로 자동 추정; mirrored 네트워킹이면 127.0.0.1).
TWIN_PORT = 55002

# ---- 조향 ----
STEERING_LIMIT_DEG = 20.0  # float 고정 — 정수면 각도 클램프 결과가 int가 돼 Float32 발행이 죽는다
# 브리지의 라이브 조향 POT 칼만필터 (ADC count 공간). ROS 파라미터로 덮어쓸 수 있다.
ARDUINO_STEERING = dict(
    kf_process_noise=1.0,       # ADC^2/tick
    kf_measurement_noise=4.0,   # ADC^2
)

# ---- teleop 녹화 (카메라 노드가 /camera/front·/camera/back을 발행할 때만 파일이 생긴다) ----
TELEOP_RECORD_DIR = os.path.expanduser("~/kiis_logs/teleop_recordings")
TELEOP_RECORD_FPS = 20.0

# ---- 실험 기록 (recorder_node) ----
RUN_DIR = os.path.expanduser("~/kiis_logs/runs")
