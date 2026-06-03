from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd
from typing import Any

from .stages import Stage, CutoffStage, FilterStage, RateStage
from .stress import StressScenario, AggravationStress

@dataclass(frozen=True)
class CreditPolicy:
    """Configuration for a credit policy simulation.
    
    This class is immutable. Methods like `add_stage` and `add_stress` return 
    a new instance of CreditPolicy rather than modifying the current one.
    """
    applicant_id_col: str
    score_cols: tuple[str, ...]
    current_approval_col: str
    actual_default_col: str
    conversion_rate_col: str | None = None
    pd_col: str | None = None
    time_col: str | None = None
    stages: tuple[Stage, ...] = field(default_factory=tuple)
    stress_scenarios: tuple[StressScenario, ...] = field(default_factory=tuple)
    
    def __post_init__(self) -> None:
        # Coerce score_cols to tuple of strings
        if isinstance(self.score_cols, str):
            score_tuple = (self.score_cols,)
        else:
            try:
                score_tuple = tuple(self.score_cols)
            except TypeError:
                score_tuple = (str(self.score_cols),)
        
        object.__setattr__(self, "score_cols", score_tuple)
        
        # Ensure stages and stress_scenarios are also tuples
        if not isinstance(self.stages, tuple):
            object.__setattr__(self, "stages", tuple(self.stages))
        if not isinstance(self.stress_scenarios, tuple):
            object.__setattr__(self, "stress_scenarios", tuple(self.stress_scenarios))

    def add_stage(self, stage: Stage) -> CreditPolicy:
        """Return a new CreditPolicy with the given stage appended."""
        new_stages = self.stages + (stage,)
        return self._replace(stages=new_stages)
        
    def add_stress(self, scenario: StressScenario) -> CreditPolicy:
        """Return a new CreditPolicy with the given stress scenario appended."""
        new_scenarios = self.stress_scenarios + (scenario,)
        return self._replace(stress_scenarios=new_scenarios)
        
    def _replace(self, **kwargs) -> CreditPolicy:
        """Helper to create a new instance with replaced fields."""
        import dataclasses
        return dataclasses.replace(self, **kwargs)

    # --- Fluid Builder Methods ---
    
    def cutoff(self, name: str, cutoffs: dict[str, float], direction: str = "gte") -> CreditPolicy:
        """Add a CutoffStage to the policy."""
        return self.add_stage(CutoffStage(name=name, cutoffs=cutoffs, direction=direction))
        
    def filter(self, name: str, condition: Any) -> CreditPolicy:
        """Add a FilterStage to the policy. Condition can be an Expression, callable, or string."""
        return self.add_stage(FilterStage(name=name, condition=condition))
        
    def rate(self, name: str, base_rate: float, variable: str | float | None = None) -> CreditPolicy:
        """Add a RateStage to the policy."""
        return self.add_stage(RateStage(name=name, base_rate=base_rate, variable=variable))
        
    def stress_aggravation(self, factor: float) -> CreditPolicy:
        """Add an AggravationStress scenario."""
        return self.add_stress(AggravationStress(factor=factor))
        
    def simulate(self, df: pd.DataFrame, method: str = "analytical") -> Any:
        """Run simulation directly from the policy object.
        
        Args:
            df: The applicant data.
            method: "analytical" or "stochastic".
            
        Returns:
            CreditSimResults object.
        """
        from .simulation import run_simulation, SimulationMethod
        sim_method = SimulationMethod.ANALYTICAL if method == "analytical" else SimulationMethod.STOCHASTIC
        return run_simulation(df, self, method=sim_method)
        
    def validate(self, df: pd.DataFrame) -> None:
        """Validate that the policy can be run on the given DataFrame.
        
        Raises:
            ValueError: If required columns are missing.
        """
        required_cols = list(self.score_cols) + [
            self.applicant_id_col,
            self.current_approval_col,
            self.actual_default_col,
        ]
        
        # Add columns from stages
        from .stages import CutoffStage, FilterStage
        from .expressions import Expression
        for stage in self.stages:
            if isinstance(stage, CutoffStage):
                required_cols.extend(stage.cutoffs.keys())
            elif isinstance(stage, FilterStage) and isinstance(stage.condition, Expression):
                required_cols.extend(stage.condition.get_columns())
                
        # We don't strictly require pd_col or conversion_rate_col unless they are 
        # specifically used, but if they are defined, they should probably exist.
        if self.conversion_rate_col is not None:
            required_cols.append(self.conversion_rate_col)
        if self.pd_col is not None:
            required_cols.append(self.pd_col)
        if self.time_col is not None:
            required_cols.append(self.time_col)
            
        required_cols = list(set(required_cols))  # deduplicate
        missing = [c for c in required_cols if c not in df.columns]
        
        if missing:
            raise ValueError(f"Missing required columns in data: {missing}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the policy to a dictionary."""
        return {
            "applicant_id_col": self.applicant_id_col,
            "score_cols": self.score_cols,
            "current_approval_col": self.current_approval_col,
            "actual_default_col": self.actual_default_col,
            "conversion_rate_col": self.conversion_rate_col,
            "pd_col": self.pd_col,
            "time_col": self.time_col,
            "stages": [s.to_dict() for s in self.stages],
            "stress_scenarios": [s.to_dict() for s in self.stress_scenarios],
        }
        
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CreditPolicy:
        """Deserialize a dictionary to a CreditPolicy object."""
        stages = tuple(Stage.from_dict(s) for s in d.get("stages", []))
        stress_scenarios = tuple(StressScenario.from_dict(s) for s in d.get("stress_scenarios", []))
        
        return cls(
            applicant_id_col=d["applicant_id_col"],
            score_cols=d["score_cols"],
            current_approval_col=d["current_approval_col"],
            actual_default_col=d["actual_default_col"],
            conversion_rate_col=d.get("conversion_rate_col"),
            pd_col=d.get("pd_col"),
            time_col=d.get("time_col"),
            stages=stages,
            stress_scenarios=stress_scenarios,
        )
        
    def describe(self) -> str:
        """Return a human-readable description of the policy."""
        lines = [
            "CreditPolicy:",
            f"  Applicant ID: {self.applicant_id_col}",
            f"  Score columns: {', '.join(self.score_cols)}",
            f"  Current approval: {self.current_approval_col}",
            f"  Actual default: {self.actual_default_col}",
        ]
        
        if self.conversion_rate_col:
            lines.append(f"  Conversion rate column: {self.conversion_rate_col}")
            
        if self.stages:
            lines.append("  Stages:")
            for i, stage in enumerate(self.stages, 1):
                lines.append(f"    {i}. {stage.name} ({stage.__class__.__name__})")
        else:
            lines.append("  Stages: None")
            
        if self.stress_scenarios:
            lines.append("  Stress Scenarios:")
            for i, scenario in enumerate(self.stress_scenarios, 1):
                lines.append(f"    {i}. {scenario.__class__.__name__}")
        else:
            lines.append("  Stress Scenarios: None")
            
        return "\n".join(lines)
        
    def export(
        self,
        rating_recipe: Any | None = None,
        path: str | None = None,
    ) -> Any:
        """Export this policy and an optional rating recipe for deployment.
        
        Args:
            rating_recipe: Optional GroupingRecipe.
            path: Optional file path to save the deployment JSON file.
            
        Returns:
            DeploymentPolicy instance.
        """
        from .deployment import DeploymentPolicy
        dep = DeploymentPolicy(policy=self, rating_recipe=rating_recipe)
        if path is not None:
            dep.save(path)
        return dep
