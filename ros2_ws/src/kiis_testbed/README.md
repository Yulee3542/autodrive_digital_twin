# kiis_testbed — 컨트롤 패널 · Unity 디지털 트윈 ROS 2 테스트베드

KIIS 2026 추계 「자율주행 테스트베드를 위한 디지털 트윈 및 컨트롤 패널 설계」용.
`autodrive_skku`(GitHub `Yulee3542/autodrive_skku` main `a300036`, 2026-10-12)에서 **teleop과 커넥터만** 추렸다.
미션·비전·라이다·오도메트리는 가져오지 않았다.

```
 teleop_node (키보드)  ┐                      ┌─ panel_bridge (arduino_node) ── 시리얼 ── 컨트롤 패널 (car_controller.ino)
 experiment_node (스크립트) ┴─ /car/cmd/* ──┤        → /car/state, /car/steering_pot, /car/steering_angle
                                              └─ twin_bridge  (arduino_node) ── socket:// ── Unity 트윈 (TwinFirmware.cs)
                                                       → /twin/car/state, /twin/car/steering_pot, /twin/car/steering_angle
 recorder_node: /car/cmd/* + 두 장치 응답 → ~/kiis_logs/runs/<이름>/log.csv
```

## autodrive_skku에서 바뀐 것

| 파일 | 변경 |
|---|---|
| `nodes/arduino_node.py` | `serial_for_url`(→ `socket://` 지원) · `cmd_prefix`/`state_prefix` 파라미터 · 칼만 Q/R을 일반 파라미터로(tuning 모듈 제거) |
| `nodes/teleop_node.py` | 그대로(카메라 커넥터 `/camera/front·back`은 발행하는 노드가 있을 때만 녹화) |
| `nodes/ports.py`, `filters.py`, `drive_logger.py` | 그대로 (모듈 경로만) |
| `config.py` | 쓰는 값만 남김 |
| `nodes/experiment_node.py`, `nodes/recorder_node.py`, `programs.py`, `launch/testbed.launch.py` | 신규 |
| `nodes/monitor_node.py` | 신규 (10-12) — 보드 vs 시뮬레이션 실시간 창 |
| `nodes/arduino_node.py` 추가 변경 (10-12) | `reconnect` 파라미터(플러그 앤 플레이: 포트 재탐색·끊김 감지·재연결), `<prefix>/connected` 발행 |

셀프테스트(ROS 불필요): `python3 -m kiis_testbed.nodes.arduino_node --selftest` (filters·drive_logger·teleop_node·ports도 같음)

## 빌드

저장소 루트의 `setup.sh`(최초 1회)·`update.sh`(갱신)가 한다 — 소스는 저장소에 둔 채 작업공간 `~/kiis_ws`(`KIIS_WS`로 변경 가능)에
`--symlink-install`로 빌드. 수동으로는:

```
source /opt/ros/$ROS_DISTRO/setup.bash
colcon --log-base ~/kiis_ws/log build --symlink-install --base-paths <저장소>/ros2_ws/src \
  --build-base ~/kiis_ws/build --install-base ~/kiis_ws/install
source ~/kiis_ws/install/setup.bash
```

## 실행

1. Unity `unity/auto_car` → Play (좌상단 `waiting :55002`). 처음엔 윈도우 방화벽 허용 창이 뜬다.
2. `ros2 launch kiis_testbed testbed.launch.py panel_port:=/dev/ttyACM0 panel_adc_left:=<좌> panel_adc_right:=<우>`
   - WSL2 NAT면 `twin_host:=auto`(기본 게이트웨이 = 윈도우), mirrored 네트워킹이면 `twin_host:=127.0.0.1`
   - 두 브리지는 재연결 모드(2026-10-12~) — 패널을 나중에 꽂거나 Unity Play를 나중에 눌러도 자동으로 붙는다 (원클릭 실행: `launcher/`)
   - `monitor:=true`면 보드 vs 시뮬레이션 실시간 모니터 창(`monitor_node`)도 뜬다
3. 명령: `ros2 run kiis_testbed experiment_node --ros-args -p program:=steps -p pulses:=3`
   또는 수동 `ros2 run kiis_testbed teleop_node` (g 주행 허용 · w/x 속도 · a/d 조향 펄스 · s 정지)
4. 분석(윈도우): `twin/analyze.py <run> --fit` — `~/kiis_logs/runs/<이름>`을 `twin/runs/`로 복사해서

## 점검 기록 (2026-10-12)

- WSL Jazzy 빌드 OK, 실행 파일 4개 등록
- `twin/wsl_e2e_test.sh`: 가짜 패널(55003, 7.5°/펄스·60 ms·백래시 1.5°)과 가짜 트윈(55002) 서버에 두 브리지를 `socket://`로 붙여
  experiment_node → recorder 전 과정 통과. 피팅 결과 7.5°/펄스·백래시 1.5°·지연 80 ms(=60 ms + ROS/TCP 경로 약 20 ms), RMSE 1.55° → 0.14°
- ~~Unity 트윈은 컴파일만 확인~~ → **2026-10-12 19:58 Unity Play 검증 통과** (`twin/wsl_unity_check.sh`, twin_host:=auto = 172.27.32.1):
  트윈 응답 483개·33 ms 주기, staircase 2펄스 ±12.0°, 시작/끝 0.03°, Unity 트윈 vs 파이썬 모델 RMSE 0.23°(lag 10 ms 넣으면 0.19°)
  → ROS 2·브리지·TCP 왕복 경로 지연 ≈ 10 ms. (`runs/unity_check_195813`, 점검용 dry_run)
  - 막혔던 것: 방화벽에 Unity.exe **Public(나중엔 Private도) 인바운드 차단 규칙**, Wi-Fi = Public → WSL에서 TCP 시간 초과.
    사용자가 관리자 PowerShell로 차단 규칙 비활성 + `KIIS twin 55002 from WSL` 허용 규칙(Unity.exe, TCP 55002, vEthernet (WSL) 어댑터만) 추가.
    되돌리기: `Remove-NetFirewallRule -DisplayName 'KIIS twin 55002 from WSL'` + 차단 규칙 Enable
  - Unity에서 열린 씬이 SampleScene이 아니면 `car`가 없어 트윈이 안 붙는다(`[TwinBootstrap] 'car' 오브젝트가 없어…`) → `Assets/Scenes/SampleScene`을 열고 Play
