"""테스트베드 기동: 패널 브리지(시리얼) + 트윈 브리지(TCP, Unity) + 기록 노드.

두 브리지는 같은 arduino_node이고 같은 /car/cmd/*를 구독한다 — 명령은 teleop_node나
experiment_node가 따로 낸다(teleop은 stdin이 필요해 ros2 run으로 직접 실행).

  ros2 launch kiis_testbed testbed.launch.py panel_port:=/dev/ttyACM0 \
      panel_adc_left:=830 panel_adc_right:=150
  ros2 launch kiis_testbed testbed.launch.py panel_port:=none          # 트윈만
  ros2 launch kiis_testbed testbed.launch.py twin:=false               # 패널만

인자
  panel_port   auto(포트 자동 감지) | none(패널 없음) | /dev/ttyACM0 ...
  twin         true | false
  twin_host    auto(WSL2 NAT의 윈도우 호스트 = 기본 게이트웨이) | 127.0.0.1(mirrored 네트워킹) | IP
  twin_port    55002 (TwinFirmware.cs의 port와 같아야 함)
  *_adc_left/right  조향 POT 좌/우 한계 ADC — 주면 /…/steering_angle(deg)도 발행
  record       true면 recorder_node가 ~/kiis_logs/runs/<시각>/log.csv에 기록
  monitor      web = web_monitor_node(윈도우 브라우저 http://localhost:8765) · gui(=true) = monitor_node(WSLg 창) · false
플러그 앤 플레이(2026-10-12~): 두 브리지는 reconnect 모드 — 패널을 나중에 꽂거나 뽑아도, Unity Play를
나중에 누르거나 다시 눌러도 1초 안에 다시 붙는다(재연결 직후엔 G를 자동으로 보내지 않음).
"""
import subprocess

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch_ros.actions import Node


def _windows_host():
    try:
        out = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=2).stdout
        return out.split()[2]
    except Exception:
        return "127.0.0.1"


def _setup(context):
    a = dict(context.launch_configurations)   # 값은 이미 문자열
    nodes = []
    if a["panel_port"] != "none":
        nodes.append(Node(
            package="kiis_testbed", executable="arduino_node", name="panel_bridge", output="screen",
            parameters=[{
                "port": "" if a["panel_port"] == "auto" else a["panel_port"], "reconnect": True,
                "cmd_prefix": "/car/cmd", "state_prefix": "/car",
                "steering_adc_left": float(a["panel_adc_left"]), "steering_adc_right": float(a["panel_adc_right"]),
            }]))
    if a["twin"].lower() == "true":
        host = _windows_host() if a["twin_host"] == "auto" else a["twin_host"]
        nodes.append(Node(
            package="kiis_testbed", executable="arduino_node", name="twin_bridge", output="screen",
            parameters=[{
                "port": f"socket://{host}:{a['twin_port']}", "reconnect": True,
                "cmd_prefix": "/car/cmd", "state_prefix": "/twin/car",
                "steering_adc_left": float(a["twin_adc_left"]), "steering_adc_right": float(a["twin_adc_right"]),
            }]))
    if a["record"].lower() == "true":
        nodes.append(Node(package="kiis_testbed", executable="recorder_node", name="recorder", output="screen",
                          parameters=[{"run_name": a["run_name"], "note": a["note"]}]))
    mon = a["monitor"].lower()
    if mon == "web":
        nodes.append(Node(package="kiis_testbed", executable="web_monitor_node", name="web_monitor", output="screen"))
    elif mon in ("true", "gui"):
        nodes.append(Node(package="kiis_testbed", executable="monitor_node", name="monitor", output="screen"))
    return nodes


def generate_launch_description():
    args = [
        ("panel_port", "auto"), ("panel_adc_left", "0.0"), ("panel_adc_right", "0.0"),
        ("twin", "true"), ("twin_host", "auto"), ("twin_port", "55002"),
        ("twin_adc_left", "825.0"), ("twin_adc_right", "146.0"),
        ("record", "true"), ("run_name", ""), ("note", ""), ("monitor", "false"),
    ]
    return LaunchDescription([DeclareLaunchArgument(n, default_value=d) for n, d in args] + [OpaqueFunction(function=_setup)])
