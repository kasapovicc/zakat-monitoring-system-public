#!/usr/bin/env python3
"""
Entry point for native macOS app.

Two modes:
- Default (no args): Run main menubar app
- --window <port>: Run window subprocess
"""

import sys
import multiprocessing
from pathlib import Path

if __name__ == "__main__":
    # Required for PyInstaller frozen environment
    multiprocessing.freeze_support()

    # Add current directory to path (frozen-aware)
    if getattr(sys, 'frozen', False):
        base_dir = Path(sys._MEIPASS)
    else:
        base_dir = Path(__file__).parent

    sys.path.insert(0, str(base_dir))

    # Check mode: window subprocess or main app
    if len(sys.argv) >= 2 and sys.argv[1] == "--window":
        # Window subprocess mode
        from app.window import main
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
        main(port)
    else:
        # Main menubar app mode
        from app.main import main
        main()
