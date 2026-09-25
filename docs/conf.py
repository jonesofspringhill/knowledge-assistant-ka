"""Build the project documentation without importing application services."""

import tomllib
from pathlib import Path

project = "Knowledge Assistant"
release = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())[
    "project"
]["version"]
extensions = ["myst_parser"]
html_theme = "sphinx_rtd_theme"
html_title = f"{project} {release}"
exclude_patterns = ["_build", ".obsidian", "features/FeatureTemplate.md"]
myst_heading_anchors = 4
html_show_sourcelink = False
