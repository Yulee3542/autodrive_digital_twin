# autodrive_digital_twin

소형 자율주행 차량([autodrive_skku](https://github.com/Yulee3542/autodrive_skku))의 **디지털 트윈 테스트베드**.
같은 ROS 2 구동 명령을 **컨트롤 패널**(차량과 같은 모터·드라이버·아두이노·펌웨어를 판 위에 올린 실제 구동계)과
**Unity 디지털 트윈**(같은 펌웨어 규칙을 1 ms 루프로 흉내 내는 가상 차량)에 동시에 보내고, 두 응답을 실시간으로 비교·기록·조정한다.

```
 teleop_node (키보드) ─┐                    ┌─ panel_bridge ── 시리얼(usbipd) ── 컨트롤 패널 (car_controller.ino)
 experiment_node ──────┴─ /car/cmd/* ──────┤                                    → /car/state · /car/steering_pot · /car/connected
                                            └─ twin_bridge ─── TCP 55002 ─────── Unity 트윈 (TwinFirmware.cs)
                                                                                 → /twin/car/state · /twin/car/steering_pot · …
 web_monitor_node: 보드 vs 시뮬레이션 실시간 화면 (http://127.0.0.1:8765)   recorder_node: log.csv   twin/analyze.py: 비교·파라미터 맞추기
```

- **플러그 앤 플레이**: 두 브리지는 끊기면 1초마다 다시 붙는다 — 패널을 나중에 꽂거나 뽑아도, Unity Play를 나중에 눌러도 된다.
  재연결된 보드에는 주행 허용(G)을 자동으로 보내지 않는다(안전).
- **차량 모델**: 이 저장소에는 차량 3D 모델이 들어 있지 않다. 씬에 `car`가 없으면 트윈이 실차 치수(휠베이스 0.545 m, 윤거 0.43 m,
  바퀴 반지름 0.1 m)의 **상자 차량과 바닥 평면**을 만들어 쓴다. 자기 모델이 있으면 씬에 `car`라는 이름으로 두면 그걸 쓴다.
- 펌웨어 규약은 autodrive_skku의 `arduino/car_controller/car_controller.ino`(9600 bps, 120 ms 조향 펄스, P 50 ms, 상태 0/1/2, 워치독 500 ms).

## 사용 설명서

### 준비물

| | 윈도우 + WSL2 (권장) | Ubuntu 단독 |
|---|---|---|
| ROS 2 | WSL2 Ubuntu 24.04 + Jazzy (22.04 + Humble도 됨) | 같음 |
| Unity | Unity Hub + 에디터 `unity/auto_car/ProjectSettings/ProjectVersion.txt`의 버전 | 트윈은 다른 윈도우 PC에서 (`twin_host:=<IP>`) |
| 패널 연결 | [usbipd-win](https://github.com/dorssel/usbipd-win) (`winget install usbipd`) | USB 직결 |

### 1단계. 클론 + 설정 (최초 1회)

윈도우에서 클론하고(Unity가 이 폴더를 연다) WSL에서 같은 폴더로 설정한다.

```
git clone https://github.com/Yulee3542/autodrive_digital_twin.git D:\autodrive_digital_twin
```
```
# WSL 안에서
cd /mnt/d/autodrive_digital_twin && ./setup.sh
```

`setup.sh`: rosdep 의존성(pyserial·numpy·opencv·matplotlib·tk) → `~/kiis_ws`에 `--symlink-install` 빌드 → dialout 권한.
작업공간 위치는 `KIIS_WS` 환경 변수로 바꿀 수 있다. Ubuntu 단독이면 아무 데나 클론하고 `./setup.sh`.

Unity Hub에서 `unity/auto_car`를 한 번 열어 둔다(처음 임포트 몇 분).

### 2단계. 실행 — `launcher\start_testbed.bat` 더블클릭

1. Unity 에디터를 열고 자동으로 Play (이미 Play 중이면 그대로)
2. Windows Terminal 탭: **KIIS testbed**(브리지·기록·웹 모니터) · **KIIS teleop**(키보드 조종)
3. **모니터 창**(주소창 없는 브라우저 앱 창)이 맨 앞에 뜬다 — 왼쪽 보드, 오른쪽 시뮬레이션, 조향각 차이, 30초 그래프, 명령 기록
4. 실행한 창은 USB를 감시하다가 아두이노가 꽂히면 WSL에 붙인다(처음 보는 보드는 관리자 승인 한 번)

조종(teleop 탭): `g` 주행 허용 → `w`/`x` 속도 · `a`/`d` 조향 펄스 · `s` 정지. Unity 화면에서 `C` = 트윈 조향 중앙.
옵션은 `launcher/README.md` (`-Record`, `-NoTeleop`, `-NoUnity`).

Ubuntu 단독:
```
source ~/kiis_ws/install/setup.bash
ros2 launch kiis_testbed testbed.launch.py panel_port:=auto twin_host:=<Unity PC IP> monitor:=web
ros2 run kiis_testbed teleop_node        # 다른 터미널
```

### 3단계. 컨트롤 패널 (선택)

1. 아두이노 메가에 autodrive_skku의 `car_controller.ino` 업로드(업로드할 땐 `usbipd detach --busid <ID>`로 윈도우에 돌려줄 것)
2. 조향 기어박스 가변저항(A6)의 좌·우 한계 ADC를 재서 `twin/calibration.json`의 `panel`에 넣고 `"measured": true`
   → launcher가 이 값을 넘겨 모니터에 패널 조향각이 나온다(미측정이면 ADC만)
3. 그냥 꽂으면 된다 — 모니터 왼쪽 카드가 "연결됨"으로 바뀐다

### 4단계. 실험 (트윈 vs 패널 비교·조정)

`twin/README.md`의 "실험 순서" — 요약:

```
ros2 run kiis_testbed experiment_node --ros-args -p program:=steps -p pulses:=<n>      # 조정용
ros2 run kiis_testbed experiment_node --ros-args -p program:=staircase -p pulses:=<n>  # 검증용
python twin/analyze.py twin/runs/<run> --fit           # 트윈 파라미터(펄스당 각도·지연·백래시) 맞추기
python twin/table2.py --cal-before … --val-before … --cal-after … --val-after …   # 조정 전/후 표·그림
```

점검(하드웨어 없이): `python twin/sim_only_test.py`(Unity 트윈 펌웨어 규칙 적합성) · `bash twin/wsl_unity_check.sh`(ROS 2 경로) ·
`python twin/dryrun.py`(가짜 패널로 분석 파이프라인).

### 5단계. 코드 갱신 (2회차 이후)

```
cd <저장소> && ./update.sh      # git pull --ff-only + 재빌드
```

## 문제 해결

| 증상 | 원인 · 해결 |
|---|---|
| 모니터 오른쪽(시뮬레이션)이 계속 "대기 중", WSL에서 55002 연결이 시간 초과 | 윈도우 방화벽이 Unity.exe 인바운드를 막음(Wi-Fi가 공용 프로필일 때 흔함). 관리자 PowerShell:<br>`New-NetFirewallRule -DisplayName 'KIIS twin 55002 from WSL' -Direction Inbound -Action Allow -Profile Any -Program '<Unity.exe 경로>' -Protocol TCP -LocalPort 55002 -InterfaceAlias 'vEthernet (WSL (Hyper-V firewall))'`<br>Unity.exe에 Public "차단" 규칙이 있으면 그것도 꺼야 한다(차단이 허용보다 우선): `Get-NetFirewallRule \| ? { $_.DisplayName -like 'Unity*Editor*' -and $_.Action -eq 'Block' } \| Disable-NetFirewallRule` |
| 시뮬레이션 주행 상태가 깜빡임(−1) | 테스트베드가 두 번 떠 있음 — 테스트베드 탭 Ctrl+C 후 다시 실행(launcher는 중복 실행을 막는다) |
| 모니터 창이 안 보임 | `http://127.0.0.1:8765`를 브라우저로 직접 연다. `localhost`보다 `127.0.0.1`(IPv6 우회) |
| 보드를 꽂았는데 왼쪽이 "대기 중" | 실행 창 로그 확인 — `usbipd list`에서 보드가 Not shared면 관리자 승인 필요, Attached인데 안 붙으면 WSL에서 `ls /dev/ttyACM*` |
| Unity에서 트윈이 상자 차량으로 나옴 | 정상(이 저장소엔 차량 모델 없음). 모델을 쓰려면 씬에 `car` 오브젝트(앞바퀴 Transform은 `FrontLeftWheel`/`FrontRightWheel` 자식)로 두기 |

## 저장소 구조

| 경로 | 내용 |
|---|---|
| `setup.sh` · `update.sh` | ROS 2 쪽 설정·갱신 |
| `launcher/` | 원클릭 실행(`start_testbed.bat`/`.ps1`), WSL 실행 스크립트 |
| `ros2_ws/src/kiis_testbed/` | ROS 2 패키지 — 브리지(`arduino_node`, 재연결), teleop, 실험 명령, 기록, 모니터(웹·WSLg) |
| `unity/auto_car/` | Unity 프로젝트 — `TwinFirmware.cs`(펌웨어 모델·TCP 55002), `TwinBootstrap.cs`, `TwinPlaceholder.cs`(상자 차량), `Editor/KiisAutoPlay.cs` |
| `twin/` | 파이썬 펌웨어 모델·분석·피팅·점검 도구, `calibration.json`, `twin_params.json`(트윈 파라미터 덮어쓰기) |

이 저장소는 개인 연구 노트 저장소에서 공개용으로 내보낸 것이다(차량 모델·논문 원고 제외). 출처: KIIS 2026 추계 「자율주행 테스트베드를 위한 디지털 트윈 및 컨트롤 패널 설계」.
