import os
import shutil


def get_notebook_path(version: int = 15) -> str:
    """Return the absolute path to the masterclass notebook within the package."""
    filename = f"tutorial_masterclass_v{version}.ipynb"
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), filename)
    )


def copy_notebook(dest: str = ".", version: int = 15) -> str:
    """Copy the tutorial notebook to the destination path.

    Args:
        dest: The directory or file path to copy the notebook to.
        version: Notebook version to copy (14 or 15).

    Returns:
        The absolute path to the copied notebook.
    """
    src_path = get_notebook_path(version)
    filename = os.path.basename(src_path)
    if os.path.isdir(dest):
        dest_path = os.path.join(dest, filename)
    else:
        dest_path = dest

    shutil.copy2(src_path, dest_path)
    return os.path.abspath(dest_path)

