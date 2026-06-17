from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify

def layout():
    return dmc.Container(
        [
            dmc.Title("Simulation & Trade-off", order=2, mb="md"),
            dmc.Text(
                "Run simulations on all saved policies to visualize the trade-off between Approval Rate and Default Rate.",
                mb="xl",
                c="dimmed"
            ),
            
            dmc.Group(
                [
                    dmc.NumberInput(
                        id="stress-factor-input",
                        label="Global Stress Factor",
                        description="e.g. 1.25 for a 25% PD increase",
                        value=1.0,
                        step=0.05,
                        min=1.0,
                        style={"width": "250px"}
                    ),
                    dmc.Button(
                        "Run Simulations", 
                        id="run-simulations-btn", 
                        color="grape", 
                        size="md",
                        leftSection=DashIconify(icon="tabler:player-play")
                    ),
                    dmc.Button(
                        "Export Rules (JSON)", 
                        id="export-rules-btn", 
                        variant="outline",
                        leftSection=DashIconify(icon="tabler:file-code")
                    ),
                    dmc.Button(
                        "Export Analytical Base", 
                        id="export-base-btn", 
                        variant="outline",
                        leftSection=DashIconify(icon="tabler:file-spreadsheet")
                    ),
                    dcc.Download(id="download-rules"),
                    dcc.Download(id="download-base")
                ],
                mb="xl"
            ),
            
            dmc.Card(
                [
                    dmc.LoadingOverlay(visible=False, id="loading-simulations"),
                    dmc.Text("Approval vs Default Trade-off", fw=500, mb="md"),
                    dcc.Graph(id="tradeoff-scatter-graph", style={"height": "500px"})
                ],
                withBorder=True,
                shadow="sm",
                radius="md",
                style={"position": "relative"}
            ),
            
            html.Div(id="simulation-click-feedback"),
            html.Div(id="simulation-segment-container", style={"marginTop": "20px"}),
            
            dmc.Space(h="xl"),
            
            html.Div(id="simulation-details-container"),
            dmc.Space(h="xl"),
            html.Div(id="user-override-container")
        ],
        fluid=True,
        p="md"
    )
