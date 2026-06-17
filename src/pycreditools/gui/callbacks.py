import base64
import io
import json

import base64
import plotly.express as px
import plotly.graph_objects as go
from dash.exceptions import PreventUpdate

from pycreditools.policy import CreditPolicy
from pycreditools.stages import FilterStage
from pycreditools.expressions import Expression
from pycreditools.stress import AggravationStress
from pycreditools.optimization import optimize_cutoffs

import pandas as pd
import numpy as np
import plotly.express as px
from dash import Input, Output, State, MATCH, ALL, html, dcc, no_update
import dash_mantine_components as dmc
from dash_iconify import DashIconify

from pycreditools import CreditPolicy, col
from .components import ingestion, studio, simulation, risk, evaluation

from .app import app


@app.callback(
    Output("page-content", "children"),
    Input("url", "pathname"),
    State("dataset-store", "data"),
    State("policies-store", "data"),
    State("dataset-config-store", "data")
)
def render_page_content(pathname, data_json, policies, config):
    # Build column list from the stored dataset (if any) to pre-populate selects
    columns = []
    segments = []
    
    if data_json:
        try:
            df = pd.read_json(io.StringIO(data_json), orient='split')
            columns = [{"label": str(c), "value": str(c)} for c in df.columns]
            
            # Extract unique segments
            config = config or {}
            segment_col = config.get("segment")
            if segment_col and segment_col in df.columns:
                segments = [{"label": str(v), "value": str(v)} for v in sorted(df[segment_col].dropna().astype(str).unique())]
        except Exception as e:
            print(f"Error extracting segments: {e}")
            
    default_target = None
    default_scores = None
    if policies:
        last_policy = list(policies.values())[-1]
        default_target = last_policy.get("target")
        default_scores = last_policy.get("scores")

    if pathname == "/":
        return ingestion.layout()
    elif pathname == "/studio":
        return studio.layout(columns=columns)
    elif pathname == "/evaluation":
        return evaluation.layout(columns=columns, segments=segments)
    elif pathname == "/simulation":
        return simulation.layout()
    elif pathname == "/risk-tiers":
        return risk.layout(columns=columns, default_target=default_target, default_scores=default_scores)
    return dmc.Text("404: Not found", size="xl", ta="center", mt="xl")


# --- Ingestion Callbacks ---

def build_ingestion_success_ui(df, filename):
    import dash_mantine_components as dmc
    from dash import html
    
    cols = [{"label": str(c), "value": str(c)} for c in df.columns]
    
    approved_col = next((c for c in df.columns if 'approv' in c.lower()), None)
    hired_col = next((c for c in df.columns if 'hire' in c.lower()), None)
    sample_col = next((c for c in df.columns if 'sample' in c.lower() or 'dev' in c.lower()), None)
    
    config_card = dmc.Card([
        dmc.Text("Dataset Configuration (Auto-detected)", fw=700, mb="md"),
        dmc.Grid([
            dmc.GridCol([
                dmc.Select(
                    id="config-target-col",
                    label="Target / Default Column",
                    description="Global target used by default",
                    data=cols,
                    value=next((c for c in df.columns if 'default' in c.lower() or 'target' in c.lower() or 'mau' in c.lower()), None),
                    searchable=True,
                    clearable=True
                )
            ], span=3),
            dmc.GridCol([
                dmc.Select(
                    id="config-applicant-id",
                    label="Applicant ID Column (Optional)",
                    description="Leave blank to auto-detect",
                    data=cols,
                    value=next((c for c in df.columns if 'id' in c.lower() or 'cpf' in c.lower() or 'applicant' in c.lower()), None),
                    searchable=True,
                    clearable=True
                )
            ], span=3),
            dmc.GridCol([
                dmc.Select(
                    id="config-time-col",
                    label="Time / Vintage Column",
                    description="Used for vintage stability charts",
                    data=cols,
                    value=next((c for c in df.columns if 'safra' in c.lower() or 'date' in c.lower() or 'month' in c.lower() or 'time' in c.lower()), None),
                    searchable=True,
                    clearable=True
                )
            ], span=3),
            dmc.GridCol([
                dmc.Select(
                    id="config-sample-col",
                    label="DEV/OOT Sample Column",
                    description="Used to split DEV (simulation) and OOT",
                    data=cols,
                    value=sample_col,
                    searchable=True,
                    clearable=True
                )
            ], span=3),
            dmc.GridCol([
                dmc.Select(
                    id="config-segment-col",
                    label="Segment Column (Optional)",
                    description="Used to break down results (e.g. Store, Channel)",
                    data=cols,
                    value=next((c for c in df.columns if 'loja' in c.lower() or 'store' in c.lower() or 'segment' in c.lower() or 'channel' in c.lower() or 'regional' in c.lower()), None),
                    searchable=True,
                    clearable=True
                )
            ], span=4),
            dmc.GridCol([
                dmc.Select(
                    id="config-approved-col",
                    label="Legacy Approved Column",
                    description="Used for legacy baseline in simulations",
                    data=cols,
                    value=approved_col,
                    searchable=True,
                    clearable=True
                )
            ], span=4),
            dmc.GridCol([
                dmc.Select(
                    id="config-hired-col",
                    label="Hired Column",
                    description="Used for legacy default rate calculation",
                    data=cols,
                    value=hired_col,
                    searchable=True,
                    clearable=True
                )
            ], span=4)
        ]),
        dmc.Divider(my="md"),
        dmc.Text("Derived Features (Low-Code Formula)", fw=600, mb="xs"),
        dmc.Text("Add custom metrics using Pandas eval syntax (e.g. vl_vencido_scr / income).", size="sm", c="dimmed", mb="sm"),
        dmc.Group([
            dmc.TextInput(id="derived-name-input", placeholder="e.g. commitment_rate", style={"flex": 1}),
            dmc.TextInput(id="derived-formula-input", placeholder="e.g. vl_vencido_scr / income", style={"flex": 2}),
            dmc.Button("Add Metric", id="add-derived-btn", variant="light", color="grape")
        ], align="flex-start", mb="sm"),
        html.Div(id="derived-features-feedback")
    ], withBorder=True, shadow="sm", radius="md", mb="xl")
    
    preview_df = df.head(10)
    header = [html.Th(col) for col in preview_df.columns]
    rows = [html.Tr([html.Td(str(val)) for val in row]) for _, row in preview_df.iterrows()]
        
    table = dmc.Table([
        html.Thead(html.Tr(header)),
        html.Tbody(rows)
    ], striped=True, highlightOnHover=True, withTableBorder=True)
    
    return html.Div([
        dmc.Alert(f"Successfully loaded {filename} ({len(df):,} rows, {len(df.columns)} columns).", color="green", title="Success", mb="md"),
        config_card,
        dmc.Text("Data Preview (Top 10 rows):", fw=500, mb="sm"),
        dmc.ScrollArea(table, type="always")
    ])

