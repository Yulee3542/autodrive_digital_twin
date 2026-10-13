"""논문 표 2 · 그림 3 만들기 — 조정 전/후 × 조정용(steps)/검증용(staircase) 네 run을 한 번에 정리한다.

  python table2.py --cal-before runs/<steps, 트윈 기본값> --val-before runs/<staircase, 트윈 기본값> \
                   --cal-after  runs/<steps, 트윈 조정 후> --val-after  runs/<staircase, 트윈 조정 후>

트윈 조정값은 --cal-before run에서 analyze.py --fit으로 만든 twin_params_fitted.json(--fitted로 바꿀 수 있음).
검증용 staircase는 조정에 쓰지 않은 명령 순서라, 조정 후 오차가 여기서도 줄면 과적합이 아니라는 근거가 된다.

나오는 것 (기본 twin/paper/):
  table2.md · table2.csv  — 표 2 (RMSE, 최대 오차, 90% 응답 시간, 잔류 각도)
  fig3_steering.pdf/png   — 그림 3 (a) steps (b) staircase: 패널 vs 트윈(기본) vs 트윈(조정 후)
  summary.json            — 위 값 + 패널 반복성(같은 명령 두 run의 패널끼리 RMSE) + Unity 트윈 vs 파이썬 모델 일치도
점검(DRY RUN) run이나 실측 아닌 calibration이 섞이면 거부한다 — 논문 수치에 점검 데이터를 쓰지 않기 위해.
(--allow-dry는 파이프라인 점검용: twin/paper_DRYRUN/에 DRY RUN 표시를 달아 저장)
"""
import argparse
import csv
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import analyze as an
import firmware_model as fm

HERE = os.path.dirname(os.path.abspath(__file__))


def load_run(path, cal):
    run = path if os.path.isabs(path) else os.path.join(HERE, path)
    meta = json.load(open(os.path.join(run, 'meta.json'), encoding='utf-8'))
    rows = an.read_log(run)
    ev = an.cmd_events(rows)
    t0 = an.first_pulse_t(ev)
    if t0 is None:
        sys.exit(f'{run}: 조향 펄스 명령이 없음')
    series = {}
    for src in ('panel', 'twin'):
        t, a = an.pot_series(rows, src, cal[src])
        if not len(t):
            sys.exit(f'{run}: {src} 응답이 없음')
        series[src] = (t, a)
    stops = [t for t, c, _ in ev if c == 'stop']
    return {'dir': run, 'name': os.path.basename(run.rstrip('/\\')), 'meta': meta, 'ev': ev, 't0': t0,
            'dur': rows[-1][0] + 0.1, 't_end': stops[-1] if stops else rows[-1][0], 'series': series,
            'pulses': sum(1 for _, c, _ in ev if c == 'steer_pulse')}


def metrics(r):
    (tp, ap_), (tt, at) = r['series']['panel'], r['series']['twin']
    rmse, mx = an.rmse_on(tp, ap_, tt, at)
    bts = an.batches(r['ev'])
    rp, rt = an.response_times(tp, ap_, bts), an.response_times(tt, at, bts)
    pairs = [(p, t) for p, t in zip(rp, rt) if p is not None and t is not None]
    return {
        'rmse_deg': round(rmse, 2), 'max_err_deg': round(mx, 2),
        'resp90_panel_s': round(float(np.mean([p for p, _ in pairs])), 3) if pairs else None,
        'resp90_twin_s': round(float(np.mean([t for _, t in pairs])), 3) if pairs else None,
        'init_panel_deg': round(an.level_before(tp, ap_, r['t0']), 2),
        'init_twin_deg': round(an.level_before(tt, at, r['t0']), 2),
        'final_panel_deg': round(an.level_before(tp, ap_, r['t_end']), 2),
        'final_twin_deg': round(an.level_before(tt, at, r['t_end']), 2),
    }


def shifted(r, src):
    t, a = r['series'][src]
    return t - r['t0'], a


def twin_vs_model(r, params):
    """Unity 트윈의 실제 응답 vs 같은 파라미터의 파이썬 모델 — 조정 후 run이면 Unity가 새 값을 읽었는지도 이걸로 안다."""
    tt, at = r['series']['twin']
    ts, a = an.sim_series(r['ev'], r['dur'], params, an.level_before(tt, at, r['t0']))
    return round(an.rmse_on(tt, at, ts, a)[0], 2)


