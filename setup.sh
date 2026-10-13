#!/usr/bin/env bash
# autodrive_digital_twin — ROS 2 쪽(WSL2 또는 Ubuntu) 최초 1회 설정.
# 저장소는 어디에 클론해도 된다(WSL이면 윈도우 쪽 D:\... 클론을 /mnt/d/...로 그대로 써도 됨 — Unity가 같은 폴더를 쓴다).
# 빌드 결과는 작업공간 ~/kiis_ws(환경 변수 KIIS_WS로 변경)에 --symlink-install로 — 소스를 고치면 재빌드 없이 반영.
# 이미 설정된 환경을 최신 코드로 갱신할 때는 update.sh.
#   ./setup.sh               의존성 설치 + 빌드 + 권한 (sudo 필요)
#   ./setup.sh --build-only  빌드만 (launcher/wsl_testbed.sh가 처음 실행 때 부름)
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
WS="${KIIS_WS:-$HOME/kiis_ws}"
BUILD_ONLY=0; [ "$1" = "--build-only" ] && BUILD_ONLY=1
chmod +x "$ROOT"/setup.sh "$ROOT"/update.sh "$ROOT"/launcher/*.sh "$ROOT"/twin/*.sh 2>/dev/null || true

if [ -n "$VIRTUAL_ENV" ]; then
    echo "Python 가상환경($VIRTUAL_ENV)이 켜져 있습니다 — colcon이 그 python3를 써서 빌드가 깨질 수 있으니 'deactivate' 후 다시."
    exit 1
fi
if [ -z "$ROS_DISTRO" ]; then
    ROS_SETUP=$(ls -t /opt/ros/*/setup.bash 2>/dev/null | head -1)
    if [ -z "$ROS_SETUP" ]; then
        echo "ROS 2가 없습니다. 먼저 설치하세요 (Ubuntu 24.04 + Jazzy 권장, 22.04 + Humble도 됨):"
        echo "  https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html"
        exit 1
    fi
    set +u; source "$ROS_SETUP"
fi
echo "== ROS 2: $ROS_DISTRO · 저장소: $ROOT · 작업공간: $WS =="

if [ $BUILD_ONLY -eq 0 ]; then
    echo "== apt: rosdep · colcon =="
    sudo apt-get update
    sudo apt-get install -y python3-rosdep python3-colcon-common-extensions
    [ -d /etc/ros/rosdep ] || sudo rosdep init
    rosdep update
    echo "== rosdep: 패키지 의존성 (pyserial · numpy · opencv · matplotlib · tk) =="
    rosdep install --from-paths "$ROOT/ros2_ws/src" --ignore-src -r -y
    echo "== 시리얼 권한 (dialout) =="
    if id -nG "$USER" | grep -qw dialout; then echo "   이미 dialout 그룹"; else
        sudo usermod -aG dialout "$USER"; echo "   dialout 그룹에 추가 — 로그아웃/재로그인(WSL은 wsl --shutdown) 후 적용"; fi
fi

echo "== colcon build (--symlink-install) =="
mkdir -p "$WS"
cd "$WS"
colcon --log-base "$WS/log" build --symlink-install --base-paths "$ROOT/ros2_ws/src" \
    --build-base "$WS/build" --install-base "$WS/install" --packages-select kiis_testbed
cd - >/dev/null

[ $BUILD_ONLY -eq 1 ] && exit 0

if grep -qi microsoft /proc/version 2>/dev/null; then
    cat <<'MSG'

[WSL2 감지] 윈도우 쪽에서 한 번만:
  1) Unity Hub에서 unity/auto_car 를 ProjectVersion.txt의 에디터 버전으로 연다(처음 임포트 몇 분).
  2) 컨트롤 패널(아두이노)을 쓸 거면: winget install usbipd  (보드 공유 등록은 launcher가 처음 꽂을 때 UAC로 함)
  3) WSL → Unity(TCP 55002)가 방화벽에 막히면 관리자 PowerShell에서 (README '문제 해결' 참고):
       New-NetFirewallRule -DisplayName 'KIIS twin 55002 from WSL' -Direction Inbound -Action Allow -Profile Any `
         -Program '<Unity.exe 경로>' -Protocol TCP -LocalPort 55002 -InterfaceAlias 'vEthernet (WSL (Hyper-V firewall))'
  이후 실행은 윈도우에서 launcher\start_testbed.bat 더블클릭.
MSG
else
    cat <<MSG

[Ubuntu] Unity 트윈은 윈도우 PC에서 돌리고, 여기서는 twin_host:=<윈도우 IP>로 붙는다:
  source $WS/install/setup.bash
  ros2 launch kiis_testbed testbed.launch.py panel_port:=auto twin_host:=<윈도우IP> monitor:=web
  모니터: 브라우저에서 http://127.0.0.1:8765
MSG
fi
echo
echo "설정 완료."
