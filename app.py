"""
OmniBrain Frontend Gateway Entrypoint.
The application source is maintained in frontend/app.py.
This script ensures seamless compatibility for local execution and container environments.
"""
import os
import runpy

_APP_PATH = os.path.join(os.path.dirname(__file__), "frontend", "app.py")
runpy.run_path(_APP_PATH, run_name="__main__")
