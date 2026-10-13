# twin — 디지털 트윈 vs 컨트롤 패널 실험

KIIS 2026 추계 「자율주행 테스트베드를 위한 디지털 트윈 및 컨트롤 패널 설계」 실험 코드.
**같은 구동 명령**을 컨트롤 패널(시리얼)과 Unity 디지털 트윈(TCP)에 동시에 보내고 조향각 응답을 비교한다.

## 구성 (2026-10-12 개편: 베이스 = autodrive_skku ROS 2, car_controller.ino 규약)

명령 송신·기록은 ROS 2 패키지 `../ros2_ws/src/kiis_testbed`가 맡는다(그쪽 README). 이 폴더는 트윈 모델·분석·점검 도구다.

| 파일 | 역할 |
|---|---|
| `../unity/auto_car/Assets/scripts/TwinFirmware.cs` | Unity 트윈 — car_controller.ino(9600 bps 규약, 120 ms 펄스, P 50 ms, 상태 0/1/2)를 TCP `0.0.0.0:55002`로 흉내 |
| `firmware_model.py` | 같은 규칙의 파이썬 모델 (둘을 함께 고칠 것) |
| `bridge_sim.py` | arduino_node 브리지 동작(G 중복 제거·200 ms keepalive·0.5 s 램프·30 Hz 발행)까지 포함한 오프라인 시뮬레이터 |
| `analyze.py` | `log.csv` → 비교 그래프·RMSE·응답 시간·시작/잔류 각도, `--fit`으로 트윈 파라미터(펄스당 각도·지연·백래시) 탐색, `--params`로 다른 run에서 맞춘 값 고정 적용 |
| `table2.py` | 조정 전/후 × steps/staircase 네 run → 표 2·그림 3 (`paper/`). DRY RUN·실측 아닌 calibration은 거부 |
| `calibration.json` | 장치별 POT 좌/우 한계 ADC — **panel은 아직 실차 값(임시)** |
| `twin_params.json` (선택) | 트윈 파라미터 덮어쓰기 — Unity와 파이썬 모델이 같이 읽는다. 피팅 결과(`twin_params_fitted.json`)를 여기에 복사 |
| `sim_only_test.py` · `wsl_unity_check.sh [host] [program]` | 시뮬레이션 단독 점검 — 같은 바이트 시각표를 Unity 트윈과 파이썬 모델에 보내 상태·워치독·펄스 규칙 비교 / ROS 2 경로로 트윈만 붙여 steps·staircase·drive 비교 |
| `dryrun.py`(`--twin-params`, `--tag`) · `fake_twin_server.py` · `wsl_e2e_test.sh` · `dryrun_panel_params.json` | 하드웨어 없는 점검용 (결과는 실험 데이터 아님, 그래프에 DRY RUN) |

기본 파라미터: 120 ms 펄스 6.0°(07-28 실측 6.1~12.2°의 하한, 기어 교체 전 값이라 패널 실측으로 피팅), 한계 ±20°, POT 좌 825/우 146, PWM–속도 곡선(aloha.toml 07-27), 휠베이스 0.54 m.

## 실험 순서 (2026-10-12 개정: 조정 = steps, 검증 = staircase)

0. **패널 준비**: 아두이노에 `autodrive_skku/arduino/car_controller/car_controller.ino` 업로드, 조향 기어박스 가변저항 A6.
   좌 한계·우 한계에서 `/car/steering_pot` 값을 읽어 `calibration.json` panel에 넣고 **`"measured": true`**로 바꾼다
   (안 바꾸면 table2.py가 거부). 같은 값을 launch 인자 `panel_adc_left/right`에도.
1. **펄스 수 정하기**: teleop으로 중앙에서 L 펄스를 하나씩 보내 펄스당 각도 d를 대충 본다.
   `pulses` = n·d ≤ 15°가 되는 최대 n (한계 ±20°에 붙으면 두 장치가 정의상 같아져 오차가 작게 나온다 — table2가 경고).
