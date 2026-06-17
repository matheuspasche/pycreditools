import dash_mantine_components as dmc
from dash import html, dcc
from dash_iconify import DashIconify

def layout(columns=None, default_target=None, default_scores=None):
    cols = columns or []
    return dmc.Container(
        [
            dmc.Title("Risk Tier Clustering", order=2, mb="md"),
            dmc.Text("Dynamically generate and configure risk groups (A, B, C, etc.) from the elected operating point.", c="dimmed", mb="xl"),
            
            dmc.Grid(
                [
                    dmc.GridCol(
                        [
                            dmc.Card(
                                [
                                    dmc.Text("Clustering Parameters", fw=700, size="lg", mb="md"),
                                    dmc.MultiSelect(
                                        id="risk-scores-select",
                                        label="Select Scores to Matrix (Matriciar)",
                                        description="Select one or more scores to cluster (e.g. Legacy + New Score)",
                                        placeholder="Select scores",
                                        data=cols,
                                        value=default_scores or [],
                                        searchable=True,
                                        mb="md"
                                    ),
                                    dmc.Select(
                                        id="risk-target-select",
                                        label="Target (Default) Column",
                                        placeholder="Select target",
                                        data=cols,
                                        value=default_target,
                                        searchable=True,
                                        mb="md"
                                    ),
                                    dmc.NumberInput(
                                        id="max-tiers-input",
                                        label="Number of Risk Tiers",
                                        description="Maximum number of groups to split the approved population into",
                                        value=5,
                                        min=2,
                                        max=10,
                                        mb="md"
                                    ),
                                    dmc.Button(
                                        "Generate Risk Tiers",
                                        id="generate-risk-tiers-btn",
                                        leftSection=DashIconify(icon="tabler:wand"),
                                        fullWidth=True,
                                        color="grape"
                                    )
                                ],
                                withBorder=True, shadow="sm", radius="md", p="md"
                            )
                        ],
                        span=4
                    ),
                    dmc.GridCol(
                        [
                            dmc.Card(
                                [
                                    dmc.Text("Risk Groups Summary", fw=700, size="lg", mb="md"),
                                    html.Div(id="risk-tiers-table-container", children=[
                                        dmc.Alert(
                                            "Awaiting calculation. Please configure parameters and generate tiers.",
                                            color="blue",
                                            title="Info"
                                        )
                                    ])
                                ],
                                withBorder=True, shadow="sm", radius="md", p="md"
                            )
                        ],
                        span=8
                    )
                ]
            )
        ],
        fluid=True,
        p="md"
    )
