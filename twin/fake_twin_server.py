"""Unity 없이 트윈 브리지(socket://)를 시험하는 가짜 트윈 — firmware_model을 실시간으로 돌려 TCP로 응답한다.

  python3 fake_twin_server.py --port 55002 [--params dryrun_panel_params.json]

TwinFirmware.cs와 같은 규약(car_controller.ino)이라 kiis_testbed의 arduino_node가 그대로 붙는다.
점검용이다 — 이 서버로 얻은 데이터는 실험 데이터가 아니다.
"""
import argparse
import os
import socket
import time

import firmware_model as fm

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--port', type=int, default=55002)
    ap.add_argument('--params', default=None)
    a = ap.parse_args()
    params = fm.load_params(os.path.join(HERE, a.params) if a.params else None)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((a.host, a.port))
    srv.listen(1)
    print(f'[fake_twin] {a.host}:{a.port} 대기 (deg_per_pulse={params["deg_per_pulse"]})', flush=True)
    while True:
        conn, addr = srv.accept()
        conn.setblocking(False)
        print('[fake_twin] 연결', addr, flush=True)
        m = fm.FirmwareModel(params)
        m.pop_lines()
        start = time.monotonic()
        try:
            while True:
                try:
                    data = conn.recv(4096)
                    if data == b'':
                        break
                    m.feed(data.decode('ascii', errors='ignore'))
                except BlockingIOError:
                    pass
                target = int((time.monotonic() - start) * 1000)
                if target > m.t:
                    m.step(target - m.t)
                out = ''.join(line + '\r\n' for _, line in m.pop_lines())
                if out:
                    conn.sendall(out.encode())
                time.sleep(0.001)
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            conn.close()
            print('[fake_twin] 연결 끊김', flush=True)


if __name__ == '__main__':
    main()
