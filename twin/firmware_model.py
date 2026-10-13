"""차량/패널 펌웨어(autodrive_skku arduino/car_controller/car_controller.ino) + 조향 기구의 동작 모델.

Unity 디지털 트윈(TwinFirmware.cs)과 같은 규칙·같은 파라미터를 쓴다. 용도:
  1) 하드웨어 없이 파이프라인을 미리 돌려 보는 가짜 장치(dry run) — 결과를 논문 데이터로 쓰면 안 된다
  2) analyze.py 에서 패널 응답에 맞춰 트윈 파라미터를 맞출 때(fitting) 오프라인 시뮬레이터

car_controller.ino 규약 (9600 bps):
  PC→MCU: G/1 주행 허용(V 전이면 기본 속도 100) · 2 후진 · S/3 정지 · V<int>\n 속도 · L/R 120 ms 조향 펄스 · F 조향 정지
  MCU→PC: 0/1/2 상태(변화 시 또는 100 ms마다) · P <adc> 조향 POT(50 ms마다)
  - 아무 바이트나 받으면 워치독 시각 갱신. V를 한 번이라도 받은 뒤 500 ms 동안 수신이 없으면 속도 0
  - 조향은 G와 무관하게 동작. 펄스 중 L/R이 다시 오면 그 시각부터 120 ms로 연장(방향은 새 명령)
  - PC의 'L'(좌회전 요청)은 펌웨어에서 물리적 steerRight()로 처리되지만 결과는 좌회전 — 모델은 의미 기준(좌 = +)
"""
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_SPEED = 100
WATCHDOG_MS = 500
STATUS_PRINT_MS = 100
POT_PRINT_MS = 50
PARSE_INT_TIMEOUT_MS = 20      # Serial.setTimeout(20)

DEFAULT_PARAMS = {
    # 조향 기구 — 모터가 도는 동안 deg_per_pulse/steer_pulse_ms [deg/ms]로 움직인다고 본다.
    # 120 ms 펄스의 각도는 07-28 실측 6.1~12.2 deg(기어 교체 전) → 하한 6.0을 초기값으로, 패널 실측으로 피팅
    "steer_pulse_ms": 120,
    "deg_per_pulse": 6.0,
    "steer_lag_ms": 0.0,        # 명령 ~ 조향축이 움직이기 시작할 때까지
    "backlash_deg": 0.0,        # 방향을 바꾼 뒤 먹히는 각도
    "steer_limit_deg": 20.0,
    # 가변저항: arduino_node.adc_to_deg와 같은 좌/우 2점 선형 매핑 (좌 한계 = +limit)
    "pot_left_adc": 825,
    "pot_right_adc": 146,
    "pot_noise_adc": 0.0,
    # 구동 (aloha.toml 07-27 PWM-속도 실측 곡선) / 기하
    "speed_calibration_pwm": [15, 20, 25, 50, 75, 100, 125, 140, 150, 255],
    "speed_calibration_mps": [0.0, 0.0667, 0.120, 0.3408, 0.5033, 0.6167, 0.6875, 0.720, 0.735, 1.00],
    "wheelbase_m": 0.54,
}


def load_params(path=None):
    p = dict(DEFAULT_PARAMS)
    path = path or os.path.join(HERE, 'twin_params.json')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            p.update({k: v for k, v in json.load(f).items() if not k.startswith('_')})
    return p


def angle_to_adc(p, deg):
    lim = p['steer_limit_deg']
    r, l = p['pot_right_adc'], p['pot_left_adc']
    return r + (deg + lim) / (2 * lim) * (l - r)


def adc_to_angle(cal, adc):
    """arduino_node.adc_to_deg와 같은 식(클램프 포함). cal: pot_left_adc / pot_right_adc / steer_limit_deg"""
    l, r, lim = cal['pot_left_adc'], cal['pot_right_adc'], cal.get('steer_limit_deg', 20.0)
    if l == r:
        return 0.0
    deg = -lim + (adc - r) / (l - r) * (2 * lim)
    return max(-lim, min(lim, deg))


def pwm_to_speed(p, pwm):
    xs, ys = p['speed_calibration_pwm'], p['speed_calibration_mps']
    a = abs(pwm)
    if a <= xs[0]:
        v = 0.0
    elif a >= xs[-1]:
        v = ys[-1]
    else:
        i = 1
        while a > xs[i]:
            i += 1
        v = ys[i - 1] + (ys[i] - ys[i - 1]) * (a - xs[i - 1]) / (xs[i] - xs[i - 1])
    return v if pwm >= 0 else -v


