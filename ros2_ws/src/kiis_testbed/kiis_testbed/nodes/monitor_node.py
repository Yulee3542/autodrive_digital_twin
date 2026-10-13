#!/usr/bin/env python3
"""테스트베드 모니터 — 컨트롤 패널(보드)과 디지털 트윈(시뮬레이션)의 응답을 한 창에 나란히 보여 준다.

  ros2 run kiis_testbed monitor_node            (testbed.launch.py monitor:=true면 자동으로 뜸)

구독: 보드 /car/{connected,state,steering_pot,steering_angle} · 시뮬레이션 /twin/car/{…} · 명령 /car/cmd/*
화면: 위 = 두 장치 카드(연결·주행 상태·조향각·ADC), 가운데 = 조향각 차이, 아래 = 최근 30 s 조향각 그래프와 명령 기록.
보드를 안 꽂았으면 왼쪽 카드가 "대기 중"으로 남고, 꽂으면(브리지 reconnect) 바로 값이 들어온다.
창은 WSLg(윈도우 11)로 뜬다. 한글은 윈도우의 맑은 고딕을 직접 읽는다.
"""
import collections
import os
import threading
import time

WINDOW_S = 30.0
STALE_S = 1.0
STATE_TXT = {0: '정지', 1: '전진', 2: '후진'}
SOURCES = (('panel', '/car', '컨트롤 패널 (보드)', '#d1495b'), ('twin', '/twin/car', '디지털 트윈 (시뮬레이션)', '#00798c'))


def _setup_font(plt):
    from matplotlib import font_manager
    for path in ('/mnt/c/Windows/Fonts/malgun.ttf', '/mnt/c/Windows/Fonts/malgunbd.ttf'):
        if os.path.exists(path):
            font_manager.fontManager.addfont(path)
    if any(f.name == 'Malgun Gothic' for f in font_manager.fontManager.ttflist):
        plt.rcParams['font.family'] = 'Malgun Gothic'
    plt.rcParams['axes.unicode_minus'] = False


class Store:
    """ROS 콜백(스레드)과 그리기(메인 스레드) 사이의 공유 상태"""

    def __init__(self):
        self.lock = threading.Lock()
        self.t0 = time.monotonic()
        self.last = {s: {} for s, *_ in SOURCES}          # key → (값, 받은 시각)
        self.angle = {s: collections.deque() for s, *_ in SOURCES}
        self.cmds = collections.deque(maxlen=200)          # (시각, 문자열)

    def now(self):
        return time.monotonic() - self.t0

    def put(self, src, key, value):
        with self.lock:
            t = self.now()
            self.last[src][key] = (value, t)
            if key == 'steering_angle':
                self.angle[src].append((t, value))
                while self.angle[src] and self.angle[src][0][0] < t - WINDOW_S - 1:
                    self.angle[src].popleft()

    def cmd(self, text):
        with self.lock:
            self.cmds.append((self.now(), text))