2. **매 run 전에 중앙 맞추기**: 패널은 손 또는 펄스로 |θ| < 1°(`/car/steering_angle`), 트윈은 Unity 화면에서 **C 키**.
   analyze가 시작 각도를 기록하고 1° 넘으면 경고한다. 모델 시뮬은 패널의 시작 각도에서 출발한다.
3. **run 1개 = launch 1번** (recorder는 launch 단위로 log 하나):
   `ros2 launch kiis_testbed testbed.launch.py panel_port:=/dev/ttyACM0 panel_adc_left:=<좌> panel_adc_right:=<우> run_name:=<이름>`
   → 다른 터미널에서 `ros2 run kiis_testbed experiment_node --ros-args -p program:=<steps|staircase> -p pulses:=<n>` → 끝나면 Ctrl-C.
   Unity는 Play를 유지해도 된다(트윈은 재접속을 받고 각도를 유지 → C 키로 중앙).
4. **조정 전** (twin_params.json 없음 = 기본값): `cal_before`(steps) · `val_before`(staircase)
5. `~/kiis_logs/runs/*`를 `twin/runs/`로 복사 →
   `python analyze.py runs/cal_before --fit` → `runs/cal_before/twin_params_fitted.json`
   `python analyze.py runs/val_before --params runs/cal_before/twin_params_fitted.json` (모델로 미리 본 검증)
6. `twin_params_fitted.json` → `twin_params.json` 복사 → **Unity Play 다시**(시작 시 읽음, 화면 하단에 pulse/lag 표시로 확인)
7. **조정 후**: `cal_after`(steps) · `val_after`(staircase) — 같은 pulses
8. `python table2.py --cal-before runs/cal_before --val-before runs/val_before --cal-after runs/cal_after --val-after runs/val_after`
   → `twin/paper/`: table2.md·csv(표 2), fig3_steering.pdf(그림 3), summary.json(패널 반복성, Unity 트윈 vs 파이썬 모델 일치도, 경고)

## 점검 (하드웨어·ROS 없이)

```
python dryrun.py --program steps --pulses 3
python analyze.py runs/<폴더> --fit
```
2026-10-12: 가짜 패널(7.5°/펄스·60 ms·백래시 1.5°)을 피팅이 정확히 복원(RMSE 1.76° → 0.11°).
WSL ROS 2 전체 흐름(`wsl_e2e_test.sh`)에서도 7.5°·1.5° 복원, 지연은 80 ms(ROS/TCP 경로 약 20 ms 포함).
2026-10-12 저녁: 위 1~8 전체를 dryrun으로 점검(`paper_DRYRUN/`, 그림에 DRY RUN 워터마크). steps에서 맞춘 7.5°·60 ms·1.5°를
staircase에 고정 적용해도 RMSE 1.94° → 0.12° 유지. table2.py는 점검 run을 거부하는 것까지 확인.
2026-10-12 20:04 시뮬레이션 단독(패널 없음) 점검 통과 — `sim_only_test.py`: G→1·후진→2·S→0 모두 Unity 3~4 ms, 워치독 503 ms(규칙 500),
조향 120 ms +5.95° · 연장 180 ms −9.01° · F 40 ms +1.94° (기대 ±0.1° 안). `wsl_unity_check.sh auto drive|steps|staircase`: 조향 RMSE 0.11/0.27/0.23°,
주행 상태 순서 0→1→0→2→0 일치. 주행 상태 시각은 Unity가 모델보다 최대 ~0.2 s 늦거나 빠름 = arduino_node 200 ms keepalive 위상(V는 keepalive 때만 전송)
→ 패널·트윈 두 브리지의 keepalive 위상이 서로 달라 **주행(속도) 응답 비교에는 최대 0.2 s 차이가 원래 섞인다**. 조향 펄스는 즉시 전달이라 무관.
