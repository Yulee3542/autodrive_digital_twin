"""실험 결과 분석: 패널·트윈 조향각 비교 그래프, 오차 지표, 트윈 파라미터 맞추기(fitting).

  python analyze.py runs/<실험폴더>            # 그래프 + 지표
  python analyze.py runs/<실험폴더> --fit      # 패널 응답에 맞춰 트윈 파라미터 탐색 → twin_params_fitted.json
  python analyze.py runs/<staircase> --params runs/<steps>/twin_params_fitted.json
                                              # 다른 run(steps)에서 맞춘 값을 고정 적용 → 검증(과적합 확인)

입력: recorder_node(또는 dryrun.py)의 <run>/log.csv — (t, source, key, value).
ADC → 각도는 calibration.json의 장치별 좌/우 한계 ADC로 arduino_node.adc_to_deg와 같은 식을 쓴다.
패널 가변저항은 차량과 다른 부품이라 반드시 패널에서 따로 재서 넣을 것.
"""
import argparse
import csv
import json
import os

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import bridge_sim
import firmware_model as fm

HERE = os.path.dirname(os.path.abspath(__file__))


def load_cal():
    with open(os.path.join(HERE, 'calibration.json'), encoding='utf-8') as f:
        return json.load(f)


def read_log(run):
    with open(os.path.join(run, 'log.csv'), encoding='utf-8') as f:
        r = csv.reader(f)
        next(r)
        return [(float(t), s, k, v) for t, s, k, v in r]


def pot_series(rows, source, cal):
    t, a = [], []
    for ts, s, k, v in rows:
        if s == source and k == 'steering_pot':
            t.append(ts)
            a.append(fm.adc_to_angle(cal, int(float(v))))
    return np.array(t), np.array(a)


def cmd_events(rows):
    ev = []
    for ts, s, k, v in rows:
        if s != 'cmd':
            continue
        if k in ('go', 'stop'):
            ev.append((ts, k, None))
        elif k == 'drive':
            ev.append((ts, k, int(float(v))))
        else:
            ev.append((ts, k, v))
    return ev


def rmse_on(t_ref, a_ref, t_x, a_x):
    lo, hi = max(t_ref[0], t_x[0]), min(t_ref[-1], t_x[-1])
    sel = (t_ref >= lo) & (t_ref <= hi)
    e = a_ref[sel] - np.interp(t_ref[sel], t_x, a_x)
    return float(np.sqrt(np.mean(e ** 2))), float(np.max(np.abs(e)))


def batches(ev, gap=0.5):
    """연속된 steer_pulse 묶음 → (시작, 끝, 방향, 펄스 수)"""
    out = []
    for t, c, v in ev:
        if c != 'steer_pulse':
            continue
        if out and out[-1][2] == v and t - out[-1][1] < gap:
            s, _, d, n = out[-1]
            out[-1] = (s, t, d, n + 1)
        else:
            out.append((t, t, v, 1))
    return out


def response_times(t, a, bts, settle=1.5):
    """각 묶음 첫 명령 → 최종 변화량의 90% 도달까지 [s]"""
    res = []
    for s, e, d, n in bts:
        pre = a[(t >= s - 0.3) & (t < s)]
        post = a[(t >= e + settle - 0.3) & (t < e + settle)]
        if len(pre) == 0 or len(post) == 0 or abs(post.mean() - pre.mean()) < 0.5:
            res.append(None)
            continue
        a0, a1 = pre.mean(), post.mean()
        target = a0 + 0.9 * (a1 - a0)
        win = (t >= s) & (t < e + settle)
        hit = np.where((a[win] - target) * np.sign(a1 - a0) >= 0)[0]
        res.append(round(float(t[win][hit[0]] - s), 3) if len(hit) else None)
    return res


def first_pulse_t(ev):
    ts = [t for t, c, _ in ev if c == 'steer_pulse']
    return ts[0] if ts else None


def level_before(t, a, t_ref, win=0.5):
    """t_ref 직전 win초 평균 각도 — 실험 시작 시 장치가 놓인 각도"""
    sel = (t >= t_ref - win) & (t < t_ref)
    return float(a[sel].mean()) if sel.any() else (float(a[0]) if len(a) else 0.0)


def sim_series(ev, dur, params, init=0.0):
    rows = bridge_sim.run(ev, dur, params, 'twin', offset=0.0, init_angle=init)
    return pot_series([(t, s, k, v) for t, s, k, v in rows], 'twin', params)


