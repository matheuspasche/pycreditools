from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify

def layout(columns=None):
    cols = columns or []
    return dmc.Container(
        [
            dmc.Title("Policy Studio", order=2, mb="md"),
            dmc.Text(
                "Build your credit policies visually. Add rules and configure your policy parameters.",
                mb="xl",
                c="dimmed"
            ),
            
            dmc.Grid(
                [
                    dmc.GridCol(
                        [
                            dmc.Card(
                                [
                                    dmc.Text("Suas Policies", fw=500, size="lg", mb="md"),
                                    dmc.Button("New Policy", id="new-policy-btn", fullWidth=True, variant="outline", leftSection=DashIconify(icon="tabler:plus"), mb="md"),
                                    html.Div(id="saved-policies-list", children=[
                                        dmc.Text("No policies saved yet.", c="dimmed", fs="italic", size="sm")
                                    ])
                                ],
                                withBorder=True, shadow="sm", radius="md", style={"minHeight": "400px"}
                            )
                        ],
                        span=2
                    ),
                    dmc.GridCol(
                        [
                            dmc.Card(
                                [
                                    dmc.Text("Policy Settings", fw=500, size="lg", mb="md"),
                                    dmc.TextInput(id="policy-name-input", label="Policy Name", placeholder="e.g. Aggressive Policy 1", mb="sm"),
                                    dmc.Select(
                                        id="target-col-select",
                                        label="Target (Default) Column",
                                        data=cols,
                                        searchable=True,
                                        mb="sm"
                                    ),
                                    dmc.MultiSelect(
                                        id="score-cols-select",
                                        label="Candidate Score Columns",
                                        description="We will generate an efficient frontier for each selected score.",
                                        data=cols,
                                        searchable=True,
                                        mb="sm"
                                    )
                                ],
                                withBorder=True,
                                shadow="sm",
                                radius="md",
                                mb="md"
                            )
                        ],
                        span=3
                    ),
                    dmc.GridCol(
                        [
                            dmc.Card(
                                [
                                    dmc.Group(
                                        [
                                            dmc.Text("Hard Filters / Base Cutoffs", fw=500, size="lg"),
                                            dmc.Button("Add Filter", id="add-stage-btn", variant="light", leftSection=DashIconify(icon="tabler:plus"))
                                        ],
                                        justify="space-between",
                                        mb="md"
                                    ),
                                    html.Div(id="stages-container", children=[]),
                                ],
                                withBorder=True,
                                shadow="sm",
                                radius="md",
                                mb="md"
                            ),
                            dmc.Button("Save Policy Setup", id="save-policy-btn", fullWidth=True, color="blue", size="lg")
                        ],
                        span=4
                    ),
                    dmc.GridCol(
                        [
                            dmc.Card(
                                [
                                    dmc.Text("Live Funnel Preview", fw=500, size="lg", mb="md"),
                                    html.Div(id="live-funnel-container", children=[
                                        dmc.Text("Add filters to see the approval volume cascading down in real-time.", c="dimmed", fs="italic")
                                    ])
                                ],
                                withBorder=True,
                                shadow="sm",
                                radius="md",
                                style={"minHeight": "400px"}
                            )
                        ],
                        span=3
                    )
                ]
            ),
            
            html.Div(id="studio-notifications")
        ],
        fluid=True,
        p="md"
    )