@app.callback(
    Output("data-preview-container", "children"),
    Output("dataset-store", "data"),
    Input("upload-data", "contents"),
    Input("test-load-btn", "n_clicks"),
    State("upload-data", "filename")
)
def update_output(contents, n_clicks, filename):
    import os
    from dash import ctx
    trigger = ctx.triggered_id
    if trigger == "test-load-btn":
        csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "dataset_v14.csv"))
        if not os.path.exists(csv_path):
            csv_path = os.path.abspath("dataset_v14.csv")
        print(f"test-load-btn: loading CSV from {csv_path}, exists={os.path.exists(csv_path)}")
        df = pd.read_csv(csv_path)
        data_json = df.to_json(date_format='iso', orient='split')
        print(f"test-load-btn: loaded {len(df)} rows, {len(df.columns)} cols")
        return build_ingestion_success_ui(df, "dataset_v14.csv"), data_json
        
    if contents is None:
        return dmc.Alert("Please upload a dataset to begin.", color="blue", title="Info"), no_update

    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)

    try:
        if 'csv' in filename:
            df = pd.read_csv(io.StringIO(decoded.decode('utf-8')))
        elif 'parquet' in filename:
            df = pd.read_parquet(io.BytesIO(decoded))
        else:
            return dmc.Alert("Unsupported file format.", color="red", title="Error"), no_update
            
        data_json = df.to_json(date_format='iso', orient='split')
        return build_ingestion_success_ui(df, filename), data_json
        
    except Exception as e:
        return dmc.Alert(f"There was an error processing this file: {str(e)}", color="red", title="Error"), no_update

@app.callback(
    Output("dataset-config-store", "data"),
    Input("config-approved-col", "value"),
    Input("config-hired-col", "value"),
    Input("config-sample-col", "value"),
    Input("config-time-col", "value"),
    Input("config-target-col", "value"),
    Input("config-applicant-id", "value"),
    Input("config-segment-col", "value")
)
def update_dataset_config(approved, hired, sample, time, target, applicant_id, segment_col):
    return {
        "approved": approved,
        "hired": hired,
        "sample": sample,
        "time": time,
        "target": target,
        "app_id": applicant_id,
        "segment": segment_col
    }

@app.callback(
    Output("dataset-store", "data", allow_duplicate=True),
    Output("data-preview-container", "children", allow_duplicate=True),
    Output("derived-features-feedback", "children"),
    Input("add-derived-btn", "n_clicks"),
    State("derived-name-input", "value"),
    State("derived-formula-input", "value"),
    State("dataset-store", "data"),
    State("upload-data", "filename"),
    prevent_initial_call=True
)
def add_derived_feature(n_clicks, name, formula, data_json, filename):
    if not n_clicks or not name or not formula or not data_json:
        from dash.exceptions import PreventUpdate
        raise PreventUpdate
        
    try:
        df = pd.read_json(io.StringIO(data_json), orient='split')
        
        # Evaluate formula
        df[name] = df.eval(formula)
        
        # Rebuild UI
        new_data_json = df.to_json(date_format='iso', orient='split')
        
        # Show success message
        feedback = dmc.Alert(f"Metric '{name}' added successfully! It is now available in the Studio.", color="green", title="Success")
        
        return new_data_json, build_ingestion_success_ui(df, filename or "data.csv"), feedback
    except Exception as e:
        feedback = dmc.Alert(f"Error evaluating formula: {str(e)}", color="red", title="Formula Error")
        from dash import no_update
        return no_update, no_update, feedback



# --- Studio Callbacks ---

@app.callback(
    Output("stages-container", "children"),
    Input("add-stage-btn", "n_clicks"),
    State("stages-container", "children"),
    State("score-cols-select", "data") # Any column can be a feature
)
def add_stage(n_clicks, children, cols_data):
    if not n_clicks:
        return children
        
    new_stage = dmc.Card(
        [
            dmc.Group(
                [
                    dmc.Text(f"Hard Filter {n_clicks}", fw=500),
                    dmc.Button("Remove", id={"type": "remove-stage-btn", "index": n_clicks}, size="xs", color="red", variant="subtle")
                ],
                justify="space-between", mb="sm"
            ),
            dmc.Grid(
                [
                    dmc.GridCol(
                        dmc.Select(
                            id={"type": "stage-feature", "index": n_clicks},
                            label="Feature",
                            data=cols_data if cols_data else [],
                            placeholder="Select feature",
                            searchable=True
                        ),
                        span=5
                    ),
                    dmc.GridCol(
                        dmc.Select(
                            id={"type": "stage-operator", "index": n_clicks},
                            label="Operator",
                            data=[
                                {"label": ">=", "value": ">="},
                                {"label": "<=", "value": "<="},
                                {"label": "==", "value": "=="},
                            ],
                            value=">=",
                        ),
                        span=3
                    ),
                    dmc.GridCol(
                        [
                            dmc.NumberInput(
                                id={"type": "stage-cutoff", "index": n_clicks},
                                label="Cutoff Value",
                                placeholder="e.g. 500"
                            ),
                            html.Div(id={"type": "stage-distribution", "index": n_clicks}, style={"marginTop": "5px"})
                        ],
                        span=4
                    )
                ]
            )
        ],
        withBorder=True, shadow="sm", mb="sm", id={"type": "stage-card", "index": n_clicks}, className="stage-card"
    )
    
    if children is None:
        children = []
    children.append(new_stage)
    return children

@app.callback(
    Output({"type": "stage-distribution", "index": MATCH}, "children"),
    Input({"type": "stage-feature", "index": MATCH}, "value"),
    State("dataset-store", "data"),
    prevent_initial_call=True
)
def update_stage_distribution(feature, data_json):
    if not feature or not data_json:
        from dash.exceptions import PreventUpdate
        raise PreventUpdate
        
    try:
        import io
        import pandas as pd
        df = pd.read_json(io.StringIO(data_json), orient='split')
        if feature in df.columns and pd.api.types.is_numeric_dtype(df[feature]):
            s = df[feature]
            vmin = s.min()
            vmed = s.median()
            vmax = s.max()
            return dmc.Text(f"Min: {vmin:g} | Med: {vmed:g} | Max: {vmax:g}", size="xs", c="dimmed", fs="italic")
        else:
            return dmc.Text("Select a numeric feature.", size="xs", c="red", fs="italic")
    except Exception:
        return ""


@app.callback(
    Output("policies-store", "data"),
    Output("studio-notifications", "children"),
    Input("save-policy-btn", "n_clicks"),
    State("policies-store", "data"),
    State("policy-name-input", "value"),
    State("target-col-select", "value"),
    State("score-cols-select", "value"),
    State({"type": "stage-feature", "index": ALL}, "value"),
    State({"type": "stage-operator", "index": ALL}, "value"),
    State({"type": "stage-cutoff", "index": ALL}, "value"),
    State("dataset-store", "data")
)
def save_policy(n_clicks, policies, name, target, scores, features, operators, cutoffs, data_json):
    print(f"save_policy TRIGGERED. n_clicks: {n_clicks}, policies: {policies}, name: {name}, target: {target}, scores: {scores}, features: {features}, cutoffs: {cutoffs}", flush=True)
    if not n_clicks:
        return no_update, no_update
        
    if not name or not target or not scores:
        print("save_policy failed: Missing fields")
        return no_update, dmc.Notification(
            title="Error",
            id="notif-error",
            action="show",
            message="Please fill Policy Name, Target, and Score Columns.",
            color="red",
            icon=DashIconify(icon="tabler:x")
        )
        
    policy_stages = []
    for f, op, c in zip(features, operators, cutoffs):
        if f and c is not None:
            policy_stages.append({
                "feature": f,
                "operator": op,
                "cutoff": c
            })
            
    policies[name] = {
        "target": target,
        "scores": scores,
        "stages": policy_stages
    }
    
    return policies, dmc.Notification(
        title="Success",
        id="notif-success",
        action="show",
        message=f"Policy '{name}' saved successfully!",
        color="green",
        icon=DashIconify(icon="tabler:check")
    )

