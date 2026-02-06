"""Resource path resolution for both development and PyInstaller frozen environments."""

import sys
from pathlib import Path


def get_base_path() -> Path:
    """
    Get the base path for resource resolution.

    Returns:
        Path: Base directory (_MEIPASS in frozen env, project root in dev)
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running in PyInstaller bundle
        return Path(sys._MEIPASS)
    # Running in development
    return Path(__file__).parent.parent


def get_resource_path(relative_path: str) -> Path:
    """
    Get absolute path to a bundled resource.

    Args:
        relative_path: Path relative to project root (e.g., "app/templates")

    Returns:
        Path: Absolute path to the resource
    """
    return get_base_path() / relative_path
