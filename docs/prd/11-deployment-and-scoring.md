# PRD 11 — Deployment & Batch Scoring

> Depends on PRD 04 (policy) + PRD 08 (rating recipe, optional). Page file:
> `pages/10_Deployment.py`. Mirrors notebook v14 Cell 14. Wraps
> `CreditPolicy.export`, `DeploymentPolicy` (`save`/`load`/`predict`/
> `to_production_rules`). See Master §8.

## Objective

Package the final policy (+ optional rating recipe) into a portable JSON, and
score a freshly uploaded applicant file with one click — producing row-level
decisions, ratings and quadrants, downloadable as CSV.

## API (verified — `policy.py`, `deployment.py`)
```python
CreditPolicy.export(rating_recipe=None, path: str|None=None, clean: bool=False) -> DeploymentPolicy
    # rating_recipe defaults to self.rating_recipe; if path given, also saves JSON.

DeploymentPolicy(policy: CreditPolicy, rating_recipe: GroupingRecipe | dict | None = None)
  .to_dict(clean=False) / from_dict(d)
  .save(path, clean=False) / DeploymentPolicy.load(path)
  .to_production_rules(clean=False) -> dict       # simplified hard-rules dict
  .save_production_rules(path, clean=False)
  .predict(df, simple=True, method="analytical") -> pd.DataFrame
     # simple=True -> to_decision_dataframe (decisao, motivo, rating, ...)
     # missing id/approval/default cols are auto-mocked, then dropped from output
```
> `clean=True` exports only hard rules/cutoffs (drops study metadata and rate
> stages) — good for a lean production artifact.
> `predict` ratings labels: cluster id → letter via `chr(64 + i)` (1→A, 2→B, …).
> For label consistency with the studio, prefer attaching the studio's
> `rating_labels` mapping when displaying.

## Page: `pages/10_Deployment.py`

Two tabs: **Exportar política** and **Escorar arquivo**.

### Tab 1 — Exportar política
1. `require_policy()`. Show `policy.describe()` summary + whether a rating recipe is
   attached (`StudioState.rating_result.recipe`).
2. Options: `clean` toggle ("apenas regras duras"), include rating recipe toggle.
3. Build `dep = policy.export(rating_recipe=recipe_or_None)`.
4. Show a JSON preview (`dep.to_dict(clean=...)`, pretty) in a code block, and a
   simplified rules view (`dep.to_production_rules(clean=...)`).
5. **Download buttons**: `st.download_button` for the full policy JSON and for the
   production-rules JSON (serialize with `json.dumps(..., indent=2, ensure_ascii=False)`).
   Also offer "salvar no projeto" (writes the path into the project bundle, PRD 02).

### Tab 2 — Escorar arquivo (batch predict)
1. Load a deployment policy: either **use current** (the active policy + recipe) or
   **upload a saved JSON** (`DeploymentPolicy.from_dict(json.load(...))` /
   `DeploymentPolicy.load(path)`).
2. Upload the applicants file (`st.file_uploader`, csv/parquet). Preview head.
3. Run `dep.predict(new_df, simple=True, method="analytical")` (cached by
   `(file_hash, dep.to_dict())`). `simple=True` returns the decision frame
   (`decisao`, `motivo`, `rating`, plus inputs); offer a `simple=False` toggle for
   the full frame (includes `new_approval`, `simulated_default`, `scenario`,
   `Rating`).
4. **Outputs**:
   - KPI: total scored, approval rate (`decisao == "Aprovado"`), rating mix.
   - Rating distribution bar (`RISK_COLORS`); decisions table (themed, paginated
     head); rejection-reason breakdown (`motivo` value counts).
   - `st.download_button` for the full scored CSV.

## Edge cases
- Scoring file missing some configured columns: `predict` auto-mocks
  id/approval/default and drops them from the output — surface a note listing what
  was mocked so the user understands.
- A rate stage in the policy makes decisions probabilistic; for clean production
  rules suggest `clean=True`.
- Custom stress isn't serializable (`CustomStress.to_dict` is lossy) — not a
  concern here since v1 only uses `AggravationStress`, which round-trips.

## Acceptance criteria
- Exporting the v14 final policy + rating recipe produces a JSON that
  `DeploymentPolicy.load` reads back, matching the notebook's
  `politica_final_producao.json` structure (metadata, funnel_stages, risk recipe).
- Re-loading that JSON and predicting on a 10-row sample yields decisão + rating +
  cenário per row (matches notebook Cell 14 `dep_loaded.predict(amostra, simple=True)`).
- Downloaded scored CSV opens with the expected columns.

## Validação & Gate (BLOQUEANTE)

> Não avance sem as 4 camadas verdes **E** o "aprovado" do dono. Ver `IMPLEMENTATION_GUIDE.md` §3–§4.

### Definition of Done
- [ ] Export JSON (política + production-rules), toggle `clean`, preview + download.
- [ ] Batch predict: usar política atual **ou** upload de JSON; `simple` toggle.
- [ ] KPIs (total, taxa de aprovação, mix de rating) + distribuição + download do CSV escorado.
- [ ] Nota listando colunas mockadas pelo `predict`.

### Validação automática
- **L1** `ruff check ...` → 0.
- **L2** `policy.export().to_dict()`↔`from_dict` round-trip; `DeploymentPolicy.load(save(x))` == `x` (estrutura).
- **L3** AppTest: aba export mostra JSON + botões de download; aba scoring com arquivo injetado → tabela de decisões.
- **L4** **Paridade**: `dep.predict(df)` via studio == `policy.simulate(df)`/`DeploymentPolicy.predict` direto (mesmas decisões/ratings).

### Verificação visual (dono)
1. Exportar a policy v14 + recipe; recarregar o JSON; escorar 10 linhas → decisão + rating + cenário por linha.

### Gate
Entregue o **Gate Report** e **pare**. Pergunte: "Aprova o PRD 11 — concluímos o v1?".