@app.callback(
    Output("saved-policies-list", "children"),
    Input("policies-store", "data")
)
def update_policies_sidebar(policies):
    if not policies:
        return dmc.Text("No policies saved yet.", c="dimmed", fs="italic", size="sm")
        
    items = []
    for pol_name in policies:
        items.append(
            dmc.Button(
                pol_name, 
                id={"type": "load-policy-btn", "index": pol_name}, 
                fullWidth=True, 
                variant="subtle", 
                color="gray", 
                style={"justifyContent": "flex-start"},
                mb=5
            )
        )
    return items

@app.callback(
    Output("policy-name-input", "value"),
    Output("target-col-select", "value"),
    Output("score-cols-select", "value"),
    Output("stages-container", "children", allow_duplicate=True),
    Input({"type": "load-policy-btn", "index": ALL}, "n_clicks"),
    Input("new-policy-btn", "n_clicks"),
    State("policies-store", "data"),
    State("score-cols-select", "data"),
    State("dataset-config-store", "data"),
    prevent_initial_call=True
)
def load_policy(load_clicks, new_clicks, policies, cols_data, config):
    from dash import ctx
    trigger = ctx.triggered_id
    
    config = config or {}
    default_target = config.get("target")
    
    if trigger == "new-policy-btn":
        return "", default_target, [], []
        
    if isinstance(trigger, dict) and trigger.get("type") == "load-policy-btn":
        pol_name = trigger.get("index")
        if policies and pol_name in policies:
            pol = policies[pol_name]
            
            # Reconstruct stages
            stages_children = []
            for i, stage in enumerate(pol.get("stages", [])):
                new_stage = dmc.Card(
                    [
                        dmc.Group(
                            [
                                dmc.Text(f"Hard Filter {i+1}", fw=500),
                                dmc.Button("Remove", id={"type": "remove-stage-btn", "index": i+1000}, size="xs", color="red", variant="subtle")
                            ],
                            justify="space-between", mb="sm"
                        ),
                        dmc.Grid(
                            [
                                dmc.GridCol(
                                    dmc.Select(
                                        id={"type": "stage-feature", "index": i+1000},
                                        label="Feature",
                                        data=cols_data if cols_data else [],
                                        value=stage["feature"],
                                        searchable=True
                                    ),
                                    span=5
                                ),
                                dmc.GridCol(
                                    dmc.Select(
                                        id={"type": "stage-operator", "index": i+1000},
                                        label="Operator",
                                        data=[
                                            {"label": ">=", "value": ">="},
                                            {"label": "<=", "value": "<="},
                                            {"label": "==", "value": "=="},
                                        ],
                                        value=stage["operator"],
                                    ),
                                    span=3
                                ),
                                dmc.GridCol(
                                    [
                                        dmc.NumberInput(
                                            id={"type": "stage-cutoff", "index": i+1000},
                                            label="Cutoff Value",
                                            value=stage["cutoff"]
                                        ),
                                        html.Div(id={"type": "stage-distribution", "index": i+1000}, style={"marginTop": "5px"})
                                    ],
                                    span=4
                                )
                            ]
                        )
                    ],
                    withBorder=True, shadow="xs", radius="md", mb="sm", p="sm"
                )
                stages_children.append(new_stage)
                
            return pol_name, pol.get("target"), pol.get("scores"), stages_children
            
    from dash.exceptions import PreventUpdate
    raise PreventUpdate



# --- Simulation Callbacks ---

