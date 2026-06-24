# PRD 02 — Data Ingestion, Column Roles & Projects

> Depends on PRD 01. Unblocks every other page. See Master §6 (state), §9 (caching,
> population selector), §10 (non-goals).

## Objective

Let the user get a base into the studio (upload **or** generate), confirm the
**column roles** the engine needs (auto-detected), preview the data, and
save/restore the whole work as a local **project**.

## Page: `pages/1_Ingestion.py`

Three sections (use `st.tabs` or expanders): **1) Carregar base · 2) Mapear
colunas · 3) Projetos**.

### 1) Carregar base
- `st.file_uploader` accepting `.csv`, `.parquet` (respect `maxUploadSize`).
- **Generate sample data** panel: `st.number_input` for `n_applicants`
  (default 50_000, max 1_000_000), `st.number_input` seed (default 42), button
  "Gerar base de exemplo" → calls `generate_sample_data(n_applicants, seed)`
  (from `pycreditools`). Show the resulting columns.
- On load: store into `StudioState.df`, `df_name`, compute `df_hash` (hash of file
  bytes, or of `n_applicants+seed` for sample). Cache the loaded DataFrame with
  `@st.cache_data` keyed by the source so reruns don't re-read.
- Show a KPI row: rows, columns, memory (MB), and (if a binary default col is
  detected) overall observed bad rate.
- Data preview: `st.dataframe(df.head(200))` themed; plus a "tipos das colunas"
  expander with dtype + %null + n-unique per column.

### 2) Mapear colunas (`components/column_roles.py`)
Render a role picker. For each role, a `st.selectbox`/`st.multiselect` over the
df columns, pre-filled by auto-detection (user can override). Roles (Master §6):

| Role | Widget | Required? | Auto-detect heuristic |
|---|---|---|---|
| `applicant_id_col` | selectbox | yes | column with all-unique values and/or name in {id, applicant_id, cpf, customer_id} |
| `score_cols` | multiselect | yes | numeric, integer-ish, range ~0–1000, name contains "score" (incl. `legacy_score`) |
| `primary_score_col` | selectbox (subset of score_cols) | yes | the score with highest KS if computable, else last of score_cols (e.g. `score_5`) |
| `current_approval_col` | selectbox | no | binary 0/1, name in {approved, approval, aprovado} |
| `actual_default_col` | selectbox | no | binary 0/1 (NaN allowed), name in {actual_default, default, target, bad, inadimplente} |
| `current_hired_col` | selectbox | no | binary 0/1, name in {hired, contratou, contracted} |
| `time_col` | selectbox | no | values like "YYYY-MM" or datetime, name in {safra, vintage, date, mes} |
| `segment_col` | selectbox | no | low-cardinality categorical, name in {region, loja, segment, uf} |
| `estimated_default_col` | selectbox | no | float in [0,1], name in {estimated_default, pd, true_pd, est_pd} |
| `oot_date` | text/select | no | if `time_col` set: default to min OOT boundary or "2025-01"; offer the sorted unique values |

- Implement detection in `data_access.detect_roles(df) -> ColumnRoles`.
- After mapping, show a small **validation panel**: build a throwaway
  `CreditPolicy(applicant_id_col, score_cols, current_approval_col,
  actual_default_col, time_col)` and call `.validate(df)`; show green check or the
  translated missing-columns error.
- Persist roles into `StudioState.roles`. Changing roles must **invalidate
  downstream caches** (because they key on roles) — naturally handled if caches
  key on `roles` values.

### 3) Projetos (`projects.py`)
A project bundles the analysis so the user can resume. Single-user/local.
- **Save project**: write a JSON to a local folder (default
  `~/.pycreditools_studio/projects/<name>.json`; allow a custom path via
  `st.text_input`). Contents:
  ```json
  {
    "name": "...",
    "created_at": "...",
    "dataset": {"name": "...", "path_or_source": "...", "hash": "...", "n_rows": N,
                "sample": {"n_applicants": ..., "seed": ...} | null},
    "roles": { ...ColumnRoles... },
    "policies": { "<name>": {"policy": <CreditPolicy.to_dict()>,
                              "flat_stress_factor": 1.2} },
    "active_policy": "...",
    "rating_recipe": <GroupingRecipe.to_dict()> | null,
    "rating_labels": {"1": "A", ...} | null
  }
  ```
  Do **not** embed the dataset (could be ~1M rows). Store the source so it can be
  re-loaded; if it was sample data, store `{n_applicants, seed}` and regenerate.
