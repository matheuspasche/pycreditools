"""
Visualization functions for credit risk policy analysis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .simulation import CreditSimResults

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


def plot_tradeoffs(
    tradeoff_df: pd.DataFrame,
    legacy_approval_rate: float | None = None,
    legacy_bad_rate: float | None = None,
    title: str = "Fronteira Eficiente (Stressed & Approved)",
    x_col: str = "approval_rate",
    y_col: str = "default_rate",
    hue_col: str | None = "Score_Model",
    save_path: str | None = None,
) -> plt.Figure:
    """Plot the tradeoff efficient frontier curve(s).

    Args:
        tradeoff_df: DataFrame with tradeoff simulation results.
        legacy_approval_rate: Optional baseline/legacy approval rate to plot.
        legacy_bad_rate: Optional baseline/legacy bad rate to plot.
        title: Title of the plot.
        x_col: Column for X axis (e.g., 'approval_rate').
        y_col: Column for Y axis (e.g., 'default_rate').
        hue_col: Column to group/color curves by.
        save_path: Path to save the generated image.
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    # Plot curves
    if hue_col and hue_col in tradeoff_df.columns:
        sns.lineplot(data=tradeoff_df, x=x_col, y=y_col, hue=hue_col, marker="o", lw=2.0, ax=ax)
    else:
        sns.lineplot(
            data=tradeoff_df, x=x_col, y=y_col, marker="o", color="royalblue", lw=2.0, ax=ax
        )

    # Legacy indicators
    if legacy_bad_rate is not None:
        ax.axhline(
            y=legacy_bad_rate,
            color="red",
            linestyle="--",
            linewidth=1.5,
            label=f"Inad. Legada (Aprovados) ({legacy_bad_rate:.1%})",
        )
    if legacy_approval_rate is not None:
        ax.axvline(
            x=legacy_approval_rate,
            color="green",
            linestyle="--",
            linewidth=1.5,
            label=f"Taxa de Aprovação Legada ({legacy_approval_rate:.1%})",
        )
    if legacy_approval_rate is not None and legacy_bad_rate is not None:
        ax.scatter(
            legacy_approval_rate,
            legacy_bad_rate,
            color="black",
            s=180,
            marker="X",
            zorder=10,
            label="Política Legada (Aprovados)",
        )

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel("Taxa de Aprovação Global (% do ToF)")
    ax.set_ylabel("Inad. Aprovados Projetada")

    # Format axes as percentage
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.1%}"))

    ax.grid(True, linestyle=":", alpha=0.7)
    ax.legend()
    plt.tight_layout()

    if save_path:
        import os

        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        plt.savefig(save_path, dpi=150)

    return fig


