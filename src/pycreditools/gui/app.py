import dash
import dash_mantine_components as dmc
from dash import html, dcc, _dash_renderer

_dash_renderer._set_react_version("18.2.0")

app = dash.Dash(
    __name__,
    external_stylesheets=[
        "https://unpkg.com/@mantine/dates@7/styles.css",
        "https://unpkg.com/@mantine/code-highlight@7/styles.css",
        "https://unpkg.com/@mantine/charts@7/styles.css",
        "https://unpkg.com/@mantine/carousel@7/styles.css",
        "https://unpkg.com/@mantine/notifications@7/styles.css",
        "https://unpkg.com/@mantine/nprogress@7/styles.css",
    ],
    suppress_callback_exceptions=True
)

app.title = "Pycreditools Studio"

def create_layout():
    return dmc.MantineProvider(
        id="mantine-provider",
        forceColorScheme="dark",
        theme={
            "primaryColor": "blue",
            "fontFamily": "Inter, sans-serif",
            "components": {
                "Card": {"defaultProps": {"shadow": "sm", "radius": "md", "withBorder": True}},
                "Button": {"defaultProps": {"radius": "md"}},
            }
        },
        children=[
            dmc.NotificationProvider(),
            dmc.AppShell(
                [
                    dmc.AppShellHeader(
                        dmc.Group(
                            [
                                dmc.Title("Pycreditools Studio", order=3),
                                dmc.Badge("No-Code", color="blue", variant="light"),
                            ],
                            h="100%",
                            px="md",
                            align="center"
                        ),
                    ),
                    dmc.AppShellNavbar(
                        [
                            dcc.Link(dmc.NavLink(label="Data Ingestion", active=True), href="/"),
                            dcc.Link(dmc.NavLink(label="Policy Studio"), href="/studio"),
                            dcc.Link(dmc.NavLink(label="Score Evaluation"), href="/evaluation"),
                            dcc.Link(dmc.NavLink(label="Simulation & Trade-off"), href="/simulation"),
                            dcc.Link(dmc.NavLink(label="Risk Tiers Configuration"), href="/risk-tiers"),
                        ],
                        p="md"
                    ),
                    dmc.AppShellMain(
                        [
                            dcc.Store(id="dataset-store", storage_type="session"),
                            dcc.Store(id="dataset-config-store", storage_type="session", data={}),
                            dcc.Store(id="policies-store", storage_type="session", data={}),
                            # Routing container
                            dcc.Location(id="url"),
                            html.Div(id="page-content")
                        ]
                    )
                ],
                header={"height": 60},
                navbar={"width": 250, "breakpoint": "sm"},
                padding="md",
            )
        ]
    )

app.layout = create_layout

def run_dashboard(debug: bool = True, port: int = 8050):
    """Run the Pycreditools Dash Studio locally."""
    # Ensure callbacks are registered
    from . import callbacks  # noqa
    app.run(debug=debug, port=port)

if __name__ == "__main__":
    run_dashboard()
