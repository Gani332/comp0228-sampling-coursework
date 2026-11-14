"""Graphs derived from saved controlled-study summaries; no simulation changes."""
import json
from pathlib import Path


def plot_study(study):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import pandas as pd

    study = Path(study)
    data = pd.DataFrame(json.loads((study/'summary.json').read_text()))
    config = json.loads((study/'config.json').read_text())
    models = ['iid_flip', 'burst_flip', 'glare_burst']
    labels = ['Independent bit flips', 'Markov burst flips', 'Force-to-one glare bursts']
    colors = dict(zip(config['codecs'], plt.get_cmap('tab10').colors))
    outputs = []
    # Separate the rate and burst-length sweeps: repeated rates are distinct conditions.
    for metric, ylabel, filename in [
        ('success_rate', 'Exact payload + CRC success probability', 'success_vs_noise'),
        ('goodput_bps', 'Delivered payload goodput (bit/s)', 'goodput_vs_noise'),
    ]:
        fig, axes = plt.subplots(2, 3, figsize=(15, 8), sharex=True, sharey=True)
        for row, depth in enumerate((1, 8)):
            for col, (model, label) in enumerate(zip(models, labels)):
                ax = axes[row, col]
                for codec in config['codecs']:
                    s = data[(data.sweep == 'rate') & (data.model == model) &
                             (data.depth == depth) & (data.codec == codec)].sort_values('rate')
                    prefix = 'success' if metric == 'success_rate' else 'goodput'
                    ax.plot(s.rate, s[metric], 'o-', color=colors[codec], label=codec, markersize=4)
                    ax.fill_between(s.rate, s[prefix+'_ci_low'], s[prefix+'_ci_high'],
                                    color=colors[codec], alpha=.12)
                ax.set_title(f'{label} · depth {depth}')
                ax.set_xlabel('Noise occupancy / flip probability')
                ax.set_ylabel(ylabel)
                ax.grid(alpha=.25)
                ax.set_ylim(bottom=0, top=1.03 if metric == 'success_rate' else None)
        handles, names = axes[0, 0].get_legend_handles_labels()
        fig.legend(handles, names, loc='lower center', ncol=len(names))
        fig.suptitle(f'Controlled synthetic coding study · {config["trials_per_condition"]:,} trials/condition\n'
                     'Shading: 95% Wilson intervals; perfect acquisition/header; framing airtime charged')
        fig.tight_layout(rect=(0, .055, 1, .91))
        for suffix in ('png', 'svg'):
            path = study/f'{filename}.{suffix}'
            fig.savefig(path, dpi=160)
            outputs.append(path.name)
        plt.close(fig)

    # The L=8 reference belongs to the rate sweep; include it in this slice too.
    sensitivity = data[data.rate == .05]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    for ax, model, label in zip(axes, models[1:], labels[1:]):
        for codec in config['codecs']:
            for depth, style in ((1, '--'), (8, '-')):
                s = sensitivity[(sensitivity.model == model) & (sensitivity.codec == codec) &
                                (sensitivity.depth == depth)].sort_values('mean_burst_slots')
                ax.plot(s.mean_burst_slots, s.success_rate, marker='o', linestyle=style,
                        color=colors[codec], label=f'{codec}, depth {depth}')
        ax.set_title(label)
        ax.set_xlabel('Mean burst length (bit slots)')
        ax.set_ylabel('Exact payload + CRC success probability')
        ax.set_ylim(0, 1.03)
        ax.grid(alpha=.25)
    handles, names = axes[0].get_legend_handles_labels()
    fig.legend(handles, names, loc='lower center', ncol=5, fontsize=8)
    fig.suptitle('Burst-length sensitivity · fixed noise occupancy 0.05\nDashed: no interleaving; solid: depth 8')
    fig.tight_layout(rect=(0, .12, 1, .88))
    for suffix in ('png', 'svg'):
        path = study/f'burst_length_sensitivity.{suffix}'
        fig.savefig(path, dpi=160)
        outputs.append(path.name)
    plt.close(fig)
    (study/'graphs.json').write_text(json.dumps(dict(
        files=outputs, source='summary.json',
        interpretation='Synthetic coding evidence, not camera/filter performance. Glare occupancy is not BER. '
                       'Payload success requires exact recovery and CRC. Goodput includes framing and coding overhead. '
                       'Rate and burst-length sweeps are plotted separately.'), indent=2)+'\n')
    return outputs
