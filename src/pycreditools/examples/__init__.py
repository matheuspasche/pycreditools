import os
import shutil

#: The single masterclass notebook shipped with the package (issue #76). The old
#: per-version files (v14/v15/v16) were retired when it was written from scratch.
NOTEBOOK_FILENAME = "tutorial_masterclass.ipynb"


def get_notebook_path() -> str:
    """Return the absolute path to the masterclass notebook within the package."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), NOTEBOOK_FILENAME))


def copy_notebook(dest: str = ".") -> str:
    """Copy the masterclass notebook to the destination path.

    Args:
        dest: The directory or file path to copy the notebook to.

    Returns:
        The absolute path to the copied notebook.
    """
    src_path = get_notebook_path()
    if os.path.isdir(dest):
        dest_path = os.path.join(dest, os.path.basename(src_path))
    else:
        dest_path = dest

    shutil.copy2(src_path, dest_path)
    return os.path.abspath(dest_path)
