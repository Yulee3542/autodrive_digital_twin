"""하드웨어·ROS 없이 실험 파이프라인 점검 — recorder_node와 같은 형식의 log.csv를 만든다.

  python dryrun.py --program steps --panel-params dryrun_panel_params.json
  python analyze.py runs/<폴더> --fit

panel = 일부러 파라미터를 다르게 준 firmware_model(가짜 패널), twin = 기본 파라미터 모델.
**결과는 실험 데이터가 아니다** (meta.json에 dry_run: true, 그래프에 DRY RUN 표시).
"""
import argparse
import csv
import json
import os
import time

import bridge_sim
import firmware_model as fm

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--program', default='steps', choices=['steps', 'staircase', 'drive'])
    ap.add_argument('--pulses', type=int, default=4)
    ap.add_argument('--panel-params', default='dryrun_panel_params.json')
    ap.add_argument('--twin-params', default=None, help='트윈 파라미터 json (없으면 twin_params.json/기본값) — 조정 후 run 흉내')
    ap.add_argument('--tag', default='')
    a = ap.parse_args()
    events, dur = bridge_sim.build(a.program, n=a.pulses)
    panel_p = fm.load_params(os.path.join(HERE, a.panel_params))
    twin_p = fm.load_params(a.twin_params)
    rows = bridge_sim.run(events, dur, panel_p, 'panel', seed=1) + bridge_sim.run(events, dur, twin_p, 'twin', seed=2)
    rows.sort(key=lambda r: r[0])
    run = os.path.join(HERE, 'runs', time.strftime('%Y%m%d_%H%M%S') + '_dryrun_' + a.program + (('_' + a.tag) if a.tag else ''))
    os.makedirs(run)
    with open(os.path.join(run, 'log.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['t', 'source', 'key', 'value'])
        w.writerows(rows)
    with open(os.path.join(run, 'meta.json'), 'w', encoding='utf-8') as f:
        json.dump({'program': a.program, 'pulses': a.pulses, 'dry_run': True, 'panel_params': a.panel_params,
                   'twin_params': a.twin_params}, f, indent=2)
    print('saved', run, len(rows), 'rows')


if __name__ == '__main__':
    main()