@app.callback(
    Output("tradeoff-scatter-graph", "figure"),
    Output("simulation-details-container", "children"),
    Output("simulation-segment-container", "children"),
    Input("run-simulations-btn", "n_clicks"),
    Input("stress-factor-input", "value"),
    State("policies-store", "data"),
    State("dataset-store", "data"),
    State("dataset-config-store", "data"),
    prevent_initial_call=True
)
def run_simulations(n_clicks, stress_factor_input, policies, data_json, config):
    if not n_clicks or not policies or not data_json:
        return px.scatter(title="Upload data and create policies first."), None
        
    df_full = pd.read_json(io.StringIO(data_json), orient='split')
    config = config or {}
    sample_col = config.get("sample")
    approved_col = config.get("approved")
    hired_col = config.get("hired")
    
    if sample_col and sample_col in df_full.columns:
        # Assuming DEV/OOT split
        df = df_full[df_full[sample_col].astype(str).str.upper() == "DEV"].copy()
        if len(df) == 0: # Fallback if no "DEV" string
            df = df_full.copy()
    else:
        time_col = config.get("time")
        if time_col and time_col in df_full.columns:
            unique_dates = sorted(df_full[time_col].dropna().unique())
            if len(unique_dates) > 1:
                oot_date = unique_dates[-1] # The latest vintage is OOT
                df = df_full[df_full[time_col] < oot_date].copy()
            else:
                df = df_full.copy()
        else:
            df = df_full.copy()
    
    N = len(df)
    
    # Legacy reference (same as V14)
    legacy_approval_rate = 0.0
    legacy_default_rate = 0.0
    try:
        if approved_col and approved_col in df.columns:
            legacy_approval_rate = df[approved_col].mean()
        if hired_col and hired_col in df.columns and "actual_default" in df.columns:
            legacy_default_rate = df.loc[df[hired_col] == 1, "actual_default"].mean()
        elif approved_col and approved_col in df.columns and "actual_default" in df.columns:
            legacy_default_rate = df.loc[df[approved_col] == 1, "actual_default"].mean()
    except Exception:
        pass

    from pycreditools import TradeoffAnalyzer, CustomStress
    from pycreditools.expressions import col as pcol

    results = []
    
    # Auto-detect applicant id if not configured
    app_id = config.get("app_id")
    if not app_id and df_full is not None:
        candidates = [c for c in df_full.columns if any(kw in c.lower() for kw in ['id', 'cpf', 'applicant'])]
        app_id = candidates[0] if candidates else df_full.columns[0]
    global_stress = float(stress_factor_input) if stress_factor_input is not None else 1.0
    
    segment_breakdown_tables = []
    
    for pol_name, pol_config in policies.items():
        try:
            target_col = pol_config["target"]
            scores = pol_config["scores"]
            
            # Build CreditPolicy exactly like V14
            policy = CreditPolicy(
                applicant_id_col=app_id,
                score_cols=tuple(scores),
                actual_default_col=target_col
            )
            
            # Add Hard Filters using .filter() — same as V14
            for stage in pol_config.get("stages", []):
                feat = stage["feature"]
                op = stage["operator"]
                val = stage["cutoff"]
                
                if op == ">=":
                    condition = pcol(feat) >= val
                elif op == "<=":
                    condition = pcol(feat) <= val
                elif op == "==":
                    condition = pcol(feat) == val
                else:
                    condition = pcol(feat) >= val

                policy = policy.filter(f"HF:{feat}{op}{val}", condition)
            
            # Add Stress like V14 (CustomStress with aggravation)
            if global_stress != 1.0:
                from pycreditools.stress import AggravationStress
                stress_scenario = AggravationStress(
                    factor=global_stress
                )
                policy = policy.add_stress(stress_scenario)
            
            # Get approved population after HF (same as V14 df_clean_hf)
            sim_hf = policy.simulate(df)
            df_clean_hf = sim_hf.data[sim_hf.data["new_approval"] == 1.0].copy()
            
            # Run TradeoffAnalyzer for each score — EXACTLY like V14
            for score_col in scores:
                if score_col not in df.columns:
                    continue
                
                if len(df_clean_hf) == 0:
                    print(f"No approved rows after HF for {pol_name}/{score_col}")
                    continue
                
                cutoffs = np.linspace(
                    df_clean_hf[score_col].quantile(0.05),
                    df_clean_hf[score_col].quantile(0.95),
                    35
                ).astype(int).tolist()
                
                direction = ">="
                try:
                    import scipy.stats
                    target_col = pol_config.get("target")
                    if target_col and target_col in df_clean_hf.columns:
                        corr, _ = scipy.stats.spearmanr(df_clean_hf[score_col].fillna(0), df_clean_hf[target_col].fillna(0))
                        if corr > 0:
                            direction = "<="
                except Exception as e:
                    print(f"Error inferring direction for {score_col}: {e}")
                
                an = TradeoffAnalyzer(policy).vary_cutoff(score_col, cutoffs, direction=direction)
                res_df = an.run(df, parallel=False)
                
                cutoff_col = f"{score_col}_cutoff"
                for _, row in res_df.iterrows():
                    cutoff_val = row.get(cutoff_col, row.get("cutoff", 0))
                    appr = row.get("approval_rate", 0)
                    dr = row.get("default_rate", 0)
                    volume = int(appr * N)
                    
                    results.append({
                        "Curve": f"{pol_name} – {score_col}",
                        "Policy": pol_name,
                        "Score": score_col,
                        "Cutoff": cutoff_val,
                        "Stress": global_stress,
                        "Approval Rate (%)": appr * 100,
                        "Default Rate (%)": dr * 100,
                        "Volume": volume,
                    })
                
                print(f"[SIM] {pol_name}/{score_col}: {len(res_df)} scenarios, "
                      f"appr range {res_df['approval_rate'].min():.1%}–{res_df['approval_rate'].max():.1%}")
                
        except Exception as e:
            import traceback
            print(f"[ERROR] simulating {pol_name}: {e}")
            traceback.print_exc()
            
    if not results:
        return go.Figure(layout=dict(title="No results — check server logs.")), dmc.Alert("Simulation produced no results. Check that your policy columns exist in the dataset.", color="red"), html.Div()
        
    results_df = pd.DataFrame(results)
    
    # Filter scenarios to realistic bounds if we have a legacy reference
    if legacy_approval_rate > 0:
        min_appr = max(0.0, legacy_approval_rate - 0.20) * 100
        max_appr = min(1.0, legacy_approval_rate + 0.20) * 100
        results_df = results_df[
            (results_df["Approval Rate (%)"] >= min_appr) & 
            (results_df["Approval Rate (%)"] <= max_appr)
        ]
    
    fig = go.Figure()
    
    COLORS = ["#4dabf7", "#f783ac", "#69db7c", "#ffd43b", "#da77f2"]
    scenarios_table_rows = []
    
    for ci, curve_name in enumerate(results_df["Curve"].unique()):
        curve_df = results_df[results_df["Curve"] == curve_name].sort_values("Approval Rate (%)")
        color = COLORS[ci % len(COLORS)]
        
        # Efficient frontier line
        fig.add_trace(go.Scatter(
            x=curve_df["Approval Rate (%)"],
            y=curve_df["Default Rate (%)"],
            mode='lines+markers',
            name=curve_name,
            line=dict(width=2.5, color=color),
            marker=dict(size=5),
            customdata=curve_df[["Cutoff", "Score", "Stress", "Volume", "Policy"]].values,
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "Aprovação: %{x:.2f}%<br>"
                "Inadimplência: %{y:.2f}%<br>"
                "Cutoff: %{customdata[0]:.0f}<br>"
                "Volume: %{customdata[3]:,.0f}<extra></extra>"
            )
        ))
        
        # 3 Executive Scenarios (Conservative, Neutral, Aggressive) — same V14 logic
        if legacy_approval_rate > 0 and legacy_default_rate > 0:
            # Conservative: same approval rate as legacy
            pol_cons = curve_df.iloc[(curve_df["Approval Rate (%)"] - legacy_approval_rate*100).abs().argsort()[:1]]
            # Aggressive: same default rate as legacy
            pol_agr  = curve_df.iloc[(curve_df["Default Rate (%)"]  - legacy_default_rate*100).abs().argsort()[:1]]
            # Neutral: midpoint cutoff
            mid_cut  = (pol_cons["Cutoff"].iloc[0] + pol_agr["Cutoff"].iloc[0]) / 2
            pol_mid  = curve_df.iloc[(curve_df["Cutoff"] - mid_cut).abs().argsort()[:1]]
            
            for label, pol, mcolor, msym in [
                ("Conservadora", pol_cons, "gold", "star"),
                ("Agressiva", pol_agr, "tomato", "diamond"),
                ("Neutra", pol_mid, "mediumpurple", "circle"),
            ]:
                fig.add_trace(go.Scatter(
                    x=pol["Approval Rate (%)"],
                    y=pol["Default Rate (%)"],
                    mode='markers',
                    marker=dict(size=16, color=mcolor, symbol=msym,
                                line=dict(width=2, color='white')),
                    name=f"{label}: cutoff {pol['Cutoff'].iloc[0]:.0f}",
                    customdata=pol[["Cutoff", "Score", "Stress", "Volume", "Policy"]].values,
                    hovertemplate=(
                        f"<b>{label}</b><br>"
                        "Aprovação: %{x:.2f}%<br>"
                        "Inadimplência: %{y:.2f}%<br>"
                        "Cutoff: %{customdata[0]:.0f}<br>"
                        "Volume: %{customdata[3]:,.0f}<extra></extra>"
                    )
                ))
                scenarios_table_rows.append(
                    html.Tr([
                        html.Td(f"{label}", style={"color": mcolor, "fontWeight": "bold"}),
                        html.Td(curve_df["Score"].iloc[0]),
                        html.Td(f"{pol['Cutoff'].iloc[0]:.0f}"),
                        html.Td(f"{pol['Approval Rate (%)'].iloc[0]:.2f}%"),
                        html.Td(f"{pol['Default Rate (%)'].iloc[0]:.2f}%"),
                        html.Td(f"{pol['Volume'].iloc[0]:,.0f}"),
                    ])
                )
            
            segment_col = config.get("segment")
            if segment_col and segment_col in df.columns:
                from pycreditools import run_simulation, summarize_results
                from pycreditools.stages import CutoffStage
                from pycreditools.stress import AggravationStress
                import copy
                
                sim_policy = copy.deepcopy(policy)
                sim_policy.add_stage(CutoffStage(cutoffs={scores[0]: pol_mid["Cutoff"].iloc[0]}, name="Primary Score Cutoff"))
                sim_policy.add_stage(AggravationStress(factor=global_stress, name="Global Stress"))
                
                try:
                    sim_res = run_simulation(df, sim_policy, method="analytical")
                    seg_summary = summarize_results(sim_res, by=segment_col)
                    
                    seg_rows = []
                    for _, row in seg_summary.iterrows():
                        seg_rows.append(html.Tr([
                            html.Td(str(row[segment_col])),
                            html.Td(f"{row['Applicants']:,.0f}"),
                            html.Td(f"{row['Approved']:,.0f}"),
                            html.Td(f"{row.get('Bad_Rate', 0):.2%}")
                        ]))
                        
                    segment_breakdown_tables.append(
                        dmc.Card([
                            dmc.Text(f"Policy: {pol_name} (Neutral Scenario)", fw=600, mb="sm", c="grape"),
                            dmc.Table([
                                html.Thead(html.Tr([html.Th("Segment"), html.Th("Applicants"), html.Th("Approved"), html.Th("Bad Rate")])),
                                html.Tbody(seg_rows)
                            ], striped=True, withTableBorder=True)
                        ], withBorder=True, shadow="sm", radius="md", mb="md")
                    )
                except Exception as e:
                    print(f"Error calculating segment summary: {e}")
    
    # Legacy reference lines
    if legacy_approval_rate > 0:
        fig.add_vline(x=legacy_approval_rate*100, line_dash="dash", line_color="lime",
                      annotation_text=f"Legado Aprov. {legacy_approval_rate:.1%}", annotation_font_color="lime")
        fig.add_hline(y=legacy_default_rate*100, line_dash="dash", line_color="orangered",
                      annotation_text=f"Legado Inad. {legacy_default_rate:.1%}", annotation_font_color="orangered")
        
        scenarios_table_rows.append(
            html.Tr([
                html.Td("Legado (baseline)", style={"fontWeight": "bold"}),
                html.Td("—"),
                html.Td("—"),
                html.Td(f"{legacy_approval_rate*100:.2f}%", style={"fontWeight": "bold"}),
                html.Td(f"{legacy_default_rate*100:.2f}%", style={"fontWeight": "bold"}),
                html.Td(f"{int(legacy_approval_rate * N):,}"),
            ])
        )

    fig.update_layout(
        plot_bgcolor="rgba(26,27,30,1)",
        paper_bgcolor="rgba(26,27,30,0)",
        font=dict(color="#c1c2c5"),
        hovermode="closest",
        title=dict(text="Fronteira Eficiente – Stressed & Approved (DEV)", font=dict(size=18)),
        xaxis=dict(title="Taxa de Aprovação Global (% ToF)", ticksuffix="%",
                   gridcolor="rgba(255,255,255,0.07)", zeroline=False),
        yaxis=dict(title="Inadimplência Estressada (Swap-in x factor)", ticksuffix="%",
                   gridcolor="rgba(255,255,255,0.07)", zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0.3)", borderwidth=1),
    )
    
    # Build comparison table (V14 parity block)
    v14_neutral_appr  = 43.33
    v14_neutral_dr    = 13.06
    v14_neutral_cut   = 513
    v14_legacy_appr   = 43.74
    v14_legacy_dr     = 13.76

    parity_note = dmc.Alert([
        dmc.Text("Referência V14 (score_5, stress 1.2x):", fw=700, mb=4),
        dmc.Text(f"  Cenário Neutro → Cutoff ≈ {v14_neutral_cut}, Aprovação ≈ {v14_neutral_appr:.1f}%, Inad ≈ {v14_neutral_dr:.2f}%"),
        dmc.Text(f"  Legado         → Aprovação ≈ {v14_legacy_appr:.1f}%, Inad ≈ {v14_legacy_dr:.2f}%"),
    ], color="blue", title="Benchmark V14 Ground Truth", mb="md")

    scenarios_table = dmc.Table([
        html.Thead(html.Tr([
            html.Th("Cenário"), html.Th("Score"), html.Th("Cutoff"),
            html.Th("Aprov. Global"), html.Th("Inad. (Stressed)"), html.Th("Volume"),
        ])),
        html.Tbody(scenarios_table_rows)
    ], striped=True, highlightOnHover=True, withTableBorder=True)
    
    details_card = dmc.Card([
        parity_note,
        dmc.Text("As 3 Proposições Executivas", fw=700, size="xl", mb="sm", c="grape"),
        scenarios_table
    ], withBorder=True, shadow="md", radius="md", p="lg")
    
    segment_ui = html.Div()
    if segment_breakdown_tables:
        segment_ui = dmc.Card([
            dmc.Text("Segment Breakdown (Neutral Scenario)", fw=700, size="xl", mb="lg"),
            dmc.Grid([dmc.GridCol(t, span=12) for t in segment_breakdown_tables])
        ], withBorder=True, shadow="md", radius="md", p="lg")
        
    return fig, details_card, segment_ui

