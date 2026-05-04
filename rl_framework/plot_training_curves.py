"""
rl_framework/plot_training_curves.py
=====================================
加载多个训练历史文件，绘制训练曲线对比图。

支持的文件格式:
  - .npz (由 train.py --save_history 生成)
  - .csv (第一列 episode, 后续列为指标值)

用法:
    # 对比 CPPO 和 Standard PPO 的奖励曲线
    python plot_training_curves.py \\
        --log_files checkpoints/training_history_cppo.npz \\
                    checkpoints/training_history_std_ppo.npz \\
        --labels CPPO "Standard PPO" --metric reward

    # 对比 SINR 改善，加 Expert 水平线
    python plot_training_curves.py \\
        --log_files hist_cppo.npz hist_std.npz \\
        --metric sinr_improvement --smooth 15 \\
        --expert_value 2.5 --title "SINR Improvement"
"""

import os
import sys
import argparse
import numpy as np

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


# =====================================================================
# 数据加载
# =====================================================================
def load_npz(filepath):
    """从 .npz 文件加载所有数组，返回 dict[str, ndarray]。"""
    data = dict(np.load(filepath, allow_pickle=True))
    return data


def load_csv(filepath):
    """
    从 .csv 文件加载，返回 dict[str, ndarray]。
    要求第一行为 header，第一列为 episode（或 index），其余为指标。
    """
    try:
        data = np.genfromtxt(filepath, delimiter=',', names=True)
        result = {}
        for name in data.dtype.names:
            result[name] = data[name]
        return result
    except Exception:
        # fallback: 无 header，所有列当作指标，index 自增
        raw = np.genfromtxt(filepath, delimiter=',')
        return {'metric': raw}


def load_log(filepath):
    """根据扩展名自动选择加载方式。"""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.npz':
        return load_npz(filepath)
    elif ext == '.csv':
        return load_csv(filepath)
    else:
        raise ValueError(f"Unsupported file format: {ext} (expected .npz or .csv)")


def infer_label(filepath):
    """从文件名推断图例标签。"""
    basename = os.path.basename(filepath)
    name = os.path.splitext(basename)[0]
    # 去掉常见前缀
    for prefix in ('training_history_', 'history_', 'log_'):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name


# =====================================================================
# 平滑
# =====================================================================
def smooth(arr, window):
    """边缘不收缩的移动平均。"""
    arr = np.array(arr, dtype=float)
    if len(arr) < window or window < 2:
        return arr
    kernel = np.ones(window) / window
    padded = np.pad(arr, (window // 2, window - window // 2 - 1), mode='edge')
    return np.convolve(padded, kernel, mode='valid')[:len(arr)]


# =====================================================================
# 绘图
# =====================================================================
def plot_curves(log_data_list, labels, metric, smooth_window, title,
                expert_value=None, output_path='training_curves.png'):
    """
    绘制多条训练曲线对比图。

    参数:
        log_data_list : list[dict]  每个 dict 包含指标名 → ndarray
        labels          : list[str]     图例标签
        metric          : str           要绘制的指标 key
        smooth_window   : int           MA 窗口
        title           : str
        expert_value    : float or None  Expert 水平线
        output_path     : str           保存路径
    """
    fig, ax = plt.subplots(figsize=(10, 5.5))

    colors = ['#e74c3c', '#3498db', '#2ecc71', '#e67e22', '#9b59b6', '#1abc9c']

    for i, (data, label) in enumerate(zip(log_data_list, labels)):
        if metric not in data:
            print(f"[warn] 指标 '{metric}' 不在文件 '{label}' 的数据中，跳过")
            continue

        raw = data[metric]
        if len(raw) == 0:
            print(f"[warn] 指标 '{metric}' 在文件 '{label}' 中为空，跳过")
            continue

        x = np.arange(len(raw))
        color = colors[i % len(colors)]

        # 原始数据（半透明）
        ax.plot(x, raw, alpha=0.2, color=color, lw=0.5)

        # 平滑曲线
        sm = smooth(raw, smooth_window)
        ax.plot(x, sm, color=color, lw=2, label=label)

    # Expert 水平线
    if expert_value is not None:
        ax.axhline(y=expert_value, color='gray', ls='--', lw=1.5,
                   alpha=0.7, label=f'Expert ({expert_value:.2f})')

    ax.set_xlabel('Episode', fontsize=12)
    metric_label = metric.replace('_', ' ').title()
    ax.set_ylabel(metric_label, fontsize=12)
    ax.set_title(title or f'Training Curve: {metric_label}', fontsize=13, fontweight='bold')
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"[plot] 图表已保存: {output_path}")


# =====================================================================
# CLI
# =====================================================================
def main():
    parser = argparse.ArgumentParser(
        description='训练曲线对比绘图',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--log_files', type=str, nargs='+', required=True,
                        help='训练历史文件路径 (.npz 或 .csv)')
    parser.add_argument('--labels', type=str, nargs='*', default=None,
                        help='图例标签（与 log_files 一一对应，默认从文件名推断）')
    parser.add_argument('--metric', type=str, default='reward',
                        help='要绘制的指标名称 (reward / sinr_improvement / detect_rate / actor_loss / critic_loss)')
    parser.add_argument('--smooth', type=int, default=10,
                        help='移动平均窗口大小')
    parser.add_argument('--output', type=str, default='training_curves.png',
                        help='输出图片路径')
    parser.add_argument('--title', type=str, default=None,
                        help='图表标题')
    parser.add_argument('--expert_value', type=float, default=None,
                        help='Expert 策略的固定性能水平（绘制水平虚线）')
    args = parser.parse_args()

    # 加载数据
    log_data_list = []
    labels = args.labels if args.labels else []

    for fpath in args.log_files:
        if not os.path.isfile(fpath):
            print(f"[warn] 文件不存在，跳过: {fpath}")
            continue
        try:
            data = load_log(fpath)
            log_data_list.append(data)
            if len(labels) < len(log_data_list):
                labels.append(infer_label(fpath))
            print(f"[load] {fpath}  指标: {list(data.keys())}")
        except Exception as e:
            print(f"[error] 加载失败 {fpath}: {e}")

    if not log_data_list:
        print("[error] 无可用数据，退出")
        sys.exit(1)

    # 确保平滑窗口不超过数据长度
    max_len = max(len(d.get(args.metric, [])) for d in log_data_list)
    smooth_win = min(args.smooth, max_len) if max_len > 0 else args.smooth
    smooth_win = max(2, smooth_win)  # 至少 2

    plot_curves(
        log_data_list=log_data_list,
        labels=labels,
        metric=args.metric,
        smooth_window=smooth_win,
        title=args.title,
        expert_value=args.expert_value,
        output_path=args.output,
    )


if __name__ == '__main__':
    main()
