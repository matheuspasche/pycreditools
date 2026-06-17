from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify

def layout(columns=None, segments=None):
    columns = columns or []
    segments = segments or []
    
    segment_data = [{"label": "All Segments", "value": "All"}] + segments
    return dmc.Container(
        [
            dmc.Title("Score Evaluation", order=2, mb="md"),
            dmc.Text(
                "Evaluate the predictive power of your scores through KS analysis, vintage stability, and decile tables.",
                mb="xl",
                c="dimmed"
            ),
            
            dmc.Card(
                [
                    dmc.Text("Analysis Settings", fw=600, mb="md"),
                    dmc.Grid(
                        [
                            dmc.GridCol(
                                dmc.Select(
                                    id="eval-segment-control",
                                    label="Segment Filter",
                                    description="Filter by Store/Channel",
                                    data=segment_data,
                                    value="All",
                                    searchable=True,
                                    clearable=False
                                ),
                                span=3
                            ),
                            dmc.GridCol(
                                dmc.Select(
                                    id="eval-sample-control",
                                    label="Sample Filter",
                                    description="Filter by DEV/OOT",
                                    data=[
                                        {"label": "All Data", "value": "All"},
                                        {"label": "DEV Only", "value": "DEV"},
                                        {"label": "OOT Only", "value": "OOT"}
                                    ],
                                    value="All"
                                ),
                                span=2
                            )
                        ]
                    )
                ],
                withBorder=True, shadow="sm", radius="md", mb="xl"
            ),
            
            html.Div(
                [
                    dmc.LoadingOverlay(
                        id="loading-eval",
                        visible=False
                    ),
                    dmc.Grid(
                        [
                            dmc.GridCol(
                                dmc.Card(
                                    [
                                        dmc.Text("Global KS Comparison", fw=500, mb="sm"),
                                        dcc.Graph(id="eval-ks-bar-graph", style={"height": "350px"})
                                    ],
                                    withBorder=True, shadow="sm", radius="md"
                                ),
                                span=4
                            ),
                            dmc.GridCol(
                                dmc.Card(
                                    [
                                        dmc.Text("KS Over Time (Vintage Stability)", fw=500, mb="sm"),
                                        dcc.Graph(id="eval-vintage-graph", style={"height": "350px"})
                                    ],
                                    withBorder=True, shadow="sm", radius="md"
                                ),
                                span=8
                            )
                        ],
                        mb="xl"
                    ),
                    
                    dmc.Card(
                        [
                            dmc.Text("Decile Table", fw=500, mb="md"),
                            html.Div(id="eval-decile-table-container")
                        ],
                        withBorder=True, shadow="sm", radius="md", mb="xl"
                    ),
                    
                    dmc.Card(
                        [
                            dmc.Text("Dual-Matrix (Bivariate Analysis)", fw=500, mb="md"),
                            dmc.Grid(
                                [
                                    dmc.GridCol(
                                        dmc.Select(
                                            id="eval-matrix-score-a",
                                            label="Score A (Rows)",
                                            data=columns,
                                            searchable=True,
                                            clearable=True
                                        ),
                                        span=3
                                    ),
                                    dmc.GridCol(
                                        dmc.Select(
                                            id="eval-matrix-score-b",
                                            label="Score B (Columns)",
                                            data=columns,
                                            searchable=True,
                                            clearable=True
                                        ),
                                        span=3
                                    ),
                                    dmc.GridCol(
                                        dmc.TextInput(
                                            id="eval-matrix-buckets-a",
                                            label="Buckets / Bins (Score A)",
                                            description="E.g. '10' or '100, 300, 500'",
                                            value="10"
                                        ),
                                        span=2
                                    ),
                                    dmc.GridCol(
                                        dmc.TextInput(
                                            id="eval-matrix-buckets-b",
                                            label="Buckets / Bins (Score B)",
                                            description="E.g. '10' or '100, 300, 500'",
                                            value="10"
                                        ),
                                        span=2
                                    )
                                ], mb="lg"
                            ),
                            html.Div(id="eval-matrix-table-container")
                        ],
                        withBorder=True, shadow="sm", radius="md"
                    )
                ],
                style={"position": "relative"}
            )
        ],
        fluid=True,
        p="md"
    )