@app.callback(
    Output("user-override-container", "children"),
    Input("tradeoff-scatter-graph", "clickData")
)
def display_click_data(clickData):
    if clickData is None:
        return dmc.Text("Click on any point in the graph to override and elect a custom cutoff.", c="dimmed", fs="italic")
        
    point = clickData["points"][0]
    curve = point.get("customdata", [None, None, None])
    cutoff = curve[0] if len(curve) > 0 else "N/A"
    score_name = curve[1] if len(curve) > 1 else "N/A"
    stress = curve[2] if len(curve) > 2 else "N/A"
    
    curve_name = point.get("fullData", {}).get("name", "")
    # Parse the policy name from the curve name if possible (e.g. "Policy 1 - score_5")
    pol_name = curve_name.split(" – ")[0] if " – " in curve_name else curve_name
    
    return dmc.Card(
        [
            dmc.Text("Elected Operating Point (User Override)", fw=700, size="lg", mb="sm", color="orange"),
            dmc.Grid([
                dmc.GridCol([dmc.Text("Score Used", fw=500), dmc.Text(str(score_name))], span=3),
                dmc.GridCol([dmc.Text("Cutoff Selected", fw=500), dmc.Text(f"{cutoff:.2f}")], span=3),
                dmc.GridCol([dmc.Text("Approval Rate", fw=500), dmc.Text(f"{point['x']:.2f}%")], span=3),
                dmc.GridCol([dmc.Text("Default Rate (Stressed)", fw=500), dmc.Text(f"{point['y']:.2f}% (Stress: {stress}x)")], span=3),
            ]),
            dmc.Space(h="md"),
            dmc.Button("Confirm Custom Policy", id="confirm-cutoff-btn", color="orange", variant="light"),
            html.Div(id="confirm-cutoff-notification")
        ],
        withBorder=True, shadow="md", radius="md", p="md"
    )
        