def fit(ev, dur, tp, ap_, init=0.0):
    base = fm.load_params()

    def score(**kw):
        p = dict(base, **kw)
        ts, a = sim_series(ev, dur, p, init)
        return rmse_on(tp, ap_, ts, a)[0], p
    # 1단계: 펄스당 각도만 굵게
    best = min((score(deg_per_pulse=float(d)) for d in np.arange(2.0, 14.01, 0.5)), key=lambda x: x[0])
    d0 = best[1]['deg_per_pulse']
    # 2단계: 주변을 촘촘히 + 지연·백래시
    for d in np.arange(d0 - 0.5, d0 + 0.51, 0.1):
        for lag in (0, 20, 40, 60, 80, 100, 130, 160):
            for bl in (0, 0.5, 1.0, 1.5, 2.0, 3.0):
                cand = score(deg_per_pulse=float(round(d, 2)), steer_lag_ms=float(lag), backlash_deg=float(bl))
                if cand[0] < best[0]:
                    best = cand
    return best, score()[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('run')
    ap.add_argument('--fit', action='store_true')
    ap.add_argument('--params', help='고정 적용할 트윈 파라미터 json (예: steps run의 twin_params_fitted.json)')
    a = ap.parse_args()
    run = a.run if os.path.isabs(a.run) else os.path.join(HERE, a.run)
    meta = json.load(open(os.path.join(run, 'meta.json'), encoding='utf-8'))
    cal = load_cal()
    rows = read_log(run)
    ev = cmd_events(rows)
    dur = rows[-1][0] + 0.1
    series = {}
    for src in ('panel', 'twin'):
        t, ang = pot_series(rows, src, cal[src])
        if len(t):
            series[src] = (t, ang)
    bts = batches(ev)

    report = {'run': os.path.basename(run), 'dry_run': meta.get('dry_run', False), 'pulse_batches': len(bts),
              'calibration_measured': {s: cal[s].get('measured', False) for s in ('panel', 'twin')}}
    t_start = first_pulse_t(ev)
    stop_ts = [t for t, c, _ in ev if c == 'stop']
    t_end = stop_ts[-1] if stop_ts else dur
    init = {}
    for src, (t, ang) in series.items():
        report[src + '_response_time_s'] = response_times(t, ang, bts)
        if t_start is not None:
            init[src] = level_before(t, ang, t_start)
            report[src + '_init_deg'] = round(init[src], 2)
            # 마지막 묶음 뒤 남은 각도 — 펄스 수만 맞춰 되돌아왔을 때의 잔류 오프셋 (본문 3.2 ④)
            report[src + '_final_deg'] = round(level_before(t, ang, t_end), 2)
    warns = []
    off = [f'{s} {v:+.2f} deg' for s, v in init.items() if abs(v) > 1.0]
    if off:
        warns.append('중앙(±1 deg)에서 시작하지 않음: ' + ', '.join(off) + ' — 패널은 손/펄스로, 트윈은 C 키로 중앙에 두고 다시 할 것')
    if not all(report['calibration_measured'].values()):
        warns.append('calibration.json panel 값이 실측이 아님(measured=false)')
    if warns:
        report['warning'] = ' | '.join(warns)
    p_init = init.get('panel', 0.0)
    if 'panel' in series and 'twin' in series:
        r, mx = rmse_on(*series['panel'], *series['twin'])
        report['rmse_deg_twin_vs_panel'] = round(r, 3)
        report['max_err_deg_twin_vs_panel'] = round(mx, 3)

    tuned = fixed = None
    if a.fit and 'panel' in series:
        (r1, p1), r0 = fit(ev, dur, *series['panel'], init=p_init)
        base = fm.load_params()
        report['fit'] = {'rmse_model_start_params_deg': round(r0, 3), 'rmse_model_tuned_deg': round(r1, 3),
                         'start_params': {k: base[k] for k in ('deg_per_pulse', 'steer_lag_ms', 'backlash_deg')},
                         'deg_per_pulse': round(p1['deg_per_pulse'], 2), 'steer_lag_ms': p1['steer_lag_ms'],
                         'backlash_deg': p1['backlash_deg'], 'model_init_deg': round(p_init, 2)}
        with open(os.path.join(run, 'twin_params_fitted.json'), 'w', encoding='utf-8') as f:
            json.dump({'_fitted_on': os.path.basename(run), '_dry_run': bool(meta.get('dry_run', False)),
                       **{k: p1[k] for k in ('deg_per_pulse', 'steer_lag_ms', 'backlash_deg')}}, f, ensure_ascii=False, indent=2)
        tuned = sim_series(ev, dur, p1, p_init)
    if a.params and 'panel' in series:
        pf = fm.load_params(a.params)
        fixed = sim_series(ev, dur, pf, p_init)
        r, mx = rmse_on(*series['panel'], *fixed)
        report['fixed_params'] = {'file': os.path.relpath(a.params, HERE), 'rmse_model_deg': round(r, 3),
                                  'max_err_model_deg': round(mx, 3),
                                  **{k: pf[k] for k in ('deg_per_pulse', 'steer_lag_ms', 'backlash_deg')}}

    # ---- 그래프 (논문용: 영문 라벨) ----
    fig, axp = plt.subplots(figsize=(6.4, 3.0), dpi=200)
    style = {'panel': dict(color='#d1495b', label='Control panel'),
             'twin': dict(color='#00798c', ls='--', label='Digital twin')}
    for src, (t, ang) in series.items():
        axp.step(t, ang, where='post', lw=1.4, **style[src])
    if tuned is not None:
        axp.step(*tuned, where='post', color='#edae49', lw=1.2, ls=':', label='Twin model (fitted here)')
    if fixed is not None:
        axp.step(*fixed, where='post', color='#30638e', lw=1.2, ls='-.', label='Twin model (fixed params)')
    for t, c, v in ev:
        if c == 'steer_pulse':
            axp.axvline(t, color='#bbbbbb', lw=0.4, zorder=0)
    axp.set_xlabel('Time [s]')
    axp.set_ylabel('Steering angle [deg]')
    axp.grid(alpha=0.3)
    axp.legend(fontsize=7, loc='upper right')
    if meta.get('dry_run'):
        axp.set_title('DRY RUN (firmware model) - not experimental data', fontsize=8, color='red')
    fig.tight_layout()
    for ext in ('png', 'pdf'):
        fig.savefig(os.path.join(run, 'steering_compare.' + ext))
    with open(os.path.join(run, 'report.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
