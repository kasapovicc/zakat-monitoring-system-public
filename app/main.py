#!/usr/bin/env python3
"""
Main entry point for Zekat macOS app

Architecture:
- Main process: rumps menubar + FastAPI server + APScheduler
- Window process: pywebview window in subprocess (app/window.py)

This file runs the main process. The window is launched as a separate process
that can be closed and reopened without stopping the server or scheduler.
"""

import sys
import subprocess
import threading
import asyncio
import uvicorn
import logging
import time
import urllib.request
import webbrowser
from pathlib import Path

import rumps

# Add parent directory to path so we can import run_app and app modules
if getattr(sys, 'frozen', False):
    base_dir = Path(sys._MEIPASS)
else:
    base_dir = Path(__file__).parent.parent
sys.path.insert(0, str(base_dir))

# Configure logging
log_file = Path.home() / '.zekat' / 'app.log'
log_file.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class UvicornServer:
    """Manages uvicorn server lifecycle with proper startup synchronization."""

    def __init__(self, app, host="127.0.0.1", port=8000):
        """
        Initialize uvicorn server.

        Args:
            app: FastAPI application instance
            host: Host to bind to
            port: Port to bind to
        """
        self.config = uvicorn.Config(
            app=app,
            host=host,
            port=port,
            log_level="warning",
            loop="asyncio",  # Explicit: no uvloop dependency issues
        )
        self.server = uvicorn.Server(config=self.config)
        self._thread = None

    def start(self):
        """Start server in a background thread with its own event loop."""
        self._thread = threading.Thread(target=self._run, daemon=False)
        self._thread.start()
        logger.info(f"Server thread started on {self.config.host}:{self.config.port}")

    def _run(self):
        """Run the server in a new asyncio event loop."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.server.serve())
        except Exception as e:
            logger.error(f"Server error: {e}", exc_info=True)

    def wait_for_startup(self, timeout=15):
        """
        Poll health endpoint until server responds or timeout.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            bool: True if server started successfully, False otherwise
        """
        url = f"http://{self.config.host}:{self.config.port}/health"
        deadline = time.monotonic() + timeout
        logger.info(f"Waiting for server to start at {url}...")

        while time.monotonic() < deadline:
            try:
                resp = urllib.request.urlopen(url, timeout=2)
                if resp.status == 200:
                    logger.info("Server is ready")
                    return True
            except Exception:
                pass
            time.sleep(0.3)

        logger.error(f"Server failed to start within {timeout}s")
        return False

    def shutdown(self):
        """Signal the server to shut down gracefully."""
        logger.info("Shutting down server...")
        self.server.should_exit = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("Server shutdown complete")


def _get_icon_path() -> Path | None:
    """
    Get the path to the menubar icon.

    Returns:
        Path to icon file, with fallback to development location.
    """
    from app.paths import get_resource_path

    # Try bundled resource location first
    icon_path = get_resource_path("icon_32x32.png")
    if icon_path.exists():
        return icon_path

    # Fallback to development location
    dev_icon = Path(__file__).parent.parent / "Zekat.iconset" / "icon_32x32.png"
    if dev_icon.exists():
        return dev_icon

    # If no icon found, rumps will use default
    logger.warning("Icon not found, using default")
    return None


class ZekatMenubarApp(rumps.App):
    """
    Main menubar application.

    Manages:
    - FastAPI server (background thread)
    - APScheduler (background thread)
    - rumps menubar icon (main thread)
    - Window subprocess (launched on demand)
    """

    def __init__(self, port: int = 8000):
        """
        Initialize the menubar app.

        Args:
            port: Port for FastAPI server
        """
        # Get icon path
        icon_path = _get_icon_path()

        # Initialize rumps app
        super().__init__(
            name="Zekat Monitor",
            icon=str(icon_path) if icon_path else None,
            quit_button=None,  # We provide our own quit button
        )

        # Add menu items
        self.menu = [
            rumps.MenuItem("Show Dashboard", callback=self.show_dashboard),
            rumps.MenuItem("Open in Browser", callback=self.open_browser),
            None,  # Separator
            rumps.MenuItem("Quit Zekat", callback=self.quit_app),
        ]

        self.port = port
        self.server = None
        self.scheduler = None
        self.window_process = None

    def _start_services(self):
        """Start FastAPI server and scheduler in background."""
        try:
            logger.info("Starting Zekat Monitor services...")

            # 1. Start FastAPI server
            logger.info("Importing FastAPI app...")
            from run_app import app as fastapi_app
            logger.info("FastAPI app imported successfully")

            logger.info("Creating UvicornServer...")
            self.server = UvicornServer(app=fastapi_app, port=self.port)
            logger.info("Starting server...")
            self.server.start()

            if not self.server.wait_for_startup(timeout=15):
                logger.error("FastAPI server failed to start. Exiting.")
                rumps.alert(
                    title="Startup Error",
                    message="Failed to start the Zekat server. Please check the logs.",
                    ok="Quit"
                )
                rumps.quit_application()
                return

            # 2. Start scheduler
            logger.info("Starting scheduler...")
            from app.scheduler import ZakatScheduler

            self.scheduler = ZakatScheduler(on_analysis_trigger=self._on_analysis_trigger)
            self.scheduler.start()

            logger.info("All services started successfully")
        except Exception as e:
            logger.error(f"Failed to start services: {e}", exc_info=True)
            rumps.alert(
                title="Startup Error",
                message=f"Failed to start services: {e}",
                ok="Quit"
            )
            rumps.quit_application()

        # 3. Auto-open window on first launch
        self._spawn_window()

    def _spawn_window(self):
        """Launch the window process via subprocess."""
        # Terminate existing window if running
        if self.window_process and self.window_process.poll() is None:
            logger.info("Window already open")
            return

        # Launch subprocess with --window flag
        try:
            self.window_process = subprocess.Popen(
                [sys.executable, "--window", str(self.port)]
            )
            logger.info(f"Window process started (PID: {self.window_process.pid})")
        except Exception as e:
            logger.error(f"Failed to launch window: {e}")
            rumps.alert(
                title="Window Error",
                message=f"Failed to open window: {e}",
                ok="OK"
            )

    @rumps.clicked("Show Dashboard")
    def show_dashboard(self, _):
        """Show or reopen the dashboard window."""
        self._spawn_window()

    @rumps.clicked("Open in Browser")
    def open_browser(self, _):
        """Open dashboard in default browser."""
        webbrowser.open(f"http://localhost:{self.port}")

    @rumps.clicked("Quit Zekat")
    def quit_app(self, _):
        """Quit the entire application."""
        logger.info("Quit requested from menubar")
        self._shutdown()
        rumps.quit_application()

    def _shutdown(self):
        """Clean shutdown of all services and child processes."""
        logger.info("Shutting down...")

        # 1. Terminate window process
        if self.window_process and self.window_process.poll() is None:
            logger.info("Terminating window process...")
            self.window_process.terminate()
            try:
                self.window_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                logger.warning("Window process did not terminate, killing...")
                self.window_process.kill()

        # 2. Stop scheduler
        if self.scheduler:
            self.scheduler.stop()

        # 3. Stop server
        if self.server:
            self.server.shutdown()

        logger.info("Zekat Monitor stopped")

    def _on_analysis_trigger(self):
        """Called by scheduler for automatic analysis."""
        logger.info("Scheduled analysis triggered")
        self._spawn_window()


def main():
    """Main application entry point."""
    app = ZekatMenubarApp(port=8000)

    # Start services in background thread so rumps event loop isn't blocked
    services_thread = threading.Thread(target=app._start_services, daemon=True)
    services_thread.start()

    # Run rumps event loop (blocks on main thread)
    app.run()


if __name__ == "__main__":
    main()