@app.callback(
    Output("policies-store", "data", allow_duplicate=True),
    Output("confirm-cutoff-notification", "children"),
    Input("confirm-cutoff-btn", "n_clicks"),
    State("tradeoff-scatter-graph", "clickData"),
    State("policies-store", "data"),
    prevent_initial_call=True
)
def confirm_custom_cutoff(n_clicks, clickData, policies):
    if not n_clicks or not clickData or not policies:
        from dash.exceptions import PreventUpdate
        raise PreventUpdate
        
    point = clickData["points"][0]
    curve = point.get("customdata", [None, None, None])
    cutoff = curve[0] if len(curve) > 0 else None
    score_name = curve[1] if len(curve) > 1 else None
    
    curve_name = point.get("curveNumber", "")
    # Need to match curve to policy name.
    # The curve name is stored in the point info, actually we can get it from the figure's data array via name, but it is available in point['curveNumber'] ? No, we can get it from customdata or fullData.name. Wait, we added hovertemplate. 
    # Let's extract the policy name we used: pol_name = curve_name.split(" – ")[0]
    full_name = point.get("fullData", {}).get("name", "")
    pol_name = full_name.split(" – ")[0] if " – " in full_name else full_name
    
    # If the policy name doesn't match exactly, fallback to the last policy
    if pol_name not in policies:
        pol_name = list(policies.keys())[-1]
        
    if cutoff is not None and score_name is not None:
        # Check if a cutoff filter for this score already exists to replace it, otherwise add it
        stages = policies[pol_name].get("stages", [])
        existing_idx = next((i for i, stage in enumerate(stages) if stage["feature"] == score_name), None)
        
        new_stage = {
            "feature": score_name,
            "operator": ">=",
            "cutoff": cutoff
        }
        
        if existing_idx is not None:
            stages[existing_idx] = new_stage
        else:
            stages.append(new_stage)
            
        policies[pol_name]["stages"] = stages
        
        return policies, dmc.Notification(
            title="Success",
            id="notif-cutoff-success",
            action="show",
            message=f"Cutoff {cutoff:.0f} for {score_name} added to {pol_name}.",
            color="green",
            icon=DashIconify(icon="tabler:check")
        )
    return no_update, dmc.Notification(
        title="Error",
        id="notif-cutoff-error",
        action="show",
        message="Could not read cutoff data.",
        color="red",
        icon=DashIconify(icon="tabler:x")
    )
    try:
        import io
        import pandas as pd
        df = pd.read_json(io.StringIO(data_json), orient='split')
        
        total_n = len(df)
        
        rows = []
        rows.append(
            html.Tr([
                html.Td("Top of Funnel", style={"fontWeight": 500}),
                html.Td(f"{total_n:,}"),
                html.Td("100.0%"),
                html.Td("-")
            ])
        )
        
        cumulativo = pd.Series(True, index=df.index)
        prev_n = total_n
        
        for idx, (feat, op, val) in enumerate(valid_stages):
            if feat not in df.columns:
                continue
                
            if op == ">=": mask = df[feat] >= val
            elif op == "<=": mask = df[feat] <= val
            elif op == "==": mask = df[feat] == val
            else: mask = df[feat] >= val
                
            cumulativo = cumulativo & mask
            n = int(cumulativo.sum())
            
            delta_pct = (n - prev_n) / prev_n if prev_n > 0 else 0
            
            rows.append(
                html.Tr([
                    html.Td(f"Filter: {feat} {op} {val}"),
                    html.Td(f"{n:,}"),
                    html.Td(f"{n / total_n:.1%}"),
                    html.Td(f"{delta_pct:+.1%}", style={"color": "red" if delta_pct < 0 else "inherit"})
                ])
            )
            prev_n = n
            
        table = dmc.Table([
            html.Thead(html.Tr([
                html.Th("Etapa"),
                html.Th("Volume"),
                html.Th("% Funil"),
            ])),
            html.Tbody(rows)
        ], striped=True, highlightOnHover=True, withTableBorder=True)
        
        return html.Div([table])
        
    except Exception as e:
        return dmc.Alert(f"Error calculating funnel: {e}", color="red")

@app.callback(
    Output("risk-tiers-table-container", "children"),
    Input("generate-risk-tiers-btn", "n_clicks"),
    State("risk-scores-select", "value"),
    State("risk-target-select", "value"),
    State("max-tiers-input", "value"),
    State("dataset-store", "data"),
    State("dataset-config-store", "data"),
    prevent_initial_call=True
)
def generate_risk_tiers(n_clicks, scores, target, max_tiers, data_json, config):
    if not n_clicks or not scores or not target or not data_json:
        return dmc.Alert("Please select scores, target, and upload data first.", color="yellow")
        
    try:
        import io
        import pandas as pd
        from pycreditools.grouping import fit_risk_groups
        
        df_full = pd.read_json(io.StringIO(data_json), orient='split')
        
        config = config or {}
        sample_col = config.get("sample")
        if sample_col and sample_col in df_full.columns:
            df = df_full[df_full[sample_col].astype(str).str.upper() == "DEV"].copy()
            if len(df) == 0:
                df = df_full.copy()
        else:
            df = df_full.copy()
            
        res = fit_risk_groups(
            data=df,
            score_cols=scores,
            default_col=target,
            max_groups=max_tiers,
            bins=20,
            min_vol_ratio=0.05
        )
        
        groups_df = res.groups
        # The result dataframe has: risk_rating, volume, pd
        
        # We map rating 1, 2, 3.. to A, B, C..
        rating_letters = {1: "A", 2: "B", 3: "C", 4: "D", 5: "E", 6: "F", 7: "G", 8: "H"}
        groups_df["Rating"] = groups_df["risk_rating"].map(lambda x: rating_letters.get(x, str(x)))
        
        total_vol = groups_df["volume"].sum()
        
        rows = []
        for _, row in groups_df.iterrows():
            vol = row["volume"]
            bad_rate = row["pd"]
            pct_vol = vol / total_vol if total_vol > 0 else 0
            
            rows.append(
                html.Tr([
                    html.Td(row["Rating"], style={"fontWeight": "bold"}),
                    html.Td(f"{vol:,.0f}"),
                    html.Td(f"{pct_vol:.1%}"),
                    html.Td(f"{bad_rate:.2%}", style={"color": "red" if bad_rate > 0.15 else "inherit"})
                ])
            )
            
        table = dmc.Table([
            html.Thead(html.Tr([
                html.Th("Risk Group (Rating)"),
                html.Th("Volume (Applicants)"),
                html.Th("% of Approved"),
                html.Th("Default Rate")
            ])),
            html.Tbody(rows)
        ], striped=True, highlightOnHover=True, withTableBorder=True)
        
        time_col = config.get("time")
        vintage_chart = None
        if time_col and time_col in res.data.columns:
            import plotly.express as px
            # res.data has risk_rating, default_col, time_col
            res_data = res.data.copy()
            res_data["Rating"] = res_data["risk_rating"].map(lambda x: rating_letters.get(x, str(x)))
            vintage_df = res_data.groupby([time_col, "Rating"])[target].mean().reset_index()
            
            fig = px.line(
                vintage_df, 
                x=time_col, 
                y=target, 
                color="Rating",
                title=f"Vintage Stability ({time_col})",
                markers=True,
                color_discrete_sequence=["#4dabf7", "#f783ac", "#69db7c", "#ffd43b", "#da77f2", "#3bc9db", "#ffa94d", "#c0eb75"]
            )
            fig.update_layout(
                plot_bgcolor="rgba(26,27,30,1)",
                paper_bgcolor="rgba(26,27,30,0)",
                font=dict(color="#c1c2c5"),
                xaxis_title="Vintage",
                yaxis_title="Default Rate",
                yaxis_tickformat='.1%',
                legend_title="Risk Group"
            )
            from dash import dcc
            vintage_chart = dcc.Graph(figure=fig)
        
        children = [
            dmc.Text(f"Clustered into {res.n_groups} distinct risk groups based on '{', '.join(scores)}'", c="green", fw=500, mb="sm"),
            table
        ]
        if vintage_chart:
            children.append(dmc.Space(h="xl"))
            children.append(vintage_chart)
            
        return html.Div(children)
        
    except Exception as e:
        return dmc.Alert(f"Error generating risk tiers: {str(e)}", color="red")
@app.callback(
    Output("download-rules", "data"),
    Input("export-rules-btn", "n_clicks"),
    State("policies-store", "data"),
    prevent_initial_call=True
)
def export_rules(n_clicks, policies):
    if not policies:
        from dash.exceptions import PreventUpdate
        raise PreventUpdate
    import json
    return dict(content=json.dumps(policies, indent=4), filename="pycreditools_policies.json")

@app.callback(
    Output("download-base", "data"),
    Input("export-base-btn", "n_clicks"),
    State("dataset-store", "data"),
    prevent_initial_call=True
)
def export_base(n_clicks, data_json):
    if not data_json:
        from dash.exceptions import PreventUpdate
        raise PreventUpdate
    import io
    import pandas as pd
    df = pd.read_json(io.StringIO(data_json), orient='split')
    return dict(content=df.to_csv(index=False), filename="analytical_base_pycreditools.csv")

