#!/bin/bash
# WSL 안에서 ROS 2 전체 흐름 점검: 가짜 패널(55003)·가짜 트윈(55002) 서버 + testbed.launch + experiment_node.
# 결과: ~/kiis_logs/runs/e2e_<시각>/log.csv  (점검용 — 실험 데이터 아님)
set -e; set +e  # kill 실패로 중단되지 않게
source "$(ls -t /opt/ros/*/setup.bash | head -1)"
source "${KIIS_WS:-$HOME/kiis_ws}/install/setup.bash"
TW="$(cd "$(dirname "$0")" && pwd)"
RUN=e2e_$(date +%H%M%S)
cd $TW
python3 fake_twin_server.py --port 55002 > /tmp/fake_twin.log 2>&1 &
P1=$!
python3 fake_twin_server.py --port 55003 --params dryrun_panel_params.json > /tmp/fake_panel.log 2>&1 &
P2=$!
sleep 1
ros2 launch kiis_testbed testbed.launch.py panel_port:=socket://127.0.0.1:55003 twin_host:=127.0.0.1 \
    panel_adc_left:=825.0 panel_adc_right:=146.0 run_name:=$RUN note:="WSL e2e dry run (fake servers)" > /tmp/testbed.log 2>&1 &
L=$!
sleep 4
timeout 60 ros2 run kiis_testbed experiment_node --ros-args -p program:=steps -p pulses:=3 2>&1 | tail -3
sleep 1
kill -INT $L; sleep 2; kill $P1 $P2 2>/dev/null || true
echo "--- testbed log"; grep -E "연결|열기 실패|기록|ERROR|Traceback" /tmp/testbed.log | head
echo "--- servers"; cat /tmp/fake_twin.log /tmp/fake_panel.log | head
mkdir -p $TW/runs/$RUN && cp ~/kiis_logs/runs/$RUN/* $TW/runs/$RUN/
python3 - "$TW/runs/$RUN/meta.json" <<PY
import json,sys; p=sys.argv[1]; m=json.load(open(p)); m["dry_run"]=True; json.dump(m,open(p,"w"),ensure_ascii=False,indent=2)
PY
wc -l $TW/runs/$RUN/log.csv; awk -F, 'NR>1{print $2","$3}' $TW/runs/$RUN/log.csv | sort | uniq -c
echo $TW/runs/$RUN
