"""Streamlit skin for the Pycreditools Studio (only place `import streamlit` lives)."""

import sys
from pathlib import Path


def run_studio(port: int = 8501) -> None:
    """Launch the Streamlit studio (`streamlit run app.py`)."""
    from streamlit.web import cli as stcli

    app_path = str(Path(__file__).parent / "app.py")
    sys.argv = ["streamlit", "run", app_path, "--server.port", str(port)]
    sys.exit(stcli.main())


__all__ = ["run_studio"]