@app.callback(
    Output("live-funnel-container", "children"),
    Input({"type": "stage-feature", "index": ALL}, "value"),
    Input({"type": "stage-operator", "index": ALL}, "value"),
    Input({"type": "stage-cutoff", "index": ALL}, "value"),
    Input("dataset-store", "data")
)
def update_live_funnel(features, ops, cutoffs, data_json):
    if not data_json:
        return dmc.Text("Please upload data first to see the live funnel.", c="dimmed", fs="italic")
        
    valid_stages = []
    for f, o, c in zip(features, ops, cutoffs):
        if f and o and c is not None:
            valid_stages.append((f, o, c))
            
    if not valid_stages:
        return dmc.Text("Add filters to see the approval volume cascading down in real-time.", c="dimmed", fs="italic")
        
    try:
        import io
        import pandas as pd
        df = pd.read_json(io.StringIO(data_json), orient='split')
        
        total_n = len(df)
        
        rows = []
        rows.append(
            html.Tr([
                html.Td("Top of Funnel", style={"fontWeight": 500}),
                html.Td(f"{total_n:,}"),
                html.Td("100.0%"),
                html.Td("-")
            ])
        )
        
        cumulativo = pd.Series(True, index=df.index)
        prev_n = total_n
        
        for idx, (feat, op, val) in enumerate(valid_stages):
            if feat not in df.columns:
                continue
                
            if op == ">=": mask = df[feat] >= val
            elif op == "<=": mask = df[feat] <= val
            elif op == "==": mask = df[feat] == val
            else: mask = df[feat] >= val
                
            cumulativo = cumulativo & mask
            n = int(cumulativo.sum())
            
            delta_pct = (n - prev_n) / prev_n if prev_n > 0 else 0
            
            rows.append(
                html.Tr([
                    html.Td(f"Filter: {feat} {op} {val}"),
                    html.Td(f"{n:,}"),
                    html.Td(f"{n / total_n:.1%}"),
                    html.Td(f"{delta_pct:+.1%}", style={"color": "red" if delta_pct < 0 else "inherit"})
                ])
            )
            prev_n = n
            
        table = dmc.Table([
            html.Thead(html.Tr([
                html.Th("Etapa"),
                html.Th("Volume"),
                html.Th("% Funil"),
            ])),
            html.Tbody(rows)
        ], striped=True, highlightOnHover=True, withTableBorder=True)
        
        return html.Div([table])
        
    except Exception as e:
        return dmc.Alert(f"Error calculating funnel: {e}", color="red")


# --- Score Evaluation Callbacks ---

@app.callback(
    Output("eval-ks-bar-graph", "figure"),
    Output("eval-vintage-graph", "figure"),
    Output("eval-decile-table-container", "children"),
    Input("eval-sample-control", "value"),
    Input("eval-segment-control", "value"),
    State("dataset-store", "data"),
    State("dataset-config-store", "data")
)
def update_evaluation_tab(sample_filter, segment_filter, data_json, config):
    if not data_json:
        return px.bar(title="Upload data first"), px.line(title="Upload data first"), dmc.Text("Upload data first.")
        
    df = pd.read_json(io.StringIO(data_json), orient='split')
    config = config or {}
    
    sample_col = config.get("sample")
    time_col = config.get("time")
    target_col = config.get("target")
    segment_col = config.get("segment")
    
    if not target_col or target_col not in df.columns:
        return px.bar(title="Target column not configured."), px.line(title="Target column not configured."), dmc.Text("Please configure the Target column in Ingestion.")
        
    # Automatically select all numeric columns excluding technical ones
    exclude_cols = {target_col, time_col, sample_col, segment_col, config.get("approved"), config.get("hired")}
    scores = [c for c in df.select_dtypes(include=np.number).columns if c not in exclude_cols]
    
    if not scores:
        return px.bar(title="No numeric scores found"), px.line(title="No numeric scores found"), dmc.Text("No numeric columns available to evaluate.")

    if segment_col and segment_col in df.columns and segment_filter and segment_filter != "All":
        df = df[df[segment_col].astype(str) == segment_filter].copy()
        
    # Apply sample filter
    if sample_col and sample_col in df.columns:
        if sample_filter == "DEV":
            df = df[df[sample_col].astype(str).str.upper() == "DEV"].copy()
        elif sample_filter == "OOT":
            df = df[df[sample_col].astype(str).str.upper() == "OOT"].copy()
    elif time_col and time_col in df.columns:
        # Auto-split based on time
        unique_dates = sorted(df[time_col].dropna().unique())
        if len(unique_dates) > 1:
            oot_date = unique_dates[-1] # The latest vintage is OOT
            if sample_filter == "DEV":
                df = df[df[time_col] < oot_date].copy()
            elif sample_filter == "OOT":
                df = df[df[time_col] >= oot_date].copy()
            
    if len(df) == 0:
        return px.bar(title="No data for this sample."), px.line(title="No data for this sample."), dmc.Text("No data available.")

    from pycreditools import ModelEvaluator
    
    # 1. Global KS Comparison
    evaluator = ModelEvaluator(df, scores, target_col)
    try:
        ks_dict = evaluator.compute_ks()
        ks_df = pd.DataFrame(list(ks_dict.items()), columns=["Score", "KS"])
        fig_ks = px.bar(ks_df, x="Score", y="KS", title=f"Global KS ({sample_filter})", color="Score", text_auto=".1%")
        fig_ks.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="white")
    except Exception as e:
        fig_ks = px.bar(title=f"Error computing KS: {e}")
        
    # 2. KS Over Time (Vintage Stability)
    fig_vintage = px.line(title="Time/Vintage column not configured")
    if time_col and time_col in df.columns:
        try:
            records = []
            for vintage, group in df.groupby(time_col):
                if len(group) > 50: # Need some minimum sample for valid KS
                    ev = ModelEvaluator(group, scores, target_col)
                    v_ks = ev.compute_ks()
                    for s, val in v_ks.items():
                        records.append({"Vintage": vintage, "Score": s, "KS": val})
            
            if records:
                v_df = pd.DataFrame(records).sort_values("Vintage")
                fig_vintage = px.line(v_df, x="Vintage", y="KS", color="Score", title=f"KS Over Time ({sample_filter})", markers=True)
                fig_vintage.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="white")
        except Exception as e:
            fig_vintage = px.line(title=f"Error computing Vintage KS: {e}")
            
    # 3. Decile Table (Matrix Form)
    decile_ui = dmc.Text("Calculating deciles...")
    try:
        import scipy.stats
        decile_data = {"Decile": [f"{i} (Melhor)" if i==1 else f"{i} (Pior)" if i==10 else str(i) for i in range(1, 11)]}
        for s in scores:
            try:
                corr, _ = scipy.stats.spearmanr(df[s].fillna(0), df[target_col].fillna(0))
                is_lower_better = corr > 0
                df_sorted = df.sort_values(by=s, ascending=is_lower_better)
                df_sorted['decile'] = pd.qcut(np.arange(len(df_sorted)), 10, labels=False) + 1
                pd_per_decile = df_sorted.groupby('decile')[target_col].mean()
                decile_data[s] = [pd_per_decile.get(i, np.nan) for i in range(1, 11)]
            except Exception:
                decile_data[s] = [np.nan] * 10
            
        dec_df = pd.DataFrame(decile_data)
        
        # Formatting the table
        header = [html.Th(col) for col in dec_df.columns]
        rows = []
        for _, row in dec_df.iterrows():
            tds = []
            for col in dec_df.columns:
                val = row[col]
                if isinstance(val, float):
                    color = "red" if val > 0.15 else ("green" if val < 0.05 else "inherit")
                    tds.append(html.Td(f"{val:.2%}", style={"color": color}))
                else:
                    tds.append(html.Td(str(val), style={"fontWeight": "bold"}))
            rows.append(html.Tr(tds))
            
        decile_ui = dmc.ScrollArea(
            dmc.Table([
                html.Thead(html.Tr(header)),
                html.Tbody(rows)
            ], striped=True, highlightOnHover=True, withTableBorder=True)
        )
    except Exception as e:
        decile_ui = dmc.Alert(f"Error computing decile matrix: {e}", color="red")
            
    return fig_ks, fig_vintage, decile_ui


