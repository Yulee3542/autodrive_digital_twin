#!/bin/bash
# WSL: 키보드 조종(teleop). 명령은 /car/cmd/*로 나가 패널과 트윈에 동시에 간다.
source "$(ls -t /opt/ros/*/setup.bash | head -1)"
source "${KIIS_WS:-$HOME/kiis_ws}/install/setup.bash"
ros2 run kiis_testbed teleop_node
exit 0   # Windows Terminal 탭이 남지 않게
