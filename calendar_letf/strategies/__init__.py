"""Strategy plugins. Each file in this folder defines one or more rules and registers them with @register.

    from calendar_letf import strategies
    strategies.registry            # {"trend_50d": <class>, ...}
    s = strategies.make("trend_200d", kind="ema")
    expo = s.exposure(ctx)         # float64 array in [0, 1], NaN before the first valid signal

See base.py for the contract. `discover()` runs at import, so a new file here is picked up with no other edit.
"""
from .base import (SignalContext, Strategy, all_variants, check_exposure, check_no_lookahead, discover, make,  # noqa: F401
                   register, registry)

discover()
