"""ROS 쪽(arduino_node 브리지)까지 포함한 오프라인 시뮬레이터.

experiment_node가 /car/cmd/*로 내는 명령 → arduino_node가 실제로 쓰는 바이트(G 중복 제거,
200 ms keepalive V, 0.5 s cubic 속도 램프, 정지 시 램프 후 S) → firmware_model → 브리지가
LOOP_HZ(30 Hz)로 발행하는 /…/steering_pot·state 를 그대로 흉내 낸다.
recorder_node의 log.csv와 같은 (t, source, key, value) 행을 돌려준다.
"""
import os
import sys

import firmware_model as fm

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'ros2_ws', 'src', 'kiis_testbed'))
from kiis_testbed import programs  # noqa: E402

KEEPALIVE_S = 0.2
SPEED_RAMP_S = 0.5
LOOP_HZ = 30


def cubic(t, dur, v0, v1):
    if dur <= 0:
        return v1
    s = max(0.0, min(1.0, t / dur))
    return v0 + (v1 - v0) * (3 * s * s - 2 * s * s * s)


def run(events, duration, params, source, offset=1.0, seed=0, angle_trace=False, init_angle=0.0):
    """events: programs.build() 결과. offset: 브리지 기동 후 실험 시작까지[s].
    init_angle: 시작 조향각[deg] — 실측 장치가 중앙이 아닌 데서 출발했을 때 모델을 거기 맞춘다."""
    m = fm.FirmwareModel(params, seed=seed)
    m.angle = float(init_angle)
    rows, trace = [], []
    q = [(t + offset, c, v) for t, c, v in events]
    i = 0
    last = {}
    speed = target = ramp_from = 0
    ramp_t0 = 0.0
    stop_after = False
    next_keep = 0.0
    next_pub = 0.0
    pot = state = None
    total_ms = int((duration + offset + 0.5) * 1000)
    for k in range(total_ms):
        now = k / 1000.0
        while i < len(q) and q[i][0] <= now:
            _, c, v = q[i]
            i += 1
            rows.append((round(now, 4), 'cmd', c, '' if v is None else v)) if source == 'panel' else None
            if c == 'go':
                stop_after = False
                if last.get('gate') != 'G':
                    m.feed('G')
                    last['gate'] = 'G'
            elif c == 'drive':
                v = max(-255, min(255, int(v)))
                if v != target:
                    ramp_from, ramp_t0, target = speed, now, v
                stop_after = False
            elif c == 'stop':
                if target != 0:
                    ramp_from, ramp_t0 = speed, now
                target = 0
                stop_after = True
            elif c == 'steer_pulse':
                m.feed(v)
                last['steer'] = v
            elif c == 'steer':
                if last.get('steer') != v:
                    m.feed(v)
                    last['steer'] = v
        if now >= next_keep:
            next_keep += KEEPALIVE_S
            speed = target if target == ramp_from else int(round(cubic(now - ramp_t0, SPEED_RAMP_S, ramp_from, target)))
            m.feed('V%d\n' % speed)
            if stop_after and speed == 0:
                if last.get('gate') != 'S':
                    m.feed('S')
                    last['gate'] = 'S'
                stop_after = False
        m.step(1)
        for _, line in m.pop_lines():
            if line in ('0', '1', '2'):
                state = int(line)
            elif line.startswith('P '):
                pot = int(line[2:])
        if angle_trace:
            trace.append((now, m.angle))
        if now >= next_pub:
            next_pub += 1.0 / LOOP_HZ
            if state is not None:
                rows.append((round(now, 4), source, 'state', state))
            if pot is not None:
                rows.append((round(now, 4), source, 'steering_pot', pot))
    return (rows, trace) if angle_trace else rows


def build(name, **kw):
    return programs.build(name, **kw)
