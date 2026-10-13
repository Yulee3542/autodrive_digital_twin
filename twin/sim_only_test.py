"""시뮬레이션 단독 적합성 테스트 — 패널 없이 Unity 트윈이 car_controller.ino 규칙대로 움직이는지.

같은 시각표의 바이트 명령을 Unity 트윈(TCP)과 파이썬 모델(firmware_model.py)에 똑같이 보내고
상태(0/1/2) 변화 시각과 조향각 변화량을 나란히 비교한다. (점검용 — 논문 표 수치 아님)

  python sim_only_test.py                 # 윈도우에서 Unity Play 중일 때 (127.0.0.1:55002)
  python sim_only_test.py --host 172.27.32.1   # WSL에서

트윈은 연결이 바뀌어도 상태(각도, V 수신 여부)를 유지하므로, 시나리오는 V0·S·F로 시작해 출발점을 맞추고
조향은 절대각이 아닌 변화량으로 비교한다.
"""
import argparse
import socket
import threading
import time

import firmware_model as fm

# (시각 ms, 보낼 바이트, 설명) — 확인할 규칙 하나씩
SCRIPT = [
    (0, 'V0\nSF', '초기화: V 수신 상태로 만들고 정지·조향 정지'),
    (300, 'V100\nG', '전진 V100 + 주행 허용 → 상태 1'),
    (500, 'V100\n', 'keepalive'),
    (700, 'V100\n', 'keepalive (마지막 수신) → 500 ms 뒤 워치독으로 상태 0'),
    (1500, 'V-80\nG', '후진 V-80 → 상태 2'),
    (1700, 'S', '정지 S → 상태 0'),
    (2000, 'L', '조향 L 펄스 1회 (120 ms)'),
    (2600, 'R', '조향 R 펄스'),
    (2660, 'R', '펄스 중 R 다시 → 2660부터 120 ms로 연장 (총 180 ms)'),
    (3300, 'L', '조향 L'),
    (3340, 'F', '40 ms 만에 F → 조향 정지'),
]
END_MS = 4000
# 조향 변화량을 볼 구간: (이름, 시작 ms, 끝 ms, 기대 펄스 길이 ms, 부호)
STEER_CHECKS = [('L 1회', 1950, 2400, 120, +1), ('R 연장', 2550, 3200, 180, -1), ('L→F', 3250, 3800, 40, +1)]
STATE_CHECKS = [('G 후 상태', 300, 1), ('워치독', 700, 0), ('후진', 1500, 2), ('정지 S', 1700, 0)]


def run_tcp(host, port):
    s = socket.create_connection((host, port), timeout=3)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    lines, buf, stop = [], b'', threading.Event()
    t0 = [None]

    def reader():
        nonlocal buf
        s.settimeout(0.05)
        while not stop.is_set():
            try:
                d = s.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not d:
                break
            buf += d
            while b'\n' in buf:
                ln, buf = buf.split(b'\n', 1)
                if t0[0] is not None:
                    lines.append(((time.perf_counter() - t0[0]) * 1000, ln.decode().strip()))
    th = threading.Thread(target=reader, daemon=True)
    th.start()
    time.sleep(0.3)
    t0[0] = time.perf_counter()
    for t_ms, data, _ in SCRIPT:
        while (time.perf_counter() - t0[0]) * 1000 < t_ms:
            time.sleep(0.0005)
        s.sendall(data.encode())
    while (time.perf_counter() - t0[0]) * 1000 < END_MS:
        time.sleep(0.01)
    stop.set()
    th.join(1)
    s.close()
    return lines


def run_model():
    m = fm.FirmwareModel(fm.load_params(), seed=0)
    m.feed('V0\n')       # 트윈처럼 이미 V를 받은 적 있는 상태에서 출발
    m.step(300)
    m.pop_lines()
    out, i = [], 0
    for t in range(END_MS):
        while i < len(SCRIPT) and SCRIPT[i][0] <= t:
            m.feed(SCRIPT[i][1])
            i += 1
        m.step(1)
        out += [(float(t), ln) for _, ln in m.pop_lines()]
    return out


def analyse(lines, cal):
    states = [(t, int(l)) for t, l in lines if l in ('0', '1', '2')]
    pots = [(t, fm.adc_to_angle(cal, int(l[2:]))) for t, l in lines if l.startswith('P ')]
    changes, last = [], None
    for t, v in states:
        if v != last:
            changes.append((t, v))
            last = v

    def state_after(t_cmd, want):
        for t, v in changes:
            if t >= t_cmd - 5 and v == want:
                return t - t_cmd
        return None

    def angle_at(t_ms):
        cand = [a for t, a in pots if t <= t_ms]
        return cand[-1] if cand else None
    st = {name: state_after(t, want) for name, t, want in STATE_CHECKS}
    sd = {}
    for name, a, b, _, _ in STEER_CHECKS:
        x, y = angle_at(a), angle_at(b)
        sd[name] = None if x is None or y is None else y - x
    return st, sd, len(states), len(pots)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=55002)
    a = ap.parse_args()
    p = fm.load_params()
    cal = {k: p[k] for k in ('pot_left_adc', 'pot_right_adc', 'steer_limit_deg')}
    twin = analyse(run_tcp(a.host, a.port), cal)
    model = analyse(run_model(), cal)
    ok = True
    print(f'메시지 수  Unity: 상태 {twin[2]} · POT {twin[3]}   모델: 상태 {model[2]} · POT {model[3]}  ({END_MS} ms)')
    print('\n[상태] 명령 → 기대 상태가 나올 때까지 [ms]')
    for name, t, want in STATE_CHECKS:
        u, m = twin[0][name], model[0][name]
        good = u is not None and m is not None and abs(u - m) <= 40
        ok &= good
        print(f'  {name:8s} 기대 {want}:  Unity {u if u is None else round(u):>5}   모델 {m if m is None else round(m):>5}   {"OK" if good else "차이"}')
    print('\n[조향] 구간 변화량 [deg]  (기대 = 펄스 길이 / 120 ms × deg_per_pulse)')
    for name, _, _, dur, sign in STEER_CHECKS:
        exp = sign * dur / p['steer_pulse_ms'] * p['deg_per_pulse']
        u, m = twin[1][name], model[1][name]
        good = u is not None and abs(u - exp) <= 0.5 and m is not None and abs(m - exp) <= 0.5
        ok &= good
        fmt = lambda v: '  None' if v is None else f'{v:+6.2f}'
        print(f'  {name:8s} 기대 {exp:+6.2f}   Unity {fmt(u)}   모델 {fmt(m)}   {"OK" if good else "차이"}')
    print('\n결과:', '통과 — Unity 트윈이 펌웨어 규칙대로 동작' if ok else '차이 있음 — 위 항목 확인')


if __name__ == '__main__':
    main()
