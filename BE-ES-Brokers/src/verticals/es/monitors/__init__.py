"""E&S vertical monitor package.

Importing this package triggers ``register_monitor`` calls for every
E&S scheduled monitor.  Import it in ``main.py`` and ``worker.py`` so
the registry is populated at both API and worker startup.
"""

from verticals.es.monitors import binder_issuance as _binder_issuance  # noqa: F401 (side-effect)
from verticals.es.monitors import quote_comparison as _quote_comparison  # noqa: F401 (side-effect)
from verticals.es.monitors import renewal_trigger as _renewal_trigger  # noqa: F401 (side-effect)

__all__: list[str] = []