@app.callback(
    Output("eval-matrix-table-container", "children"),
    Input("eval-matrix-score-a", "value"),
    Input("eval-matrix-score-b", "value"),
    Input("eval-matrix-buckets-a", "value"),
    Input("eval-matrix-buckets-b", "value"),
    Input("eval-segment-control", "value"),
    State("dataset-store", "data"),
    State("dataset-config-store", "data")
)
def update_matrix_tab(score_a, score_b, buckets_a, buckets_b, segment_filter, data_json, config):
    if not score_a or not score_b or not data_json:
        return dmc.Text("Select Score A and Score B to view the matrix.")
        
    df = pd.read_json(io.StringIO(data_json), orient='split')
    config = config or {}
    target_col = config.get("target")
    
    if not target_col or target_col not in df.columns:
        return dmc.Alert("Target column not found in dataset.", color="red")
        
    segment_col = config.get("segment")
    if segment_col and segment_col in df.columns and segment_filter and segment_filter != "All":
        df = df[df[segment_col].astype(str) == segment_filter].copy()
        
    if score_a not in df.columns or score_b not in df.columns:
        return dmc.Alert("Selected scores not found in dataset.", color="red")
        
    if len(df) == 0:
        return dmc.Alert("No data available for this segment.", color="yellow")
        
    # Group by quantiles or custom bins
    try:
        import scipy.stats
        
        def assign_buckets(val, df, score, target_col):
            corr, _ = scipy.stats.spearmanr(df[score].fillna(0), df[target_col].fillna(0))
            is_lower_better = corr > 0
            
            try:
                if "," in str(val):
                    bins = [-np.inf] + [float(x.strip()) for x in str(val).split(",") if x.strip()] + [np.inf]
                    bins = sorted(list(set(bins)))
                    bucket = pd.cut(df[score], bins=bins, labels=False) + 1
                else:
                    q = int(str(val).strip())
                    bucket = pd.qcut(df[score], q=q, labels=False, duplicates='drop') + 1
            except Exception:
                bucket = pd.qcut(df[score], q=10, labels=False, duplicates='drop') + 1
                
            # If higher score = better (is_lower_better == False), then bucket 1 (lowest numeric score) is the WORST.
            # Usually users want bucket 1 to be the BEST. So we invert it.
            # If lower score = better (is_lower_better == True), then bucket 1 (lowest numeric score) is the BEST. We don't invert.
            if not is_lower_better:
                max_b = bucket.max()
                bucket = (max_b - bucket) + 1
                
            return bucket
            
        df["_bucket_a"] = assign_buckets(buckets_a, df, score_a, target_col)
        df["_bucket_b"] = assign_buckets(buckets_b, df, score_b, target_col)
        
        # Calculate PD and Volume per cell
        matrix = df.groupby(["_bucket_a", "_bucket_b"]).agg(
            Vol=(target_col, "count"),
            PD=(target_col, "mean")
        ).reset_index()
        
        # Pivot table for PD
        pd_pivot = matrix.pivot(index="_bucket_a", columns="_bucket_b", values="PD")
        vol_pivot = matrix.pivot(index="_bucket_a", columns="_bucket_b", values="Vol")
        
        # Create HTML Table
        header = [html.Th(f"B {c}") for c in pd_pivot.columns]
        header.insert(0, html.Th("Score A \\ B"))
        
        rows = []
        import matplotlib
        import matplotlib.cm as cm
        cmap = cm.get_cmap("RdYlGn_r") # Red (bad) to Green (good) reversed? No, RdYlGn: Green=0, Red=1. Wait, high PD is bad (Red). RdYlGn_r: 0=Green, 1=Red.
        
        # Find global min and max PD for color scaling
        min_pd = matrix["PD"].min()
        max_pd = matrix["PD"].max()
        
        for r_idx in pd_pivot.index:
            tds = [html.Th(f"A {r_idx}")]
            for c_idx in pd_pivot.columns:
                pd_val = pd_pivot.loc[r_idx, c_idx]
                vol_val = vol_pivot.loc[r_idx, c_idx]
                
                if pd.isna(pd_val):
                    tds.append(html.Td("-", style={"textAlign": "center"}))
                else:
                    # Calculate color
                    # normalize
                    norm = (pd_val - min_pd) / (max_pd - min_pd + 1e-9)
                    rgba = cmap(norm)
                    color = f"rgba({int(rgba[0]*255)}, {int(rgba[1]*255)}, {int(rgba[2]*255)}, 0.8)"
                    
                    cell_content = dmc.Stack([
                        dmc.Text(f"{pd_val:.1%}", fw=600, size="sm"),
                        dmc.Text(f"Vol: {vol_val:,.0f}", size="xs", c="dimmed")
                    ], gap=0, align="center")
                    
                    tds.append(html.Td(cell_content, style={"backgroundColor": color, "textAlign": "center"}))
            rows.append(html.Tr(tds))
            
        return dmc.ScrollArea(
            dmc.Table([
                html.Thead(html.Tr(header)),
                html.Tbody(rows)
            ], withTableBorder=True, withColumnBorders=True)
        )
        
    except Exception as e:
        return dmc.Alert(f"Error calculating matrix: {e}", color="red")

@app.callback(
    Output("policies-store", "data", allow_duplicate=True),
    Output("simulation-click-feedback", "children"),
    Input("tradeoff-scatter-graph", "clickData"),
    State("policies-store", "data"),
    prevent_initial_call=True
)
def save_cutoff_to_policy(clickData, policies):
    if not clickData or not policies:
        from dash.exceptions import PreventUpdate
        raise PreventUpdate
        
    point = clickData["points"][0]
    customdata = point.get("customdata")
    if not customdata or len(customdata) < 5:
        from dash.exceptions import PreventUpdate
        raise PreventUpdate
        
    cutoff = customdata[0]
    score_col = customdata[1]
    pol_name = customdata[4]
    
    if pol_name in policies:
        pol = policies[pol_name]
        stages = pol.get("stages", [])
        
        # Check if score_col is already an HF
        existing = next((i for i, s in enumerate(stages) if s["feature"] == score_col), None)
        if existing is not None:
            stages[existing]["cutoff"] = cutoff
            stages[existing]["operator"] = ">="
        else:
            stages.append({"feature": score_col, "operator": ">=", "cutoff": cutoff})
            
        policies[pol_name]["stages"] = stages
        
        return policies, dmc.Notification(
            title="Policy Updated",
            id="notif-cutoff-added",
            action="show",
            message=f"Added cutoff {cutoff:g} for '{score_col}' in '{pol_name}'.",
            color="blue",
            icon=DashIconify(icon="tabler:check")
        )
    
    from dash.exceptions import PreventUpdate
    raise PreventUpdate