class FirmwareModel:
    """1 ms 단위로 도는 car_controller.ino + 조향 기구. feed(str)로 명령, step(ms)로 시간 진행, 응답은 pop_lines()."""

    def __init__(self, params=None, seed=0):
        self.p = params or load_params()
        self.rng = random.Random(seed)
        self.t = 0
        self.out = []
        self.can_go = False
        self.cmd_speed = 0
        self.use_serial_speed = False
        self.last_serial = 0
        self.steer_start = None      # 펄스 시작 시각(ms), None = 정지
        self.steer_dir = 0           # +1 좌, -1 우 (의미 기준)
        self.last_state = -1
        self.last_status_ms = -10 ** 9
        self.last_pot_ms = -10 ** 9
        self.reading_v = False
        self.v_digits = ''
        self.v_start = 0
        # 기구
        self.angle = 0.0
        self.motor_hist = []         # (시각, 방향) — steer_lag_ms 만큼 늦게 기구에 반영
        self.slack = 0.0             # 남은 백래시
        self.last_move_dir = 0
        self.speed = 0.0
        self.x = self.y = self.yaw = 0.0
        self._print_state(0)

    def _emit(self, s):
        self.out.append((self.t, s))

    # ---- 펌웨어 ----
    def feed(self, data):
        for c in data:
            self._byte(c)

    def _finish_v(self):
        try:
            v = int(self.v_digits) if self.v_digits not in ('', '-') else 0
        except ValueError:
            v = 0
        self.cmd_speed = max(-255, min(255, v))
        self.use_serial_speed = True
        self.reading_v = False
        self.v_digits = ''

    def _byte(self, c):
        self.last_serial = self.t
        if self.reading_v:
            if c.isdigit() or (c == '-' and self.v_digits == ''):
                self.v_digits += c
                return
            if self.v_digits == '' and not c.isdigit():
                # parseInt는 숫자가 나올 때까지 앞의 비숫자 문자를 버린다
                return
            self._finish_v()          # 비숫자 문자는 소비하지 않고 아래에서 명령으로 처리
        if c in 'G1':
            self.can_go = True
            if not self.use_serial_speed:
                self.cmd_speed = DEFAULT_SPEED
        elif c == '2':
            self.can_go = True
            if not self.use_serial_speed:
                self.cmd_speed = -DEFAULT_SPEED
        elif c in 'S3':
            self.can_go = False
        elif c == 'V':
            self.reading_v, self.v_digits, self.v_start = True, '', self.t
        elif c == 'F':
            self.steer_start = None
            self._motor(0)
        elif c in 'LR':
            self.steer_start = self.t
            self.steer_dir = 1 if c == 'L' else -1
            self._motor(self.steer_dir)

    def _motor(self, d):
        self.motor_hist.append((self.t, d))

    def _print_state(self, st):
        if st != self.last_state or self.t - self.last_status_ms >= STATUS_PRINT_MS:
            self._emit(str(st))
            self.last_state, self.last_status_ms = st, self.t

    def _tick(self):
        p = self.p
        if self.reading_v and self.t - self.v_start >= PARSE_INT_TIMEOUT_MS:
            self._finish_v()
        if self.steer_start is not None and self.t - self.steer_start >= p['steer_pulse_ms']:
            self.steer_start = None
            self._motor(0)
        tripped = self.use_serial_speed and self.t - self.last_serial > WATCHDOG_MS
        sp = 0 if (not self.can_go or tripped) else self.cmd_speed
        self._print_state(1 if sp > 0 else (2 if sp < 0 else 0))
        if self.t - self.last_pot_ms >= POT_PRINT_MS:
            self.last_pot_ms = self.t
            adc = angle_to_adc(p, self.angle) + self.rng.gauss(0, p['pot_noise_adc'])
            self._emit('P %d' % max(0, min(1023, round(adc))))
        # 기구: lag 만큼 지난 모터 상태로 움직인다
        lagged = self.t - p['steer_lag_ms']
        d, keep_from = 0, 0
        for i, (ts, md) in enumerate(self.motor_hist):
            if ts <= lagged:
                d, keep_from = md, i
            else:
                break
        # 지금 유효한 마지막 상태(keep_from)는 남기고 그 이전만 버린다 (TwinFirmware.cs와 같은 방식)
        del self.motor_hist[:keep_from]
        if d != 0:
            step = p['deg_per_pulse'] / p['steer_pulse_ms']
            if self.last_move_dir != 0 and d != self.last_move_dir:
                self.slack = p['backlash_deg']
            self.last_move_dir = d
            if self.slack > 0:
                eat = min(self.slack, step)
                self.slack -= eat
                step -= eat
            lim = p['steer_limit_deg']
            self.angle = max(-lim, min(lim, self.angle + d * step))
        # 차량 운동(자전거 모델) — 패널은 바퀴가 없어 비교에 쓰지 않지만 트윈과 같게 둔다
        self.speed = pwm_to_speed(p, sp)
        dt = 0.001
        self.yaw += self.speed / p['wheelbase_m'] * math.tan(math.radians(self.angle)) * dt
        self.x += self.speed * math.cos(self.yaw) * dt
        self.y += self.speed * math.sin(self.yaw) * dt
        self.t += 1

    def step(self, ms):
        for _ in range(int(ms)):
            self._tick()

    def pop_lines(self):
        o, self.out = self.out, []
        return o
