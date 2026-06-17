from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify

def layout():
    return dmc.Container(
        [
            dmc.Title("Data Ingestion", order=2, mb="md"),
            dmc.Text(
                "Upload a historical dataset or synthetic data containing candidate scores and actual default flags. "
                "The file must be a CSV or Parquet format.",
                mb="xl",
                c="dimmed"
            ),
            dmc.Button("Test Load", id="test-load-btn", style={"display": "none"}),
            
            dcc.Upload(
                id='upload-data',
                children=dmc.Group(
                    [
                        dmc.ThemeIcon(
                            DashIconify(icon="tabler:cloud-upload", width=30),
                            size="xl", variant="light", color="blue"
                        ),
                        html.Div([
                            dmc.Text("Drag and Drop or Click to Select File", size="lg", fw=500),
                            dmc.Text("Supported formats: .csv, .parquet", size="sm", c="dimmed")
                        ])
                    ],
                    align="center", justify="center", style={"height": "150px", "border": "2px dashed #4dabf7", "borderRadius": "8px", "cursor": "pointer"}
                ),
                multiple=False
            ),
            
            dmc.Space(h="xl"),
            
            html.Div(
                [
                    dmc.LoadingOverlay(visible=False, id="loading-data-preview"),
                    html.Div(id="data-preview-container")
                ],
                style={"position": "relative", "minHeight": "100px"}
            )
        ],
        fluid=True,
        p="md"
    )
