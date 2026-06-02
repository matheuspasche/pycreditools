import json
import sys
import matplotlib
matplotlib.use("Agg")

def run_notebook(path):
    with open(path, "r", encoding="utf-8") as f:
        nb = json.load(f)
    
    global_env = {}
    
    # Pre-add sys path
    sys.path.insert(0, "c:/Users/Matheus/Documents/GitHub/pycreditools/src")
    
    for i, cell in enumerate(nb["cells"]):
        if cell["cell_type"] == "code":
            code = "".join(cell["source"])
            print(f"\n--- Running cell {i+1} ---")
            try:
                # We exec the code block inside global_env
                exec(code, global_env)
            except Exception as e:
                print(f"Error in cell {i+1}:")
                print(code)
                raise e
    print("\nNotebook execution successful!")

if __name__ == "__main__":
    run_notebook("tutorial_masterclass_v14.ipynb")
