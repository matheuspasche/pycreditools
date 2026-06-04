"""
pycreditools: A Python library for credit risk policy simulation and analysis.
"""

from . import examples
from ._types import ClusteringMethod, PolicySummary, Quadrant, SimulationMethod, StageDirection
from .analysis import TradeoffAnalyzer, run_tradeoff_analysis
from .deployment import DeploymentPolicy
from .expressions import Expression, col
from .grouping import GroupingRecipe, RiskGroupResult, fit_risk_groups, fit_pairwise_risk_groups, find_risk_groups
from .optimization import (
    OptimizationResult,
    optimize_cutoffs,
)
from .performance import (
    ModelEvaluator,
    compare_policies,
    print_delta_table,
    print_quadrant_summary,
    print_rating_quadrant_table,
    print_swap_in_by_rating,
    summarize_results,
)
from .policy import CreditPolicy
from .sample_data import generate_sample_data
from .screening import ScreeningRecipe, ScreeningResult, fit_risk_segments, screen_risk_segments
from .simulation import CreditSimResults, run_simulation
from .stages import CutoffStage, FilterStage, RateStage, Stage, register_callable
from .stress import AggravationStress, CustomStress, MonotonicStress, StressScenario
from .visualization import (
    plot_crash_test,
    plot_tradeoffs,
    plot_vintage_stability,
    plot_optimization,
    visualize_tradeoffs,
)

__all__ = [
    "SimulationMethod",
    "ClusteringMethod",
    "Quadrant",
    "StageDirection",
    "PolicySummary",
    "Stage",
    "CutoffStage",
    "FilterStage",
    "RateStage",
    "register_callable",
    "StressScenario",
    "AggravationStress",
    "MonotonicStress",
    "CustomStress",
    "CreditPolicy",
    "CreditSimResults",
    "run_simulation",
    "DeploymentPolicy",
    "summarize_results",
    "compare_policies",
    "print_delta_table",
    "print_quadrant_summary",
    "print_swap_in_by_rating",
    "print_rating_quadrant_table",
    "plot_tradeoffs",
    "plot_vintage_stability",
    "plot_crash_test",
    "run_tradeoff_analysis",
    "fit_risk_groups",
    "find_risk_groups",
    "RiskGroupResult",
    "GroupingRecipe",
    "fit_pairwise_risk_groups",
    "fit_risk_segments",
    "screen_risk_segments",
    "ScreeningResult",
    "ScreeningRecipe",
    "generate_sample_data",
    "col",
    "Expression",
    "TradeoffAnalyzer",
    "ModelEvaluator",
    "optimize_cutoffs",
    "OptimizationResult",
    "plot_optimization",
    "visualize_tradeoffs",
    "examples",
]
