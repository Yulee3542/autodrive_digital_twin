# launcher — 테스트베드 원클릭 실행 (컨트롤 패널 플러그 앤 플레이)

**`start_testbed.bat` 더블클릭** 한 번으로:

1. **시뮬레이션** — Unity `unity/auto_car`를 열고 자동으로 Play (`Assets/Editor/KiisAutoPlay.cs`).
   이미 열려 있으면 Play 요청만, 이미 Play 중이면 그대로 둔다. Hub 로그인 상태여야 한다.
2. **ROS 2 테스트베드** (WSL, Windows Terminal 탭 "KIIS testbed") — 패널 브리지(`panel_port:=auto`) + 트윈 브리지 + 웹 모니터 서버
   → 준비되면 **모니터 창**(Chrome/Edge 앱 창, 주소창 없음, `http://127.0.0.1:8765`)이 맨 앞에 뜬다
3. **키보드 조종** (탭 "KIIS teleop") — `g` 주행 허용 → `w/x` 속도 · `a/d` 조향 펄스 · `s` 정지. 명령은 패널과 트윈에 동시에 간다.
4. **USB 감시** (실행한 창) — 아두이노가 꽂히면 `usbipd attach`로 WSL에 붙인다. 처음 보는 보드는 관리자 승인 창이 한 번 뜬다(`usbipd bind`).

## 모니터 창 (`web_monitor_node`, 브라우저 앱 창)

WSLg 창(`monitor_node`, `monitor:=gui`)은 최소화·뒤쪽에 뜨거나 아예 안 그려지는 일이 있어(10-12) 기본을 브라우저로 바꿨다.
창을 닫았으면 `http://127.0.0.1:8765`를 브라우저로 열거나 `start_testbed.bat`을 다시 실행(이미 떠 있으면 새로 띄우지 않고 창만 앞으로).

| 위치 | 내용 |
|---|---|
| 왼쪽 카드 | **컨트롤 패널(보드)** — 연결 상태(연결됨 / 대기 중 / 브리지 꺼짐), 주행 상태, 조향각, POT ADC |
| 오른쪽 카드 | **디지털 트윈(시뮬레이션)** — 같은 항목 |
| 가운데 | 조향각 차이(보드 − 시뮬레이션): 1° 미만 초록 · 3° 미만 주황 · 그 이상 빨강 |
| 아래 | 최근 30 s 조향각 그래프(두 장치) + 명령 시점 세로선 · 최근 명령 기록 |

패널 각도는 `twin/calibration.json`의 panel이 `"measured": true`일 때만 표시된다(아니면 ADC만, "보정 필요").

## 플러그 앤 플레이 동작

- 두 브리지(`arduino_node`, `reconnect:=true`)는 포트가 없으면 1초마다 다시 찾고, 뽑히거나 끊기면 정리하고 다시 기다린다.
  → 보드를 **실행 후에 꽂아도, 중간에 뽑았다 다시 꽂아도** 자동으로 붙는다. Unity Play를 다시 눌러도 마찬가지.
- 안전: 다시 붙은 보드에는 **G(주행 허용)를 자동으로 보내지 않는다** — 다음 `g`(go) 명령 전까지 정지 상태.
- 보드 판별: USB VID 2341·2a03(Arduino), 1a86(CH340), 0403(FTDI) 또는 이름에 Arduino/CH340. CP210x(라이다)는 제외.
- 펌웨어를 올릴 때(Arduino IDE): 실행 창을 닫고 `usbipd detach --busid <ID>`로 보드를 윈도우에 돌려준 뒤 업로드.

## 중복 실행 방지

- `start_testbed.bat`을 두 번 눌러도 WSL 테스트베드가 이미 떠 있으면 새로 띄우지 않는다 — 두 벌이 뜨면 두 번째 트윈 브리지가
  Unity에 못 붙은 채 상태 −1을 같은 토픽에 섞어 보낸다(10-12 실제로 겪음).
- 끝낼 때: "KIIS testbed" 탭에서 Ctrl+C (탭은 자동으로 닫힘), 실행 창은 그냥 닫기.

## 옵션

```
.\start_testbed.ps1 -Record      # ~/kiis_logs/runs/<시각>/log.csv 기록 (실험 run은 twin/README의 절차대로 run_name을 줄 것)
.\start_testbed.ps1 -NoTeleop    # 조종 탭 없이 (experiment_node로 명령할 때)
.\start_testbed.ps1 -NoUnity     # Unity는 손대지 않음
```

## 파일

| 파일 | 역할 |
|---|---|
| `start_testbed.bat` / `start_testbed.ps1` | 윈도우 진입점 (ps1은 UTF-8 BOM 필수 — 한글 메시지) |
| `wsl_testbed.sh` | WSL: 처음이면 `setup.sh --build-only` → `testbed.launch.py panel_port:=auto monitor:=web` |
| `wsl_teleop.sh` | WSL: `teleop_node` |

## 점검 기록 (2026-10-12)

- 플러그 앤 플레이: 가짜 패널 서버로 시작 시 없음 → 꽂음 → 명령 → 뽑음 → 다시 꽂음 전 과정 자동 재연결 확인 (트윈은 실제 Unity)
- 원클릭: Unity Play 중 상태에서 실행 → WSL에 panel_bridge·twin_bridge·web_monitor·teleop_node 기동, 트윈 연결 True / 패널 대기 False,
  모니터 앱 창이 맨 앞에 뜨는 것을 화면 캡처로 확인
- 겪은 문제: WSLg 창 안 보임 → 브라우저로 전환 · `localhost`는 IPv6 먼저라 1초 제한에 걸림 → 127.0.0.1 ·
  bat의 `pwsh || powershell`이 강제 종료 때 두 번째 실행 → if/else로 · 백그라운드 창은 포커스를 못 가져감 → 잠깐 항상 위 토글
- 방화벽: WSL→Unity 55002가 막히면 `ros2_ws/src/kiis_testbed/README.md` 점검 기록의 허용 규칙 참고
