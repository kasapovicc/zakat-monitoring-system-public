"""
macOS LaunchAgent management for Launch at Login

Creates/removes plist file in ~/Library/LaunchAgents/
"""

import plistlib
import sys
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def get_launch_agent_plist_path() -> Path:
    """Get the path to the LaunchAgent plist file"""
    return Path.home() / "Library" / "LaunchAgents" / "com.zekat.monitor.plist"


def get_app_executable_path() -> str:
    """
    Get the path to the app executable.

    Returns:
        Path to python executable and main.py
    """
    # Get the python executable
    python_path = sys.executable

    # Get the main.py path
    main_py = Path(__file__).parent / "main.py"

    return f"{python_path} {main_py}"


def create_plist_content() -> dict:
    """
    Create the plist content for LaunchAgent.

    Returns:
        Dictionary representing the plist
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller bundle: executable is the app binary
        program_args = [sys.executable]
    else:
        # Dev mode: python + main.py
        program_args = [sys.executable, str(Path(__file__).parent / "main.py")]

    plist = {
        "Label": "com.zekat.monitor",
        "ProgramArguments": program_args,
        "RunAtLoad": True,
        "KeepAlive": False,
        "StandardOutPath": str(Path.home() / "Library" / "Logs" / "Zekat" / "stdout.log"),
        "StandardErrorPath": str(Path.home() / "Library" / "Logs" / "Zekat" / "stderr.log"),
        "EnvironmentVariables": {
            "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        }
    }

    return plist


def install_launch_agent() -> bool:
    """
    Install LaunchAgent plist for auto-start on login.

    Returns:
        True if successful, False otherwise
    """
    try:
        plist_path = get_launch_agent_plist_path()

        # Create LaunchAgents directory if it doesn't exist
        plist_path.parent.mkdir(parents=True, exist_ok=True)

        # Create logs directory
        logs_dir = Path.home() / "Library" / "Logs" / "Zekat"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Create plist content
        plist_content = create_plist_content()

        # Write plist file
        with open(plist_path, 'wb') as f:
            plistlib.dump(plist_content, f)

        # Set permissions
        plist_path.chmod(0o644)

        logger.info(f"LaunchAgent installed at {plist_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to install LaunchAgent: {e}")
        return False


def remove_launch_agent() -> bool:
    """
    Remove LaunchAgent plist to disable auto-start.

    Returns:
        True if successful, False otherwise
    """
    try:
        plist_path = get_launch_agent_plist_path()

        if plist_path.exists():
            plist_path.unlink()
            logger.info(f"LaunchAgent removed from {plist_path}")
        else:
            logger.warning("LaunchAgent plist not found")

        return True

    except Exception as e:
        logger.error(f"Failed to remove LaunchAgent: {e}")
        return False


def is_launch_agent_installed() -> bool:
    """
    Check if LaunchAgent is installed.

    Returns:
        True if installed, False otherwise
    """
    plist_path = get_launch_agent_plist_path()
    return plist_path.exists()


def load_launch_agent() -> bool:
    """
    Load the LaunchAgent using launchctl.

    Returns:
        True if successful, False otherwise
    """
    try:
        import subprocess

        plist_path = get_launch_agent_plist_path()

        if not plist_path.exists():
            logger.error("LaunchAgent plist not found")
            return False

        # Load the agent
        result = subprocess.run(
            ["launchctl", "load", str(plist_path)],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            logger.info("LaunchAgent loaded successfully")
            return True
        else:
            logger.error(f"Failed to load LaunchAgent: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Error loading LaunchAgent: {e}")
        return False


def unload_launch_agent() -> bool:
    """
    Unload the LaunchAgent using launchctl.

    Returns:
        True if successful, False otherwise
    """
    try:
        import subprocess

        plist_path = get_launch_agent_plist_path()

        if not plist_path.exists():
            logger.warning("LaunchAgent plist not found")
            return True

        # Unload the agent
        result = subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            logger.info("LaunchAgent unloaded successfully")
            return True
        else:
            # It's okay if it wasn't loaded
            logger.warning(f"LaunchAgent unload result: {result.stderr}")
            return True

    except Exception as e:
        logger.error(f"Error unloading LaunchAgent: {e}")
        return False
