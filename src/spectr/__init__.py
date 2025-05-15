from importlib.metadata import PackageNotFoundError, version
try:
    __version__ = version(__name__)
except PackageNotFoundError:  # during editable install
    __version__ = "0.0.0"

from spectr import SpectrApp  # re-export
