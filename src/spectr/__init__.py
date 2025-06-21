from importlib.metadata import PackageNotFoundError, version
try:
    __version__ = version(__name__)
except PackageNotFoundError:  # during editable install
    __version__ = "0.2.0"

from .fetch import broker_interface, data_interface  # noqa
import utils
