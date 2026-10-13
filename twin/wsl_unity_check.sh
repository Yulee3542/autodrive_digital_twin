#!/bin/bash
# Unity Play 검증: 패널 없이 실제 Unity 트윈(TwinFirmware.cs)만 붙여 staircase 명령을 보내고,
# 응답이 같은 파라미터의 파이썬 모델(firmware_model.py)과 일치하는지 본다. (점검용 — 논문 데이터 아님)
# 먼저 윈도우에서 Unity auto_car를 Play(좌상단 "waiting :55002"), 그다음 WSL에서:
#   bash twin/wsl_unity_check.sh [twin_host(기본 auto)] [program(기본 staircase, drive면 주행)]
source "$(ls -t /opt/ros/*/setup.bash | head -1)"
source "${KIIS_WS:-$HOME/kiis_ws}/install/setup.bash"
TW="$(cd "$(dirname "$0")" && pwd)"
HOST=${1:-auto}
PROG=${2:-staircase}
RUN=unity_check_${PROG}_$(date +%H%M%S)
ros2 launch kiis_testbed testbed.launch.py panel_port:=none twin_host:=$HOST run_name:=$RUN \
    note:="Unity Play check (twin only)" > /tmp/unity_check.log 2>&1 &
L=$!
sleep 4
timeout 60 ros2 run kiis_testbed experiment_node --ros-args -p program:=$PROG -p pulses:=2 2>&1 | tail -2
sleep 1
kill -INT $L; sleep 2
echo "--- twin_bridge log"; grep -E "twin_bridge|socket|연결|열기 실패|ERROR|Traceback" /tmp/unity_check.log | head
mkdir -p $TW/runs/$RUN && cp ~/kiis_logs/runs/$RUN/* $TW/runs/$RUN/
cd $TW && python3 - "$RUN" <<'PY'
import json, sys
import numpy as np
import analyze as an, firmware_model as fm
run = 'runs/' + sys.argv[1]
m = json.load(open(run + '/meta.json')); m['dry_run'] = True
json.dump(m, open(run + '/meta.json', 'w'), ensure_ascii=False, indent=2)
rows = an.read_log(run); ev = an.cmd_events(rows)
t, a = an.pot_series(rows, 'twin', an.load_cal()['twin'])
if not len(t):
    sys.exit('트윈 응답 없음 → Unity Play 상태·방화벽(Public 프로필 Unity.exe 차단 규칙)·twin_host 확인')
p = fm.load_params()
ts, am = an.sim_series(ev, rows[-1][0] + 0.1, p, an.level_before(t, a, an.first_pulse_t(ev)))
r, mx = an.rmse_on(t, a, ts, am)
print(f'트윈 응답 {len(t)}개, 각도 범위 {a.min():+.1f}~{a.max():+.1f} deg, 발행 주기 {np.median(np.diff(t))*1000:.0f} ms')
print(f'Unity 트윈 vs 파이썬 모델(deg_per_pulse={p["deg_per_pulse"]}, lag={p["steer_lag_ms"]}): RMSE {r:.2f} deg, 최대 {mx:.2f} deg')
print('→ 일치' if r < 0.5 else '→ 불일치: TwinFirmware.cs와 firmware_model.py 규칙 차이 또는 지연 확인')
# 주행 상태(0 정지 / 1 전진 / 2 후진) 변화 시각: Unity vs 모델(브리지 램프·keepalive 포함)
import bridge_sim
def changes(rr, src):
    out, last = [], None
    for tt, s_, k, v in rr:
        if s_ == src and k == 'state' and int(float(v)) != last:
            last = int(float(v)); out.append((round(tt, 2), last))
    return out
cu = changes(rows, 'twin')
cm = changes(bridge_sim.run(ev, rows[-1][0] + 0.1, p, 'twin', offset=0.0), 'twin')
print('상태 변화 Unity:', cu)
print('상태 변화 모델:', cm)
# 주행 V는 arduino_node의 200 ms keepalive 때만 나가므로(위상은 실행마다 다름) 시각은 keepalive 1주기 + 발행 33 ms 안이면 같다고 본다.
# 첫 항목은 기록 시작 시점이라 제외. (조향 펄스는 즉시 전달 — 이 차이와 무관)
same = [x[1] for x in cu] == [x[1] for x in cm] and all(abs(x[0] - y[0]) < 0.25 for x, y in list(zip(cu, cm))[1:])
print('→ 상태 순서 일치, 시각 차이는 keepalive 위상(≤0.25 s) 안' if same else '→ 상태 변화 차이 있음')
PY
echo $TW/runs/$RUN