def plot_vintage_stability(
    df: pd.DataFrame,
    rating_col: str = "Rating",
    time_col: str = "safra",
    default_col: str = "actual_default",
    approval_col: str = "new_approval",
    oot_start_safra: str | None = "2025-01",
    title: str = "Estabilidade dos Ratings por Safra (DEV vs OOT)",
    save_path: str | None = None,
) -> plt.Figure:
    """Plot default rates over time (vintages) grouped by rating.

    Args:
        df: DataFrame containing the applicants and simulation outputs.
        rating_col: Column containing risk rating.
        time_col: Column containing safra (vintage format like 'YYYY-MM').
        default_col: Column containing observed default outcome (0/1).
        approval_col: Column containing approval outcome (0 or 1, or probability).
        oot_start_safra: Safra marking the beginning of the Out-Of-Time period.
        title: Plot title.
        save_path: Path to save the generated image.
    """
    fig, ax = plt.subplots(figsize=(12, 5))

    # Filter for approved cases only (where approval is > 0)
    approved_df = df[df[approval_col] > 0.0].copy()

    # Calculate bad rate by safra and rating
    sfp = approved_df.pivot_table(
        index=time_col, columns=rating_col, values=default_col, aggfunc="mean"
    )

    # Sort columns (ratings) so that they display nicely
    sorted_cols = sorted(sfp.columns)

    for r in sorted_cols:
        ax.plot(sfp.index, sfp[r] * 100.0, marker="o", lw=2, label=f"Rating {r}")

    if oot_start_safra:
        # Draw vertical line
        try:
            ax.axvline(
                x=oot_start_safra, color="red", linestyle="--", lw=2, label="Divisor DEV/OOT"
            )
        except Exception:
            pass

        # Add labels
        ylim = ax.get_ylim()
        y_text = ylim[1] * 0.85

        try:
            idx_list = list(sfp.index)
            if oot_start_safra in idx_list:
                pos = idx_list.index(oot_start_safra)
                dev_label_pos = idx_list[max(0, pos // 2)]
                oot_label_pos = idx_list[min(len(idx_list) - 1, pos + (len(idx_list) - pos) // 2)]
                ax.text(
                    dev_label_pos,
                    y_text,
                    "Desenvolvimento (DEV)",
                    color="blue",
                    fontsize=11,
                    fontweight="bold",
                    ha="center",
                )
                ax.text(
                    oot_label_pos,
                    y_text,
                    "Fora do Tempo (OOT)",
                    color="red",
                    fontsize=11,
                    fontweight="bold",
                    ha="center",
                )
            else:
                pos = len(idx_list) // 2
                ax.text(
                    idx_list[max(0, pos - 2)],
                    y_text,
                    "Desenvolvimento (DEV)",
                    color="blue",
                    fontsize=11,
                    fontweight="bold",
                    ha="center",
                )
                ax.text(
                    idx_list[min(len(idx_list) - 1, pos + 2)],
                    y_text,
                    "Fora do Tempo (OOT)",
                    color="red",
                    fontsize=11,
                    fontweight="bold",
                    ha="center",
                )
        except Exception:
            pass

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel("Safra")
    ax.set_ylabel("Bad Rate (%)")

    plt.xticks(rotation=45)
    ax.grid(True, linestyle="--", alpha=0.6)
    ax.legend(title=rating_col, loc="upper left")
    plt.tight_layout()

    if save_path:
        import os

        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        plt.savefig(save_path, dpi=150)

    return fig


def plot_crash_test(
    crash_df: pd.DataFrame,
    legacy_bad_rate: float,
    breakeven_factor: float | None = None,
    title: str = "Crash Test: Resiliência da Nova Política",
    save_path: str | None = None,
) -> plt.Figure:
    """Plot the crash test results showing bad rate as aggravation factor increases.

    Args:
        crash_df: DataFrame containing tradeoff analysis over aggravation factors.
                  Must have columns 'aggravation_factor' and 'default_rate'.
        legacy_bad_rate: Baseline/legacy bad rate to plot.
        breakeven_factor: Aggravation factor where bad rate matches legacy bad rate.
        title: Plot title.
        save_path: Path to save the generated image.
    """
    fig, ax = plt.subplots(figsize=(10, 5))

    ax.plot(
        crash_df["aggravation_factor"],
        crash_df["default_rate"] * 100.0,
        color="royalblue",
        lw=2,
        label="Bad Rate Nova Política",
    )

    ax.axhline(
        y=legacy_bad_rate * 100.0,
        color="red",
        linestyle="--",
        lw=1.5,
        label=f"Bad Rate Legada ({legacy_bad_rate:.2%})",
    )

    if breakeven_factor is not None:
        ax.axvline(
            x=breakeven_factor,
            color="orange",
            linestyle=":",
            lw=2,
            label=f"Breakeven ({breakeven_factor:.2f}×)",
        )

    ax.set_xlabel("Fator de Agravamento Swap In (×)")
    ax.set_ylabel("Bad Rate Contratado (%)")
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.grid(True, linestyle=":", alpha=0.7)
    ax.legend()
    plt.tight_layout()

    if save_path:
        import os

        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        plt.savefig(save_path, dpi=150)

    return fig


def plot_optimization(
    opt_results: Any,
    type: str = "tradeoff",
    save_path: str | None = None,
) -> plt.Figure:
    """Visualize tradeoffs between approval rate and default rate.

    Args:
        opt_results: OptimizationResult from find_optimal_cutoffs.
        type: "tradeoff" (all points) or "pareto" (only Pareto frontier and optimal point).
        save_path: Path to save the plot.

    Returns:
        plt.Figure object.
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    all_res = opt_results.all_results
    pareto_res = opt_results.pareto_frontier

    opt_app = opt_results.metrics["overall_approval_rate"]
    opt_def = opt_results.metrics["overall_default_rate"]

    if type == "tradeoff":
        # All evaluated points in gray
        ax.scatter(
            all_res["overall_approval_rate"] * 100.0,
            all_res["overall_default_rate"] * 100.0,
            alpha=0.5,
            color="grey",
            label="Grid Combinations",
        )

        # Plot optimal point as red diamond
        ax.scatter(
            opt_app * 100.0,
            opt_def * 100.0,
            color="red",
            s=150,
            marker="D",
            zorder=10,
            label=f"Optimal Point ({opt_app:.1%}, {opt_def:.2%})",
        )

        ax.set_title("Approval vs. Default Rate Trade-off", fontsize=14, fontweight="bold")

    else:
        # Pareto Frontier plot
        ax.scatter(
            all_res["overall_approval_rate"] * 100.0,
            all_res["overall_default_rate"] * 100.0,
            alpha=0.2,
            color="grey",
            label="Grid Combinations",
        )

        # Pareto frontier as a blue line with markers
        sorted_pareto = pareto_res.sort_values("overall_approval_rate")
        ax.plot(
            sorted_pareto["overall_approval_rate"] * 100.0,
            sorted_pareto["overall_default_rate"] * 100.0,
            color="blue",
            lw=2.5,
            marker="o",
            label="Pareto Efficient Frontier",
        )

        # Plot optimal point as red diamond
        ax.scatter(
            opt_app * 100.0,
            opt_def * 100.0,
            color="red",
            s=150,
            marker="D",
            zorder=10,
            label=f"Optimal Point ({opt_app:.1%}, {opt_def:.2%})",
        )

        ax.set_title("Pareto Frontier of Optimal Solutions", fontsize=14, fontweight="bold")

    ax.set_xlabel("Overall Approval Rate (%)")
    ax.set_ylabel("Overall Default Rate (%)")
    ax.grid(True, linestyle=":", alpha=0.7)
    ax.legend(loc="upper left")
    plt.tight_layout()

    if save_path:
        import os

        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        plt.savefig(save_path, dpi=150)

    return fig


def visualize_tradeoffs(*args, **kwargs) -> plt.Figure:
    """Deprecated alias for plot_optimization."""
    import warnings
    warnings.warn(
        "visualize_tradeoffs is deprecated and will be removed in a future version. "
        "Use plot_optimization instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return plot_optimization(*args, **kwargs)


def plot_funnel(sim_results: CreditSimResults) -> go.Figure:
    """Create a decision funnel visualization using a Plotly Sankey diagram.

    Args:
        sim_results: Results of the credit policy simulation.

    Returns:
        A plotly.graph_objects.Figure.
    """
    try:
        import plotly.graph_objects as go
    except ImportError:
        raise ImportError(
            "Plotly is required for plot_funnel. Please install it using "
            "'pip install plotly' or install pycreditools with the [viz] extra."
        )

    # Policy Extraction
    pol = sim_results.policy
    if pol is None:
        policy_dict = sim_results.metadata.get("policy")
        if policy_dict:
            from .policy import CreditPolicy
            try:
                pol = CreditPolicy.from_dict(policy_dict)
            except Exception:
                pass
        if pol is None:
            raise ValueError("No policy reference found in simulation results to extract hard filters.")

    # Hard Stage Extraction
    from .stages import RateStage
    hard_stages = [stage for stage in pol.stages if not isinstance(stage, RateStage)]
    H = len(hard_stages)

    # Data Verification
    if "reason" not in sim_results.data.columns:
        raise ValueError(
            "The 'reason' column is missing from simulation results. "
            "Please ensure the simulation was run and calculated decision reasons."
        )

    # Node Count Calculations
    N_total = len(sim_results.data)
    
    # Calculate R (rejected) and P (passed) for each stage
    R = []
    for i, stage in enumerate(hard_stages):
        fail_label = f"{i + 1}: {stage.name}"
        R.append((sim_results.data["reason"] == fail_label).sum())

    P = []
    total_approved = (sim_results.data["reason"] == "Approved").sum()
    for i in range(H):
        p_count = total_approved + sum(R[j] for j in range(i + 1, H))
        P.append(p_count)

    V_rejected = sum(R)
    V_approved = P[H - 1] if H > 0 else N_total

    # Sankey Node Mapping
    labels = [
        f"<b>Total</b><br><span style='font-size: 10px; color: #64748b;'>{N_total:,} (100.0%)</span>"
    ]
    node_colors = ["#475569"]  # Slate-600

    for i in range(H):
        passed_pct = P[i] / N_total if N_total > 0 else 0.0
        labels.append(
            f"<b>{i + 1}: {hard_stages[i].name}</b><br><span style='font-size: 10px; color: #64748b;'>{P[i]:,.0f} ({passed_pct:.1%})</span>"
        )
        node_colors.append("#6366f1")  # Indigo-500

    approved_pct = V_approved / N_total if N_total > 0 else 0.0
    labels.append(
        f"<b>Approved</b><br><span style='font-size: 10px; color: #047857;'>{V_approved:,.0f} ({approved_pct:.1%})</span>"
    )
    node_colors.append("#10b981")  # Emerald-500

    # Sankey Link Calculations
    sources = []
    targets = []
    values = []
    link_colors = []

    def add_link(src, tgt, val, col):
        if val > 0:
            sources.append(src)
            targets.append(tgt)
            values.append(val)
            link_colors.append(col)

    if H == 0:
        add_link(0, 1, N_total, "rgba(16, 185, 129, 0.2)")
    else:
        # Total to Stage 0
        add_link(0, 1, P[0], "rgba(99, 102, 241, 0.15)")

        for i in range(1, H):
            # Stage i-1 to Stage i
            add_link(i, i + 1, P[i], "rgba(99, 102, 241, 0.15)")

        # Last Stage to Approved
        add_link(H, H + 1, V_approved, "rgba(16, 185, 129, 0.2)")

    # Build the figure
    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=18,
            thickness=25,
            line=dict(color="rgba(0,0,0,0)", width=0),
            label=labels,
            color=node_colors
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=link_colors
        )
    )])

    fig.update_layout(
        title=dict(
            text="<b>Credit Policy Decision Funnel</b>",
            font=dict(size=18, color="#1e293b", family="Outfit, Inter, sans-serif"),
            y=0.95
        ),
        font_size=11,
        font_family="Inter, sans-serif",
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=40, r=40, t=60, b=40),
        hoverlabel=dict(
            bgcolor="white",
            bordercolor="#e2e8f0",
            font_size=12,
            font_family="Inter, sans-serif"
        )
    )

    return fig

