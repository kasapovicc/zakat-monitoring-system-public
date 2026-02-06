#!/usr/bin/env python3
"""
Standalone pywebview window process.

Launched by the main menubar process via subprocess.
Displays the Zekat dashboard in a native WebKit window.
Exits when the user closes the window.
"""

import sys
import webview


def main(port: int = 8000):
    """
    Open a native window showing the dashboard.

    Args:
        port: The port where the FastAPI server is running.
    """
    window = webview.create_window(
        title='Zekat Monitor',
        url=f'http://localhost:{port}',
        width=1200,
        height=800,
        resizable=True,
        min_size=(800, 600),
        text_select=True,
    )
    webview.start()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    main(port)
