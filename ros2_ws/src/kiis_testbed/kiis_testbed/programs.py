"""실험 명령 프로그램 — experiment_node(ROS)와 twin/dryrun.py(오프라인 점검)가 같이 쓴다.

각 프로그램은 (시각[s], 명령, 값) 목록과 총 길이[s]를 돌려준다. 명령은 /car/cmd/<명령> 토픽 이름과 같다:
  go(None) · stop(None) · drive(int, -255..255) · steer_pulse("L"/"R") · steer("F")
조향 펄스는 car_controller.ino 기준 120 ms라, 펄스 사이 간격(gap)은 그보다 길어야 각 펄스가 따로 나간다
(펄스 중에 L/R이 또 오면 펌웨어가 펄스를 연장한다).
"""


def steps(n=4, gap=0.25, hold=2.5):
    """중앙 → 좌(n펄스) → 우(2n펄스) → 중앙(n펄스). 묶음 계단 응답."""
    ev, t = [(0.5, 'go', None)], 1.0
    for k, d in ((n, 'L'), (2 * n, 'R'), (n, 'L')):
        for _ in range(k):
            ev.append((round(t, 3), 'steer_pulse', d))
            t += gap
        t += hold
    return ev, t + 1.0


def staircase(n=4, gap=0.8):
    """펄스 하나씩 gap 간격 — 펄스당 각도·백래시·지연을 따로 보기 위한 계단."""
    ev, t = [(0.5, 'go', None)], 1.0
    for k, d in ((n, 'L'), (2 * n, 'R'), (n, 'L')):
        for _ in range(k):
            ev.append((round(t, 3), 'steer_pulse', d))
            t += gap
    return ev, t + 1.5


def drive(pwm=60, n=2, gap=0.25):
    """구동 명령 계단(앞 → 정지 → 뒤 → 정지) + 조향 n펄스. 상태(0/1/2)와 램프를 본다."""
    ev = [(0.5, 'go', None), (1.0, 'drive', pwm), (3.0, 'drive', 0), (4.0, 'drive', -pwm), (6.0, 'drive', 0)]
    for k in range(n):
        ev.append((round(2.0 + k * gap, 3), 'steer_pulse', 'L'))
    return ev, 7.5


PROGRAMS = {'steps': steps, 'staircase': staircase, 'drive': drive}


def build(name, **kw):
    ev, dur = PROGRAMS[name](**{k: v for k, v in kw.items() if v is not None})
    ev = sorted(ev, key=lambda e: e[0])
    ev.append((round(dur - 0.2, 3), 'stop', None))
    return ev, dur
