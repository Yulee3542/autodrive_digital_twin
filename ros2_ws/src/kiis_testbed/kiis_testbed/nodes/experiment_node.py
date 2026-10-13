#!/usr/bin/env python3
"""실험 명령 노드 — 정해진 명령 프로그램(programs.py)을 /car/cmd/*로 시각에 맞춰 발행하고 끝나면 종료한다.

teleop_node가 사람이 키보드로 내는 명령이라면, 이 노드는 같은 토픽에 '반복 가능한' 명령을 낸다.
패널 브리지와 트윈 브리지가 둘 다 /car/cmd/*를 구독하므로, 한 번 발행한 명령이 두 장치에 똑같이 간다.

  ros2 run kiis_testbed experiment_node --ros-args -p program:=steps -p pulses:=4
"""
import time


def main(args=None):
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import Empty, Int16, String

    from .. import programs

    class ExperimentNode(Node):
        def __init__(self):
            super().__init__("experiment_node")
            self.declare_parameter("program", "steps")
            self.declare_parameter("pulses", 4)
            self.declare_parameter("gap_s", 0.0)        # 0 = 프로그램 기본값
            self.declare_parameter("pwm", 60)
            self.declare_parameter("start_delay_s", 2.0)  # 브리지·기록 노드가 구독을 잡을 시간
            name = self.get_parameter("program").value
            kw = {"n": self.get_parameter("pulses").value}
            if self.get_parameter("gap_s").value > 0:
                kw["gap"] = self.get_parameter("gap_s").value
            if name == "drive":
                kw["pwm"] = self.get_parameter("pwm").value
            self.events, self.duration = programs.build(name, **kw)
            self.name = name
            self.pubs = {
                "go": self.create_publisher(Empty, "/car/cmd/go", 10),
                "stop": self.create_publisher(Empty, "/car/cmd/stop", 10),
                "drive": self.create_publisher(Int16, "/car/cmd/drive", 10),
                "steer": self.create_publisher(String, "/car/cmd/steer", 10),
                "steer_pulse": self.create_publisher(String, "/car/cmd/steer_pulse", 10),
            }
            self.marker = self.create_publisher(String, "/experiment/marker", 10)

        def send(self, cmd, value):
            pub = self.pubs[cmd]
            if cmd in ("go", "stop"):
                pub.publish(Empty())
            elif cmd == "drive":
                pub.publish(Int16(data=int(value)))
            else:
                pub.publish(String(data=str(value)))

        def run(self):
            delay = self.get_parameter("start_delay_s").value
            print(f"[experiment] {self.name}: {len(self.events)}개 명령, {self.duration:.1f}s — {delay:.1f}s 후 시작")
            time.sleep(delay)
            self.marker.publish(String(data=f"start {self.name}"))
            t0 = time.monotonic()
            for t, cmd, value in self.events:
                while time.monotonic() - t0 < t:
                    time.sleep(0.0005)
                self.send(cmd, value)
            while time.monotonic() - t0 < self.duration:
                time.sleep(0.01)
            self.marker.publish(String(data=f"end {self.name}"))
            print("[experiment] 끝")

    rclpy.init(args=args)
    node = ExperimentNode()
    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.send("stop", None)
        time.sleep(0.2)
        node.destroy_node()
        rclpy.shutdown()