def main():
    ap = argparse.ArgumentParser()
    for k in ('cal-before', 'val-before', 'cal-after', 'val-after'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('--fitted', help='기본: <cal-before>/twin_params_fitted.json')
    ap.add_argument('--out', default=None)
    ap.add_argument('--allow-dry', action='store_true')
    a = ap.parse_args()

    cal = an.load_cal()
    runs = {k: load_run(getattr(a, k.replace('-', '_')), cal) for k in ('cal-before', 'val-before', 'cal-after', 'val-after')}
    dry = [r['name'] for r in runs.values() if r['meta'].get('dry_run')]
    not_measured = [s for s in ('panel', 'twin') if not cal[s].get('measured', False)]
    if (dry or not_measured) and not a.allow_dry:
        sys.exit(f'거부: DRY RUN run {dry} / 실측 아닌 calibration {not_measured} — 논문 수치로 쓸 수 없음')
    is_dry = bool(dry or not_measured)
    out = a.out or os.path.join(HERE, 'paper_DRYRUN' if is_dry else 'paper')
    os.makedirs(out, exist_ok=True)

    fitted_path = a.fitted or os.path.join(runs['cal-before']['dir'], 'twin_params_fitted.json')
    if not os.path.exists(fitted_path):
        sys.exit(f'{fitted_path} 없음 — 먼저 python analyze.py <cal-before> --fit')
    fitted_raw = json.load(open(fitted_path, encoding='utf-8'))
    p_fit = fm.load_params(fitted_path)
    p_def = dict(fm.DEFAULT_PARAMS)
    notes = []
    if fitted_raw.get('_fitted_on') not in (None, runs['cal-before']['name']):
        notes.append(f"조정값이 {fitted_raw['_fitted_on']}에서 나옴 (cal-before = {runs['cal-before']['name']})")
    for k in ('cal', 'val'):
        if runs[k + '-before']['pulses'] != runs[k + '-after']['pulses']:
            notes.append(f'{k}: 조정 전/후 펄스 수가 다름 — 같은 프로그램·pulses로 다시 할 것')

    m = {k: metrics(r) for k, r in runs.items()}
    lim = cal['panel'].get('steer_limit_deg', 20.0)
    for k, r in runs.items():
        tp, ap_ = r['series']['panel']
        sat = float(np.mean(np.abs(ap_[(tp >= r['t0']) & (tp <= r['t_end'])]) > lim - 0.5))
        m[k]['panel_saturated_frac'] = round(sat, 2)
        if sat > 0.05:
            notes.append(f'{k}: 패널이 시간의 {sat:.0%} 동안 조향 한계(±{lim:g} deg)에 붙어 있음 — 한계는 두 장치가 정의상 같아 '
                         f'오차가 작게 나옴. pulses를 줄여 다시 할 것')
    # 패널 반복성: 같은 명령 두 번 → 패널끼리 RMSE (트윈이 이보다 더 좋아질 수는 없다)
    rep = {}
    for k in ('cal', 'val'):
        (t1, a1), (t2, a2) = shifted(runs[k + '-before'], 'panel'), shifted(runs[k + '-after'], 'panel')
        rep[k] = round(an.rmse_on(t1, a1, t2, a2)[0], 2)
    consistency = {k: twin_vs_model(r, p_def if k.endswith('before') else p_fit) for k, r in runs.items()}
    for k in ('cal-after', 'val-after'):
        if consistency[k] > 1.0:
            notes.append(f'{k}: Unity 트윈이 조정값 모델과 {consistency[k]} deg 다름 — Unity가 twin_params.json을 읽었는지 확인')

    def red(k):
        b, f = m[k + '-before']['rmse_deg'], m[k + '-after']['rmse_deg']
        return round(100 * (b - f) / b, 1) if b > 0 else None

    hdr = ['Data', 'Twin', 'RMSE [deg]', 'Max error [deg]', 't90 panel [s]', 't90 twin [s]', 'Residual panel/twin [deg]']
    lab = {'cal': 'Steps (tuning)', 'val': 'Staircase (validation)'}
    rows = []
    for k in ('cal', 'val'):
        for when, name in (('before', 'Default'), ('after', 'Tuned')):
            x = m[f'{k}-{when}']
            rows.append([lab[k], name, x['rmse_deg'], x['max_err_deg'], x['resp90_panel_s'], x['resp90_twin_s'],
                         f"{x['final_panel_deg']:+.2f} / {x['final_twin_deg']:+.2f}"])
    with open(os.path.join(out, 'table2.csv'), 'w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerows([hdr] + rows)
    md = ['| ' + ' | '.join(hdr) + ' |', '|' + '---|' * len(hdr)] + ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in rows]
    md += ['', f"Tuned twin parameters (fitted on steps): {p_fit['deg_per_pulse']:.2f} deg/pulse, "
                f"lag {p_fit['steer_lag_ms']:.0f} ms, backlash {p_fit['backlash_deg']:.1f} deg "
                f"(default {p_def['deg_per_pulse']:.2f} / {p_def['steer_lag_ms']:.0f} / {p_def['backlash_deg']:.1f})",
           f"RMSE reduction: steps {red('cal')} %, staircase {red('val')} %",
           f"Panel repeatability (panel vs panel, same program): steps {rep['cal']} deg, staircase {rep['val']} deg"]
    if is_dry:
        md.insert(0, '**DRY RUN — not experimental data**\n')
    with open(os.path.join(out, 'table2.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(md) + '\n')

    # ---- 그림 3 (2단 논문 한 단 폭) ----
    fig, axs = plt.subplots(2, 1, figsize=(3.4, 3.9), dpi=300, sharey=True)
    for ax, k, tag in zip(axs, ('cal', 'val'), ('(a) Steps (tuning)', '(b) Staircase (validation)')):
        ax.step(*shifted(runs[k + '-after'], 'panel'), where='post', color='#d1495b', lw=1.3, label='Control panel')
        ax.step(*shifted(runs[k + '-before'], 'twin'), where='post', color='#00798c', lw=1.0, ls='--', label='Twin (default)')
        ax.step(*shifted(runs[k + '-after'], 'twin'), where='post', color='#edae49', lw=1.1, ls='-.', label='Twin (tuned)')
        for t, c, _ in runs[k + '-after']['ev']:
            if c == 'steer_pulse':
                ax.axvline(t - runs[k + '-after']['t0'], color='#cccccc', lw=0.3, zorder=0)
        ax.set_title(tag, fontsize=7, loc='left')
        ax.set_ylabel('Steering [deg]', fontsize=7)
        ax.tick_params(labelsize=6)
        ax.grid(alpha=0.3, lw=0.4)
        ax.set_xlim(-0.5, runs[k + '-after']['t_end'] - runs[k + '-after']['t0'] + 0.5)
    axs[-1].set_xlabel('Time from first steering command [s]', fontsize=7)
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, fontsize=6, loc='upper center', ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.0))
    if is_dry:
        fig.text(0.5, 0.5, 'DRY RUN', fontsize=28, color='red', alpha=0.25, ha='center', va='center', rotation=20)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    for ext in ('png', 'pdf'):
        fig.savefig(os.path.join(out, 'fig3_steering.' + ext))

    summary = {'dry_run': is_dry, 'runs': {k: r['name'] for k, r in runs.items()}, 'metrics': m,
               'rmse_reduction_pct': {'steps': red('cal'), 'staircase': red('val')},
               'panel_repeatability_rmse_deg': {'steps': rep['cal'], 'staircase': rep['val']},
               'twin_vs_python_model_rmse_deg': consistency,
               'fitted_params': {k: p_fit[k] for k in ('deg_per_pulse', 'steer_lag_ms', 'backlash_deg')},
               'default_params': {k: p_def[k] for k in ('deg_per_pulse', 'steer_lag_ms', 'backlash_deg')},
               'notes': notes}
    with open(os.path.join(out, 'summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print('\n'.join(md))
    print(json.dumps({k: summary[k] for k in ('panel_repeatability_rmse_deg', 'twin_vs_python_model_rmse_deg', 'notes')},
                     ensure_ascii=False, indent=2))
    print('→', out)


if __name__ == '__main__':
    main()
