#!/usr/bin/env python3
"""테스트베드 웹 모니터 — 보드(컨트롤 패널)와 시뮬레이션(디지털 트윈)을 브라우저 한 화면에 나란히.

  ros2 run kiis_testbed web_monitor_node      → 윈도우 브라우저에서 http://localhost:8765
  (testbed.launch.py monitor:=web, start_testbed.bat가 브라우저까지 연다)

monitor_node(WSLg 창)와 같은 내용인데, WSLg 창이 안 그려지거나 다른 창 뒤에 숨는 문제가 있어(2026-10-12)
윈도우 브라우저로 보는 방식을 기본으로 했다. WSL2 NAT의 localhost 전달로 윈도우→WSL 접속이라 방화벽과 무관.
의존성 없음(파이썬 표준 http.server). 페이지는 /state(JSON)를 0.1 s마다 받아 그린다.
"""
import collections
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WINDOW_S = 30.0
STALE_S = 1.0
SOURCES = (('panel', '/car'), ('twin', '/twin/car'))

PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>KIIS 테스트베드 모니터</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 :root { --panel:#d1495b; --twin:#00798c; --ok:#2e7d32; --wait:#e08a00; --off:#999; --bg:#fafafa; --card:#fff; --ink:#222; --sub:#666; }
 body { margin:0; font-family:"Malgun Gothic","Apple SD Gothic Neo",sans-serif; background:var(--bg); color:var(--ink); }
 header { padding:12px 20px; font-size:18px; font-weight:700; border-bottom:1px solid #ddd; background:#fff; display:flex; justify-content:space-between; }
 header span { font-size:13px; font-weight:400; color:var(--sub); }
 .cards { display:grid; grid-template-columns:1fr 1fr; gap:16px; padding:16px 20px 0; }
 .card { background:var(--card); border:2px solid; border-radius:10px; padding:14px 18px; }
 .card h2 { margin:0 0 6px; font-size:17px; }
 .conn { font-size:14px; margin-bottom:8px; }
 .row { display:flex; align-items:baseline; gap:28px; }
 .angle { font-size:52px; font-weight:800; font-variant-numeric:tabular-nums; min-width:220px; }
 .meta { font-size:15px; line-height:1.7; color:var(--sub); }
 .meta b { color:var(--ink); }
 .topic { font-size:11px; color:#aaa; }
 #diff { text-align:center; font-size:20px; padding:12px; font-weight:600; }
 .bottom { display:grid; grid-template-columns:3fr 1fr; gap:16px; padding:0 20px 20px; }
 canvas { width:100%; height:330px; background:#fff; border:1px solid #ddd; border-radius:8px; }
 #log { background:#fff; border:1px solid #ddd; border-radius:8px; padding:10px 12px; font-size:13px; height:308px; overflow:hidden; white-space:pre; font-variant-numeric:tabular-nums; }
 #log h3 { margin:0 0 6px; font-size:14px; }
 .legend { font-size:13px; color:var(--sub); margin:4px 2px; }
 .legend i { display:inline-block; width:18px; height:3px; vertical-align:middle; margin:0 4px 0 12px; }
</style></head><body>
<header>KIIS 테스트베드 모니터 — 보드 vs 시뮬레이션 <span id="clock">연결 중…</span></header>
<div class="cards">
 <div class="card" style="border-color:var(--panel)"><h2 style="color:var(--panel)">컨트롤 패널 (보드)</h2>
  <div class="conn" id="panel_conn"></div>
  <div class="row"><div class="angle" id="panel_angle">—</div><div class="meta">주행: <b id="panel_state">—</b><br>POT ADC: <b id="panel_adc">—</b></div></div>
  <div class="topic">/car/*</div></div>
 <div class="card" style="border-color:var(--twin)"><h2 style="color:var(--twin)">디지털 트윈 (시뮬레이션)</h2>
  <div class="conn" id="twin_conn"></div>
  <div class="row"><div class="angle" id="twin_angle">—</div><div class="meta">주행: <b id="twin_state">—</b><br>POT ADC: <b id="twin_adc">—</b></div></div>
  <div class="topic">/twin/car/*</div></div>
</div>
<div id="diff">—</div>
<div class="bottom">
 <div><canvas id="plot"></canvas>
  <div class="legend"><i style="background:var(--panel)"></i>컨트롤 패널 (보드)<i style="background:var(--twin)"></i>디지털 트윈 (시뮬레이션)<i style="background:#ccc;height:10px;width:1px"></i>명령 시점 · 최근 30초 조향각 [deg]</div></div>
 <div id="log"><h3>최근 명령</h3><div id="logbody"></div></div>
</div>
<script>
const STATE = {0:'정지', 1:'전진', 2:'후진'};
const C = {panel:'#d1495b', twin:'#00798c'};
function setConn(id, c, src) {
  const el = document.getElementById(id);
  if (c === null) { el.textContent = '● 브리지 꺼짐 (testbed 확인)'; el.style.color = 'var(--off)'; }
  else if (c) { el.textContent = '● 연결됨'; el.style.color = 'var(--ok)'; }
  else { el.textContent = '● 대기 중 — ' + (src === 'panel' ? '보드를 꽂으면 자동 연결' : 'Unity Play 대기'); el.style.color = 'var(--wait)'; }
}
function draw(d) {
  const cv = document.getElementById('plot'), r = window.devicePixelRatio || 1;
  const W = cv.clientWidth, H = cv.clientHeight; cv.width = W * r; cv.height = H * r;
  const g = cv.getContext('2d'); g.scale(r, r); g.clearRect(0, 0, W, H);
  const L = 42, R = 10, T = 10, B = 26, pw = W - L - R, ph = H - T - B;
  const X = t => L + (t + d.window) / (d.window + 0.5) * pw, Y = a => T + (22 - a) / 44 * ph;
  g.font = '11px sans-serif'; g.fillStyle = '#888'; g.strokeStyle = '#eee'; g.lineWidth = 1;
  for (let a = -20; a <= 20; a += 10) { g.beginPath(); g.moveTo(L, Y(a)); g.lineTo(L + pw, Y(a)); g.stroke(); g.fillText(a, 8, Y(a) + 4); }
  for (let t = -30; t <= 0; t += 5) { g.fillText(t + 's', X(t) - 10, H - 8); }
  g.strokeStyle = '#ccc'; for (const c of d.cmds) { if (c.t >= -d.window) { g.beginPath(); g.moveTo(X(c.t), T); g.lineTo(X(c.t), T + ph); g.stroke(); } }
  for (const src of ['panel', 'twin']) {
    const s = d[src].series; if (!s.length) continue;
    g.strokeStyle = C[src]; g.lineWidth = 2; g.beginPath();
    s.forEach((p, i) => { const x = X(p[0]), y = Y(p[1]); if (i) { g.lineTo(x, Y(s[i-1][1])); g.lineTo(x, y); } else g.moveTo(x, y); });
    g.lineTo(X(0), Y(s[s.length - 1][1])); g.stroke();
  }
}
async function tick() {
  try {
    const d = await (await fetch('/state', {cache:'no-store'})).json();
    for (const src of ['panel', 'twin']) {
      const s = d[src];
      setConn(src + '_conn', s.connected, src);
      document.getElementById(src + '_angle').textContent = s.angle !== null ? (s.angle >= 0 ? '+' : '') + s.angle.toFixed(2) + '°' : (s.pot !== null ? '보정 필요' : '—');
      document.getElementById(src + '_state').textContent = s.state !== null ? (STATE[s.state] || s.state) : '—';
      document.getElementById(src + '_adc').textContent = s.pot !== null ? s.pot : '—';
    }
    const df = document.getElementById('diff');
    if (d.panel.angle !== null && d.twin.angle !== null) {
      const v = d.panel.angle - d.twin.angle;
      df.textContent = '조향각 차이 (보드 - 시뮬레이션): ' + (v >= 0 ? '+' : '') + v.toFixed(2) + '°';
      df.style.color = Math.abs(v) < 1 ? 'var(--ok)' : (Math.abs(v) < 3 ? 'var(--wait)' : '#c62828');
    } else { df.textContent = '조향각 차이: 두 장치가 모두 연결되면 표시'; df.style.color = 'var(--off)'; }
    document.getElementById('logbody').textContent = d.cmds.slice().reverse().slice(0, 18).map(c => c.t.toFixed(1).padStart(6) + 's  ' + c.text).join('\n');
    document.getElementById('clock').textContent = '갱신 ' + new Date().toLocaleTimeString();
    draw(d);
  } catch (e) { document.getElementById('clock').textContent = '테스트베드 연결 끊김 — WSL의 testbed가 켜져 있는지 확인'; }
  setTimeout(tick, 100);
}
tick();
</script></body></html>
"""


class Store:
    def __init__(self):
        self.lock = threading.Lock()
        self.t0 = time.monotonic()
        self.last = {s: {} for s, _ in SOURCES}
        self.angle = {s: collections.deque() for s, _ in SOURCES}
        self.cmds = collections.deque(maxlen=200)

    def now(self):
        return time.monotonic() - self.t0

    def put(self, src, key, value):
        with self.lock:
            t = self.now()
            self.last[src][key] = (value, t)
            if key == 'steering_angle':
                q = self.angle[src]
                q.append((t, value))
                while q and q[0][0] < t - WINDOW_S - 1:
                    q.popleft()

    def cmd(self, text):
        with self.lock:
            self.cmds.append((self.now(), text))

    def snapshot(self):
        with self.lock:
            t = self.now()
            out = {'window': WINDOW_S, 'cmds': [{'t': round(ct - t, 2), 'text': x} for ct, x in self.cmds if ct > t - WINDOW_S]}
            for src, _ in SOURCES:
                def fresh(k):
                    v = self.last[src].get(k)
                    return v[0] if v and t - v[1] < STALE_S else None
                conn = self.last[src].get('connected')
                pts = list(self.angle[src])
                step = max(1, len(pts) // 600)
                out[src] = {
                    'connected': None if conn is None or t - conn[1] > STALE_S else bool(conn[0]),
                    'state': None if fresh('state') is None or fresh('state') < 0 else fresh('state'),  # -1 = 브리지가 아직 모름
                    'pot': fresh('steering_pot'),
                    'angle': None if fresh('steering_angle') is None else round(float(fresh('steering_angle')), 3),
                    'series': [[round(pt - t, 3), round(float(a), 3)] for pt, a in pts[::step]],
                }
            return out


def main(args=None):
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import Bool, Empty, Float32, Int8, Int16, Int32, String

    store = Store()

    class WebMonitorNode(Node):
        def __init__(self):
            super().__init__('web_monitor_node')
            self.declare_parameter('port', 8765)
            for src, prefix in SOURCES:
                for key, typ in (('connected', Bool), ('state', Int8), ('steering_pot', Int32), ('steering_angle', Float32)):
                    self.create_subscription(typ, f'{prefix}/{key}', lambda m, s=src, k=key: store.put(s, k, m.data), 10)
            self.create_subscription(Empty, '/car/cmd/go', lambda m: store.cmd('go (주행 허용)'), 10)
            self.create_subscription(Empty, '/car/cmd/stop', lambda m: store.cmd('stop (정지)'), 10)
            self.create_subscription(Int16, '/car/cmd/drive', lambda m: store.cmd(f'drive {m.data:+d}'), 10)
            self.create_subscription(String, '/car/cmd/steer', lambda m: store.cmd(f'steer {m.data}'), 10)
            self.create_subscription(String, '/car/cmd/steer_pulse', lambda m: store.cmd(f'steer_pulse {m.data}'), 10)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith('/state'):
                body, ctype = json.dumps(store.snapshot()).encode(), 'application/json'
            elif self.path in ('/', '/index.html'):
                body, ctype = PAGE.encode('utf-8'), 'text/html; charset=utf-8'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    rclpy.init(args=args)
    node = WebMonitorNode()
    port = node.get_parameter('port').value
    srv = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    node.get_logger().info(f'웹 모니터: 윈도우 브라우저에서 http://localhost:{port}')
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        srv.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
