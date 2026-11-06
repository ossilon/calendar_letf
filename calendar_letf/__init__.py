"""calendar_letf: simulate 2x leveraged ETFs that reset their leverage on a calendar (weekly, monthly or
quarterly) and their daily-reset twins, with every cost layer explicit and labeled.

Modules (import the one you need; nothing heavy is loaded here):
    periods    which week / month / quarter each trading day belongs to, where each period ends, accrual fractions
    nyse       NYSE trading sessions from 1970 (holiday rules and one-off closures), for the period ends
    kernel     the NAV (net asset value) loops, compiled with numba, plus pandas wrappers
    costs      fee, spread and turns, each with a status (VERIFIED / ASSUMED / OPEN) and a source
    products   the registry of live, modeled and daily-twin products
    loader     price and rate files, the "known the day before" rate lag, gap checks
    series     the underlying index series (price and constructed total return) with provenance

Research tooling, not investment advice. Results for designs with no live fund today are labeled MODELED (a live
fund of each design traded 2024-08-30 to 2025-02-28; see products.MODELED_NOTE).
"""

__version__ = "0.1.1"
