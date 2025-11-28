"""Global render lock for plotext.

Plotext maintains global state and is not thread-safe. We serialize all
builds across views to avoid interleaved/glitchy renders when timers or
background threads trigger concurrent draws.
"""

from threading import RLock

# Re-entrant so nested plotting within the same thread is safe.
PLOT_LOCK = RLock()

