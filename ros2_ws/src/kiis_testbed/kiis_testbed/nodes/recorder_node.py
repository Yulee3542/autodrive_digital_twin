#!/usr/bin/env python3
"""실험 기록 노드 — 명령(/car/cmd/*)과 두 장치의 응답(패널 /car/*, 트윈 /twin/car/*)을 한 CSV에 남긴다.

한 줄 = (t, source, key, value). t는 이 노드가 메시지를 받은 시각(초, 노드 시작 기준).
  source: cmd | panel | twin | marker
  key   : go/stop/drive/steer/steer_pulse | state/steering_pot/steering_angle | (marker 문자열)
분석은 twin/analyze.py가 이 파일(<run_dir>/log.csv)을 읽는다.
rosbag 대신 CSV인 이유: 윈도우 쪽 분석 스크립트가 ROS 없이 바로 읽게 하려고.
"""
import csv
import datetime
import json
import os
import time


def main(args=None):
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import Empty, Float32, Int8, Int16, Int32, String

    from .. import config

    class RecorderNode(Node):
        def __init__(self):
            super().__init__("recorder_node")
            self.declare_parameter("run_dir", config.RUN_DIR)
            self.declare_parameter("run_name", "")
            self.declare_parameter("note", "")
            name = self.get_parameter("run_name").value or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.dir = os.path.join(os.path.expanduser(self.get_parameter("run_dir").value), name)
            os.makedirs(self.dir, exist_ok=True)
            self.f = open(os.path.join(self.dir, "log.csv"), "w", newline="", encoding="utf-8")
            self.w = csv.writer(self.f)
            self.w.writerow(["t", "source", "key", "value"])
            self.t0 = time.monotonic()
            with open(os.path.join(self.dir, "meta.json"), "w", encoding="utf-8") as m:
                json.dump({"started": datetime.datetime.now().isoformat(timespec="seconds"),
                           "note": self.get_parameter("note").value}, m, ensure_ascii=False, indent=2)

            def sub(typ, topic, source, key):
                self.create_subscription(typ, topic, lambda msg: self.row(source, key, msg), 50)

            for key, typ in (("go", Empty), ("stop", Empty), ("drive", Int16), ("steer", String), ("steer_pulse", String)):
                sub(typ, f"/car/cmd/{key}", "cmd", key)
            for source, prefix in (("panel", "/car"), ("twin", "/twin/car")):
                sub(Int8, f"{prefix}/state", source, "state")
                sub(Int32, f"{prefix}/steering_pot", source, "steering_pot")
                sub(Float32, f"{prefix}/steering_angle", source, "steering_angle")
            self.create_subscription(String, "/experiment/marker", lambda msg: self.row("marker", msg.data, None), 10)
            self.get_logger().info(f"기록 → {self.dir}/log.csv")

        def row(self, source, key, msg):
            v = getattr(msg, "data", "") if msg is not None else ""
            if isinstance(v, float):
                v = round(v, 4)
            self.w.writerow([round(time.monotonic() - self.t0, 4), source, key, v])
            self.f.flush()

        def destroy_node(self):
            self.f.close()
            super().destroy_node()

    rclpy.init(args=args)
    node = RecorderNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
