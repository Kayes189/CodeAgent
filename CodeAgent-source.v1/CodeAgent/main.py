"""Entry point for both `python main.py` and the PyInstaller build."""
from codeagent.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
