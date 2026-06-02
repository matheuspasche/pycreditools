import os
import shutil

def get_notebook_path() -> str:
    """Return the absolute path to the masterclass notebook within the package."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "tutorial_masterclass_v14.ipynb"))

def get_generator_path() -> str:
    """Return the absolute path to the notebook generator script within the package."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "generate_notebook_v14.py"))

def copy_notebook(dest: str = ".") -> str:
    """Copy the tutorial notebook to the destination path.
    
    Args:
        dest: The directory or file path to copy the notebook to.
        
    Returns:
        The absolute path to the copied notebook.
    """
    src_path = get_notebook_path()
    if os.path.isdir(dest):
        dest_path = os.path.join(dest, "tutorial_masterclass_v14.ipynb")
    else:
        dest_path = dest
        
    shutil.copy2(src_path, dest_path)
    return os.path.abspath(dest_path)
