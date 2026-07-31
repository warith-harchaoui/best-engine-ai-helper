"""
sources — external catalog/benchmark feeds consumed by ``catalog update``.

Each submodule adapts one public source into the project's own vocabulary
(parameter count, model kind, peak inference RAM, licence, weights URL) so the
refresh path can merge heterogeneous feeds without every caller re-learning each
site's private schema.

Author
------
Warith Harchaoui <warith.harchaoui@gmail.com>
"""

from __future__ import annotations