- **Load project**: list JSON files in the projects folder (`st.selectbox`), load,
  reconstruct: roles, policies via `CreditPolicy.from_dict`, rating recipe via
  `GroupingRecipe.from_dict`. Re-load/regenerate the dataset; if the original CSV
  path is gone, prompt the user to re-upload (match by `hash`).
- Buttons: "Salvar projeto", "Carregar projeto", "Novo projeto" (clears state).

## Helper module: `data_access.py`
- `load_csv(file) -> (df, hash)` / `load_parquet(...)` — `@st.cache_data`.
- `make_sample(n, seed) -> (df, hash)` — wraps `generate_sample_data`, hash from
  `(n, seed)`.
- `detect_roles(df) -> ColumnRoles`.
- `population_filter(df, roles, choice, custom_expr=None) -> df` — the shared
  population selector used by other pages (All / Aprovados / Contratados / DEV /
  OOT / Custom). DEV/OOT derived from `time_col` vs `oot_date`. "Aprovados" uses
  `current_approval_col == 1`; "Contratados" uses `current_hired_col == 1`.

## Edge cases
- No `actual_default_col`: downstream KS/grouping pages show "defina a coluna de
  default para habilitar esta análise".
- `actual_default` is NaN for non-hired (sample data): the preview bad rate and
  KS must `dropna` and report effective N.
- Huge file: show a spinner; rely on pyarrow CSV engine; cap preview to 200 rows.
- Re-uploading a different file resets `last_sim`, `legacy_sim`, `rating_result`.

## Acceptance criteria
- Generating sample data (n=50k, seed=42) populates the base and auto-detects:
  `applicant_id`, scores `score_2..5`+`legacy_score`, `actual_default`,
  `approved`, `hired`, `safra`, `region`, and suggests `oot_date≈2025-01`.
- Uploading `dataset_v14.csv` yields the same role mapping.
- `.validate(df)` passes after auto-detection; a deliberately wrong role shows a
  friendly error.
- Saving then "Novo projeto" then loading restores roles + policies + ratings, and
  the dataset is re-loaded/regenerated.

## Validação & Gate (BLOQUEANTE)

> Não avance sem as 4 camadas verdes **E** o "aprovado" do dono. Ver `IMPLEMENTATION_GUIDE.md` §3–§4.

### Definition of Done
- [ ] Upload CSV/Parquet **e** "Gerar base de exemplo" populam `StudioState.df/df_name/df_hash`.
- [ ] `detect_roles` preenche os papéis no v14 sample (ids, scores, default, approved, hired, safra, region, oot≈2025-01); usuário pode sobrescrever.
- [ ] Painel de validação roda `CreditPolicy.validate` e mostra ok/erro traduzido.
- [ ] Salvar / Carregar / Novo projeto funcionam; dataset re-carregado ou regenerado por `{n,seed}`.
- [ ] `population_filter` (All/Aprovados/Contratados/DEV/OOT/Custom) implementado e reutilizável.

### Validação automática
- **L1** `ruff check ...` → 0.
- **L2** `detect_roles(sample_df)` retorna os papéis esperados; `population_filter` subsetta certo (DEV = `time_col < oot_date`); `projects.save`→`load` faz round-trip de roles+policies+recipe.
- **L3** AppTest de `1_Ingestion.py`: sem estado → mostra uploader; com base injetada via fixture → KPIs + preview sem exceção; alterar um role atualiza `session_state`.
- **L4** Paridade: **N/A** (a única chamada de engine é `validate`/`generate_sample_data`).

### Verificação visual (dono)
1. Gerar base (50k, seed 42) → conferir roles auto-detectados. 2. Salvar projeto → "Novo projeto" → Carregar → tudo volta (roles/políticas/rating).

### Gate
Entregue o **Gate Report** e **pare**. Pergunte: "Aprova o PRD 02?".
