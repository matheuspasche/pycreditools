# PRD 01 — App Shell & Design System

> Foundation task. No dependency on other pages. Produces the theme, the
> navigation shell, the session-state module and the reusable components every
> other page imports. See Master (PRD 00) §4, §6, §7, §9.

## Objective

Stand up the Streamlit app skeleton with a polished **dark fintech** look, the
sidebar navigation, the shared `state.py`, and the `components/` + `theme.py`
helpers — so pages 02–11 only have to fill in content.

## Deliverables

1. `src/pycreditools/gui/app.py` — entrypoint.
2. `src/pycreditools/gui/__init__.py` — `run_studio()`.
3. `src/pycreditools/gui/theme.py` — `apply_theme()` + Plotly template `pct_dark`.
4. `src/pycreditools/gui/assets/studio.css`.
5. `.streamlit/config.toml` — dark theme tokens.
6. `src/pycreditools/gui/state.py` — `StudioState`, `get_state`, `guard_dataset`,
   `guard_roles`, `require_policy`.
7. `src/pycreditools/gui/components/{__init__,kpi,tables,charts}.py` — themed primitives.
8. `pyproject.toml` updates: add `studio` extra + `[project.scripts]`, remove `gui` Dash extra.
9. Delete the old Dash app (see PRD 00 §4 "Delete" list).

## Details

### `app.py`
```python
import streamlit as st
from .theme import apply_theme
from .state import init_state

st.set_page_config(page_title="Pycreditools Studio", page_icon="📊", layout="wide")
apply_theme()
init_state()

pages = [
    st.Page("pages/1_Ingestion.py", title="Ingestão", icon="📥"),
    st.Page("pages/2_Score_Evaluation.py", title="Avaliação de Score", icon="📈"),
    st.Page("pages/3_Policy_Studio.py", title="Policy Studio", icon="🧱"),
    st.Page("pages/4_Simulation.py", title="Simulação", icon="🧪"),
    st.Page("pages/5_Tradeoff.py", title="Trade-off", icon="⚖️"),
    st.Page("pages/6_Optimization.py", title="Otimização", icon="🎯"),
    st.Page("pages/7_Risk_Grouping.py", title="Risk Grouping", icon="🗂️"),
    st.Page("pages/8_Risk_Screening.py", title="Screening", icon="🔬"),
    st.Page("pages/9_Crash_Test.py", title="Crash Test", icon="💥"),
    st.Page("pages/10_Deployment.py", title="Deploy & Scoring", icon="🚀"),
]
nav = st.navigation(pages, position="sidebar")
render_sidebar_context()   # dataset name + row count + active policy
nav.run()
```
- `render_sidebar_context()` (in `state.py` or a small `components/sidebar.py`)
  shows, in `st.sidebar`: app title/logo, a divider, then "Base: `{df_name}` ·
  `{n:,} linhas`" and "Política ativa: `{active_policy or '—'}`". Muted text.

### `theme.py`
- `apply_theme()`:
  1. read `assets/studio.css`, inject with `st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)`.
  2. build a Plotly template named `pct_dark` from the §7 tokens and register it
     (`plotly.io.templates["pct_dark"] = ...; plotly.io.templates.default = "pct_dark"`).
     Set transparent paper/plot bg, Inter font, `--text` font color, `--border`
     gridlines, colorway `["#4F8CFF", "#3DD68C", "#F5C84B", "#F5853F", "#FF5C5C", "#9B8CFF"]`.
- Export `RISK_COLORS = {"A": "#3DD68C", "B": "#9BD460", "C": "#F5C84B", "D": "#F5853F", "E": "#FF5C5C"}`.

### `assets/studio.css`
- Apply the §7 tokens as CSS variables on `:root`.
- Style: app background `--bg`; `[data-testid="stSidebar"]` → `--surface`;
  bordered containers (`[data-testid="stVerticalBlockBorderWrapper"]`) → `--surface`
  bg, `--border` border, 12px radius, card padding; headings in Inter, tight;
  `st.dataframe` header subtle; reduce default top padding of `.block-container`
  (e.g. `padding-top: 2rem`). Keep it minimal — don't fight Streamlit internals
  beyond colors/spacing/radius.

### `.streamlit/config.toml`
```toml
[theme]
base = "dark"
primaryColor = "#4F8CFF"
backgroundColor = "#0B0E14"
secondaryBackgroundColor = "#141925"
textColor = "#E6EAF2"
font = "sans serif"

[server]
maxUploadSize = 1024   # allow large CSVs (MB)
```

### `state.py`
- Implement the `StudioState`, `ColumnRoles`, `PolicyEntry` per Master §6 (a
  dataclass stored under `st.session_state["studio"]`).
- `init_state()` — create the state once if missing.
- `get_state() -> StudioState`.
- `guard_dataset()`, `guard_roles(*required)`, `require_policy()` — friendly
  `st.warning(...)` + `st.stop()` when prerequisites are missing.

### `components/kpi.py`
- `kpi_row(items: list[dict])` where each item = `{label, value, delta?, delta_good?: bool, help?}`.
  Render with `st.columns(len(items))`, each a bordered container: small dim label,
  large value, optional delta line colored `--success`/`--danger`.

### `components/tables.py`
- `dataframe(df, *, percent_cols=(), int_cols=(), money_cols=(), **kwargs)` →
  themed `st.dataframe(use_container_width=True, hide_index=True)` building
  `column_config` (PercentColumn/NumberColumn with formats).
- `pct(x)`, `thousands(x)`, `score(x)` formatters.

### `components/charts.py`
- Stub the themed builders other PRDs will use (each returns `go.Figure`,
  `template="pct_dark"`, explicit height, tight margins):
  `frontier(...)`, `funnel(...)`, `ks_curve(...)`, `bars(...)`,
  `vintage_stability(...)`, `crash(...)`, `pareto(...)`, `distribution(...)`.
  PRDs 03–11 specify each one's data contract; here just create the module with
  signatures + a shared `_apply_layout(fig, title, height)` helper.

## Acceptance criteria
- `pycreditools-studio` (or `streamlit run src/pycreditools/gui/app.py`) launches a
  dark, well-spaced app with the 10-item sidebar and the context header.
- No Dash imports remain anywhere; `pip install -e .[studio]` works without dash.
- Visiting any page before a dataset exists shows a friendly "carregue uma base"
  message, never a traceback.
- A throwaway Plotly figure rendered on the home/empty state uses the `pct_dark`
  template (dark, Inter, accent color).
