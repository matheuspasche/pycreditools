# PRD 01 — App Shell & Design System

> Foundation task. No dependency on other pages. Produces the theme, the
> navigation shell, the session-state module and the reusable components every
> other page imports. See Master (PRD 00) §4, §6, §7, §9.

## Objective

Stand up the Streamlit app skeleton with a polished **dark fintech** look, the
sidebar navigation, the shared `state.py`, and the `components/` + `theme.py`
helpers — so pages 02–11 only have to fill in content.

> **Architecture (read PRD 00 §4b first).** This PRD establishes the two layers:
> the framework-agnostic **core** `pycreditools/studio/` (no `streamlit`) and the
> Streamlit **skin** `pycreditools/gui/`. Get this split right here — every later
> PRD depends on it.

## Deliverables

**Core — `src/pycreditools/studio/` (must NOT import streamlit):**
1. `__init__.py`.
2. `models.py` — `StudioState`, `ColumnRoles`, `PolicyEntry`, `ProjectBundle`
   (pure dataclasses, per Master §6).
3. `charts.py` — registers the Plotly template `pct_dark` (from §7 tokens),
   exports `RISK_COLORS`, and stubs the themed `go.Figure` builders (PRD 01 §charts).

**Skin — `src/pycreditools/gui/` (only place `import streamlit` appears):**
4. `app.py` — entrypoint (`st.navigation`).
5. `__init__.py` — `run_studio()`.
6. `theme.py` — `apply_theme()`: inject `assets/studio.css` and set
   `plotly.io.templates.default = "pct_dark"` (template comes from `studio.charts`).
7. `assets/studio.css`.
8. `session.py` — bridges `st.session_state` ↔ `studio.models`; `init_state`,
   `get_state`, `guard_dataset`, `guard_roles`, `require_policy`.
9. `components/{__init__,kpi,tables}.py` — st rendering helpers (call
   `studio.charts` for figures; never build figures with `st` inside).

**Shared:**
10. `.streamlit/config.toml` — dark theme tokens.
11. `pyproject.toml`: add `studio` extra + `[project.scripts]`, remove `gui` Dash extra.
12. `tests/studio/conftest.py` (fixtures, guide §5) + `tests/studio/test_boundary.py`
    (core has no `streamlit` import).
13. Delete the old Dash app (see PRD 00 §4 "Delete" list).

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

### `studio/charts.py` — Plotly template + colors (pure, no streamlit)
- On import, build and register a Plotly template `pct_dark` from the §7 tokens
  (`plotly.io.templates["pct_dark"] = ...`): transparent paper/plot bg, Inter font,
  `--text` font color, `--border` gridlines, colorway
  `["#4F8CFF", "#3DD68C", "#F5C84B", "#F5853F", "#FF5C5C", "#9B8CFF"]`.
- Export `RISK_COLORS = {"A": "#3DD68C", "B": "#9BD460", "C": "#F5C84B", "D": "#F5853F", "E": "#FF5C5C"}`.

### `gui/theme.py` (skin)
- `apply_theme()`:
  1. read `assets/studio.css`, inject with `st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)`.
  2. `import pycreditools.studio.charts` (registers `pct_dark`) and set
     `plotly.io.templates.default = "pct_dark"`.

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

### `studio/models.py` (pure) + `gui/session.py` (skin)
- `studio/models.py`: the `StudioState`, `ColumnRoles`, `PolicyEntry`,
  `ProjectBundle` dataclasses per Master §6 — **no streamlit**.
- `gui/session.py`:
  - `init_state()` — create a `StudioState` once under `st.session_state["studio"]`.
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

### `studio/charts.py` — figure builders (pure, no streamlit)
- Stub the themed builders other PRDs will use (each returns `go.Figure`,
  `template="pct_dark"`, explicit height, tight margins):
  `frontier(...)`, `funnel(...)`, `ks_curve(...)`, `bars(...)`,
  `vintage_stability(...)`, `crash(...)`, `pareto(...)`, `distribution(...)`.
  PRDs 03–11 specify each one's data contract; here just create the module with
  signatures + a shared `_apply_layout(fig, title, height)` helper. Pages render
  them with `st.plotly_chart(fig, use_container_width=True)` (the only st part).

## Acceptance criteria
- `pycreditools-studio` (or `streamlit run src/pycreditools/gui/app.py`) launches a
  dark, well-spaced app with the 10-item sidebar and the context header.
- No Dash imports remain anywhere; `pip install -e .[studio]` works without dash.
- Visiting any page before a dataset exists shows a friendly "carregue uma base"
  message, never a traceback.
- A throwaway Plotly figure rendered on the home/empty state uses the `pct_dark`
  template (dark, Inter, accent color).

## Validação & Gate (BLOQUEANTE)

> Não avance sem as 4 camadas verdes **E** o "aprovado" do dono. Ver `IMPLEMENTATION_GUIDE.md` §3–§4.

### Definition of Done
- [ ] `pycreditools-studio` e `streamlit run src/pycreditools/gui/app.py` abrem o app dark com a sidebar de 10 itens e o header de contexto.
- [ ] Nenhum import do Dash em lugar algum; `pip install -e ".[studio,dev]"` instala sem dash.
- [ ] `theme.py` injeta o CSS e registra/define o template Plotly `pct_dark`.
- [ ] `state.py` expõe `init_state/get_state/guard_dataset/guard_roles/require_policy`.
- [ ] `components/{kpi,tables,charts}.py` existem com as assinaturas do PRD.
- [ ] `tests/studio/conftest.py` com os fixtures do guia §5.

### Validação automática
- **L1** `ruff check src/pycreditools/gui tests/studio` → 0 erros.
- **L2** `pytest tests/studio -q -k "not apptest and not parity"`: `get_state` cria o estado; `guard_dataset` chama `st.stop`/avisa sem dados; cada builder de `charts.*` retorna `plotly.graph_objects.Figure`; `tables.dataframe`/`kpi_row` não levantam.
- **L3** `pytest tests/studio/apptest -q`: `AppTest.from_file(".../app.py").run()` sem exceção; abrir qualquer página sem dataset mostra warning (não traceback).
- **L4** Paridade: **N/A** neste PRD.

### Verificação visual (dono)
1. `streamlit run src/pycreditools/gui/app.py`. 2. Conferir tema escuro, sidebar de 10 itens, header de contexto, espaçamento "leve". 3. Abrir página sem base → mensagem amigável.

### Gate
Entregue o **Gate Report** (guia §4) e **pare**. Pergunte: "Aprova o PRD 01 para eu seguir?".
