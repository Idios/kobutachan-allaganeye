"""Allagan Eye - FF14 Frontline video auto-highlight extraction tool."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("kobutachan-allaganeye")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
