import matplotlib
matplotlib.use("Agg")
import json
import sys
import os
import io
import contextlib

sys.stdout.reconfigure(encoding='utf-8')

def run_notebook(path):
    print(f"Reading notebook {path}...")
    with open(path, "r", encoding="utf-8") as f:
        nb = json.load(f)
    
    global_env = {}
    # Insert source directory to path
    sys.path.insert(0, os.path.abspath("src"))
    
    for i, cell in enumerate(nb["cells"]):
        if cell["cell_type"] == "code":
            code = "".join(cell["source"])
            print(f"Running cell {i+1}...")
            
            # Capture stdout
            stdout_io = io.StringIO()
            try:
                with contextlib.redirect_stdout(stdout_io), contextlib.redirect_stderr(stdout_io):
                    exec(code, global_env)
                
                output_text = stdout_io.getvalue()
                # If there is output, save it in the cell
                if output_text:
                    cell["outputs"] = [
                        {
                            "name": "stdout",
                            "output_type": "stream",
                            "text": [l + "\n" for l in output_text.splitlines()]
                        }
                    ]
                else:
                    cell["outputs"] = []
                cell["execution_count"] = i + 1
            except Exception as e:
                output_text = stdout_io.getvalue()
                print(f"Error in cell {i+1}:")
                print(output_text)
                print(e)
                raise e
                
    print(f"Writing outputs back to {path}...")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)
        
    print("Notebook run and saved successfully!")

if __name__ == "__main__":
    run_notebook("src/pycreditools/examples/tutorial_masterclass_v14.ipynb")
