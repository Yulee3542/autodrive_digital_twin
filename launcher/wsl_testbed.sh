#!/bin/bash
# WSL: 테스트베드(패널 브리지 + 트윈 브리지 + 모니터 창 [+ 기록]) 실행. start_testbed.ps1이 Windows Terminal 탭으로 부른다.
# 두 브리지는 재연결 모드 — 패널(보드)을 나중에 꽂거나 뽑아도, Unity Play가 늦어도 자동으로 붙는다.
#   bash wsl_testbed.sh [record(true|false)] [추가 launch 인자...]
ROOT="$(cd "$(dirname "$0")/.." && pwd)"          # 저장소 루트 (어디에 클론해도 됨)
WS="${KIIS_WS:-$HOME/kiis_ws}"
source "$(ls -t /opt/ros/*/setup.bash | head -1)"
if [ ! -x "$WS/install/kiis_testbed/lib/kiis_testbed/web_monitor_node" ]; then
  echo "[testbed] 처음 실행 — 빌드부터 (setup.sh --build-only)"
  bash "$ROOT/setup.sh" --build-only || exit 1
fi
source "$WS/install/setup.bash"
REC=${1:-false}; shift
echo "[testbed] 패널 포트 auto(꽂으면 연결) · 트윈 $(ip route show default | awk '{print $3}'):55002 · 기록 $REC"
echo "[testbed] 모니터: 윈도우 브라우저 http://127.0.0.1:8765 · 끝내려면 Ctrl+C"
ros2 launch kiis_testbed testbed.launch.py panel_port:=auto twin_host:=auto monitor:=web record:=$REC "$@"
exit 0   # Ctrl+C로 끝나도 0 → Windows Terminal 탭이 남지 않고 닫힘
