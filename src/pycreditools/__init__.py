"""
pycreditools: A Python library for credit risk policy simulation and analysis.
"""

from ._types import SimulationMethod, ClusteringMethod, Quadrant, StageDirection, PolicySummary
from .stages import Stage, CutoffStage, FilterStage, RateStage
from .stress import StressScenario, AggravationStress, MonotonicStress, CustomStress
from .policy import CreditPolicy
from .simulation import CreditSimResults, run_simulation
from .performance import (
    summarize_results,
    compare_policies,
    ModelEvaluator,
    print_delta_table,
    print_quadrant_summary,
    print_swap_in_by_rating,
    print_rating_quadrant_table,
)
from .analysis import run_tradeoff_analysis, TradeoffAnalyzer
from .grouping import find_risk_groups, RiskGroupResult, GroupingRecipe
from .screening import screen_risk_segments, ScreeningResult, ScreeningRecipe
from .sample_data import generate_sample_data
from .visualization import plot_tradeoffs, plot_vintage_stability, plot_crash_test
from .expressions import col, Expression
from . import examples

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
    "StressScenario",
    "AggravationStress",
    "MonotonicStress",
    "CustomStress",
    "CreditPolicy",
    "CreditSimResults",
    "run_simulation",
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
    "find_risk_groups",
    "RiskGroupResult",
    "GroupingRecipe",
    "screen_risk_segments",
    "ScreeningResult",
    "ScreeningRecipe",
    "generate_sample_data",
    "col",
    "Expression",
    "TradeoffAnalyzer",
    "ModelEvaluator",
    "examples",
]
