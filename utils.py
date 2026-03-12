"""Visualization utilities for flow field prediction."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
from pathlib import Path

OUT_DIR = Path("plots")
POINT_SIZE = 0.5  # scatter marker size
QUIVER_STRIDE = 50  # plot every Nth point as arrow


def _add_quiver(ax, px, py, ux, uy, stride=QUIVER_STRIDE):
    """Add velocity arrows to an axes, subsampled for clarity."""
    ax.quiver(px[::stride], py[::stride], ux[::stride], uy[::stride],
              angles="xy", scale_units="xy", scale=150, width=0.002,
              color="k", alpha=0.4, headwidth=3)


def _setup_ax(ax, x_lo, x_hi, y_lo, y_hi, surf_pos):
    """Common axis setup."""
    ax.set_aspect("equal")
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(y_lo, y_hi)
    ax.plot(surf_pos[:, 0], surf_pos[:, 1], "k.", markersize=0.3)


def _get_view_bounds(pos, surf_pos):
    """Compute standard view bounds."""
    x_lo, x_hi = -1.0, 2.0
    y_lo = max(0.0, pos[:, 1].min())
    y_hi = min(surf_pos[:, 1].mean() + 3.0, pos[:, 1].max())
    near = (
        (pos[:, 0] >= x_lo) & (pos[:, 0] <= x_hi) &
        (pos[:, 1] >= y_lo) & (pos[:, 1] <= y_hi)
    )
    return x_lo, x_hi, y_lo, y_hi, near


def _scatter_field(ax, fig, px, py, vals, cmap="viridis", vmin=None, vmax=None):
    """Plot a scalar field as a scatter plot."""
    sc = ax.scatter(px, py, c=vals, s=POINT_SIZE, cmap=cmap, vmin=vmin, vmax=vmax,
                    edgecolors="none", rasterized=True)
    fig.colorbar(sc, ax=ax)
    return sc


def plot_samples(dataset, indices=None, n_samples=4, prefix="data_sample", out_dir=None):
    """Plot ground truth flow fields: velocity magnitude + arrows, and pressure."""
    out_dir = Path(out_dir) if out_dir else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    if indices is None:
        indices = list(range(min(n_samples, len(dataset))))

    for i, idx in enumerate(indices):
        x, y_true, is_surface = dataset[idx]
        pos = x[:, :2].numpy()
        y_np = y_true.numpy()
        is_surf_np = is_surface.numpy()
        surf_pos = pos[is_surf_np]

        x_lo, x_hi, y_lo, y_hi, near = _get_view_bounds(pos, surf_pos)
        px, py = pos[near, 0], pos[near, 1]

        ux, uy, p_field = y_np[near, 0], y_np[near, 1], y_np[near, 2]
        vmag = np.sqrt(ux**2 + uy**2)

        fig, axes = plt.subplots(1, 2, figsize=(16, 6))
        fig.suptitle(f"Sample {idx}", fontsize=14)

        # Velocity magnitude + arrows
        _scatter_field(axes[0], fig, px, py, vmag, cmap="viridis")
        axes[0].set_title("|U| (velocity magnitude)")
        _add_quiver(axes[0], px, py, ux, uy)
        _setup_ax(axes[0], x_lo, x_hi, y_lo, y_hi, surf_pos)

        # Pressure
        _scatter_field(axes[1], fig, px, py, p_field, cmap="RdBu_r")
        axes[1].set_title("p (pressure)")
        _setup_ax(axes[1], x_lo, x_hi, y_lo, y_hi, surf_pos)

        plt.tight_layout()
        path = out_dir / f"{prefix}_{idx}.png"
        fig.savefig(path, dpi=200)
        plt.close(fig)
        saved.append(path)
        print(f"  Saved {path}")

    return saved


def visualize(model, val_ds, stats, device, n_samples=4, out_dir=None):
    """Generate flow field comparison plots: velocity (magnitude+arrows) and pressure.

    Layout: 2 rows (velocity, pressure) x 3 cols (GT, Predicted, Error).
    """
    out_dir = Path(out_dir) if out_dir else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    model.eval()
    saved = []

    indices = list(range(min(n_samples, len(val_ds))))
    for sample_idx in indices:
        x, y_true, is_surface = val_ds[sample_idx]

        with torch.no_grad():
            x_dev = x.unsqueeze(0).to(device)
            x_norm = (x_dev - stats["x_mean"]) / stats["x_std"]
            pred_norm = model({"x": x_norm})["preds"]
            y_pred = (pred_norm * stats["y_std"] + stats["y_mean"]).squeeze(0).cpu()

        pos = x[:, :2].numpy()
        y_true_np = y_true.numpy()
        y_pred_np = y_pred.numpy()
        is_surf_np = is_surface.numpy()

        surf_pos = pos[is_surf_np]
        x_lo, x_hi, y_lo, y_hi, near = _get_view_bounds(pos, surf_pos)
        px, py = pos[near, 0], pos[near, 1]

        gt_ux, gt_uy, gt_p = y_true_np[near, 0], y_true_np[near, 1], y_true_np[near, 2]
        pr_ux, pr_uy, pr_p = y_pred_np[near, 0], y_pred_np[near, 1], y_pred_np[near, 2]
        gt_vmag = np.sqrt(gt_ux**2 + gt_uy**2)
        pr_vmag = np.sqrt(pr_ux**2 + pr_uy**2)
        err_vmag = gt_vmag - pr_vmag
        err_p = gt_p - pr_p

        fig, axes = plt.subplots(2, 3, figsize=(20, 10))
        fig.suptitle(f"Validation sample {sample_idx}", fontsize=14)

        # Row 0: Velocity magnitude
        vmin_v, vmax_v = gt_vmag.min(), gt_vmag.max()
        _scatter_field(axes[0, 0], fig, px, py, gt_vmag, cmap="viridis", vmin=vmin_v, vmax=vmax_v)
        axes[0, 0].set_title("|U| — Ground Truth")
        _add_quiver(axes[0, 0], px, py, gt_ux, gt_uy)

        _scatter_field(axes[0, 1], fig, px, py, pr_vmag, cmap="viridis", vmin=vmin_v, vmax=vmax_v)
        axes[0, 1].set_title("|U| — Predicted")
        _add_quiver(axes[0, 1], px, py, pr_ux, pr_uy)

        err_v_max = max(abs(err_vmag.min()), abs(err_vmag.max()), 1e-6)
        _scatter_field(axes[0, 2], fig, px, py, err_vmag, cmap="RdBu_r", vmin=-err_v_max, vmax=err_v_max)
        axes[0, 2].set_title("|U| — Error")

        # Row 1: Pressure
        vmin_p, vmax_p = gt_p.min(), gt_p.max()
        _scatter_field(axes[1, 0], fig, px, py, gt_p, cmap="RdBu_r", vmin=vmin_p, vmax=vmax_p)
        axes[1, 0].set_title("p — Ground Truth")

        _scatter_field(axes[1, 1], fig, px, py, pr_p, cmap="RdBu_r", vmin=vmin_p, vmax=vmax_p)
        axes[1, 1].set_title("p — Predicted")

        err_p_max = max(abs(err_p.min()), abs(err_p.max()), 1e-6)
        _scatter_field(axes[1, 2], fig, px, py, err_p, cmap="RdBu_r", vmin=-err_p_max, vmax=err_p_max)
        axes[1, 2].set_title("p — Error")

        for ax in axes.flat:
            _setup_ax(ax, x_lo, x_hi, y_lo, y_hi, surf_pos)

        plt.tight_layout()
        path = out_dir / f"val_sample_{sample_idx}.png"
        fig.savefig(path, dpi=200)
        plt.close(fig)
        saved.append(path)
        print(f"  Saved {path}")

    return saved
