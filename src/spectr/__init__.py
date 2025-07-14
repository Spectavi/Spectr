from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version(__name__)
except PackageNotFoundError:  # during editable install
    __version__ = "0.2.0"

from .fetch import broker_interface, data_interface, alpaca, fmp, robinhood  # noqa
from . import utils
from . import exceptions
from .plotext_fix import apply_patch as _patch_plotext

_patch_plotext()