def main(args=None):
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import Bool, Empty, Float32, Int8, Int16, Int32, String
    import matplotlib
    matplotlib.use('TkAgg')
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation

    store = Store()

    class MonitorNode(Node):
        def __init__(self):
            super().__init__('monitor_node')
            # 점검용: snapshot:=<경로.png>면 snapshot_after_s초 뒤 화면을 한 번 저장
            self.declare_parameter('snapshot', '')
            self.declare_parameter('snapshot_after_s', 8.0)
            for src, prefix, *_ in SOURCES:
                for key, typ in (('connected', Bool), ('state', Int8), ('steering_pot', Int32), ('steering_angle', Float32)):
                    self.create_subscription(typ, f'{prefix}/{key}',
                                             lambda m, s=src, k=key: store.put(s, k, m.data), 10)
            self.create_subscription(Empty, '/car/cmd/go', lambda m: store.cmd('go (주행 허용)'), 10)
            self.create_subscription(Empty, '/car/cmd/stop', lambda m: store.cmd('stop (정지)'), 10)
            self.create_subscription(Int16, '/car/cmd/drive', lambda m: store.cmd(f'drive {m.data:+d}'), 10)
            self.create_subscription(String, '/car/cmd/steer', lambda m: store.cmd(f'steer {m.data}'), 10)
            self.create_subscription(String, '/car/cmd/steer_pulse', lambda m: store.cmd(f'steer_pulse {m.data}'), 10)

    rclpy.init(args=args)
    node = MonitorNode()
    threading.Thread(target=rclpy.spin, args=(node,), daemon=True).start()

    _setup_font(plt)
    fig = plt.figure(figsize=(11, 7.2))
    fig.canvas.manager.set_window_title('KIIS 테스트베드 모니터 — 보드 vs 시뮬레이션')
    gs = fig.add_gridspec(3, 2, height_ratios=[1.25, 0.25, 2.2], width_ratios=[3, 1], hspace=0.35, wspace=0.08)
    ax_cards = fig.add_subplot(gs[0, :])
    ax_diff = fig.add_subplot(gs[1, :])
    ax_plot = fig.add_subplot(gs[2, 0])
    ax_log = fig.add_subplot(gs[2, 1])
    for a in (ax_cards, ax_diff, ax_log):
        a.set_axis_off()

    cards = {}
    for i, (src, prefix, title, color) in enumerate(SOURCES):
        x = 0.01 + i * 0.505
        ax_cards.add_patch(plt.Rectangle((x, 0.0), 0.485, 1.0, transform=ax_cards.transAxes,
                                         fc='#f7f7f7', ec=color, lw=2))
        ax_cards.text(x + 0.015, 0.86, title, transform=ax_cards.transAxes, fontsize=13, weight='bold', color=color)
        cards[src] = {
            'conn': ax_cards.text(x + 0.015, 0.66, '', transform=ax_cards.transAxes, fontsize=11),
            'angle': ax_cards.text(x + 0.015, 0.22, '', transform=ax_cards.transAxes, fontsize=30, weight='bold'),
            'state': ax_cards.text(x + 0.30, 0.48, '', transform=ax_cards.transAxes, fontsize=12),
            'adc': ax_cards.text(x + 0.30, 0.24, '', transform=ax_cards.transAxes, fontsize=10, color='#555555'),
            'topic': ax_cards.text(x + 0.015, 0.05, f'{prefix}/*', transform=ax_cards.transAxes, fontsize=8, color='#888888'),
        }
    diff_txt = ax_diff.text(0.5, 0.5, '', transform=ax_diff.transAxes, ha='center', va='center', fontsize=13)

    lines = {src: ax_plot.plot([], [], color=color, lw=1.6, drawstyle='steps-post',
                               label=title)[0] for src, _, title, color in SOURCES}
    ax_plot.set_ylim(-22, 22)
    ax_plot.set_ylabel('조향각 [deg]')
    ax_plot.set_xlabel('시간 [s] (0 = 지금)')
    ax_plot.grid(alpha=0.3)
    ax_plot.legend(loc='upper left', fontsize=9)
    ax_plot.axhline(0, color='#999999', lw=0.6)
    cmd_marks = []
    log_txt = ax_log.text(0.0, 1.0, '', transform=ax_log.transAxes, va='top', fontsize=9)
    ax_log.set_title('최근 명령', fontsize=10, loc='left')

    snapped = []

    def fresh(src, key, t):
        v = store.last[src].get(key)
        return v[0] if v and t - v[1] < STALE_S else None

    def update(_):
        with store.lock:
            t = store.now()
            ang_now = {}
            for src, *_ in SOURCES:
                c = cards[src]
                conn_msg = store.last[src].get('connected')
                if conn_msg is None or t - conn_msg[1] > STALE_S:
                    c['conn'].set_text('● 브리지 꺼짐 (testbed.launch 확인)')
                    c['conn'].set_color('#999999')
                elif conn_msg[0]:
                    c['conn'].set_text('● 연결됨')
                    c['conn'].set_color('#2e7d32')
                else:
                    c['conn'].set_text('● 대기 중 — ' + ('보드를 꽂으면 자동 연결' if src == 'panel' else 'Unity Play 대기'))
                    c['conn'].set_color('#e08a00')
                st, pot, ang = fresh(src, 'state', t), fresh(src, 'steering_pot', t), fresh(src, 'steering_angle', t)
                c['state'].set_text('주행: ' + (STATE_TXT.get(st, '—') if st is not None else '—'))
                c['adc'].set_text(f'POT ADC: {pot}' if pot is not None else 'POT ADC: —')
                if ang is not None:
                    c['angle'].set_text(f'{ang:+6.2f}°')
                    ang_now[src] = ang
                else:
                    c['angle'].set_text('  —' if pot is None else '보정 필요')
                d = list(store.angle[src])
                lines[src].set_data([p[0] - t for p in d], [p[1] for p in d])
            if len(ang_now) == 2:
                dd = ang_now['panel'] - ang_now['twin']
                diff_txt.set_text(f'조향각 차이 (보드 - 시뮬레이션): {dd:+.2f}°')
                diff_txt.set_color('#2e7d32' if abs(dd) < 1.0 else ('#e08a00' if abs(dd) < 3.0 else '#c62828'))
            else:
                diff_txt.set_text('조향각 차이: 두 장치가 모두 연결되면 표시')
                diff_txt.set_color('#888888')
            for m in cmd_marks:
                m.remove()
            cmd_marks.clear()
            recent = [(ct, txt) for ct, txt in store.cmds if ct > t - WINDOW_S]
            for ct, txt in recent:
                if txt.startswith('steer_pulse') or txt.startswith('drive') or txt.startswith('go') or txt.startswith('stop'):
                    cmd_marks.append(ax_plot.axvline(ct - t, color='#bbbbbb', lw=0.6, zorder=0))
            log_txt.set_text('\n'.join(f'{ct - t:6.1f}s  {txt}' for ct, txt in list(store.cmds)[-18:][::-1]))
        ax_plot.set_xlim(-WINDOW_S, 0.5)
        snap = node.get_parameter('snapshot').value
        if snap and not snapped and store.now() > node.get_parameter('snapshot_after_s').value:
            snapped.append(1)
            fig.savefig(snap, dpi=90)
            print(f'[monitor] 화면 저장 → {snap}', flush=True)
        return []

    _anim = FuncAnimation(fig, update, interval=100, cache_frame_data=False)  # noqa: F841 (참조 유지)
    try:  # WSLg가 창을 최소화/뒤쪽에 띄우는 경우가 있어 한 번 앞으로 (윈도우 쪽은 start_testbed.ps1이 다시 올림)
        win = fig.canvas.manager.window
        win.after(800, lambda: (win.deiconify(), win.lift(), win.attributes('-topmost', True),
                                win.after(1500, lambda: win.attributes('-topmost', False))))
    except Exception:
        pass
    try:
        plt.show()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
