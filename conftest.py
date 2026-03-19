"""Root conftest -- Playwright browser context configuration."""

from pathlib import Path

import pytest

_RESULTS_DIR = Path(__file__).resolve().parent / "test-results"


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Configure Playwright browser context with video recording."""
    video_dir = _RESULTS_DIR / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    return {
        **browser_context_args,
        "record_video_dir": str(video_dir),
        "record_video_size": {"width": 1280, "height": 720},
    }
