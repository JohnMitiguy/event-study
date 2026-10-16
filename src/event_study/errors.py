"""Exception types shared across the project."""


class EventDataError(ValueError):
    """A problem with one event's data, as opposed to bad input overall.

    Raised for: day 0 not in the data, a window running off the data, NaN or
    inf returns, too few observations, mismatched security/benchmark dates,
    and a perfect (degenerate) market-model fit.

    The runner catches only this type: the event is recorded as failed and
    the other events still run. Any other ValueError (bad parameters, a
    broken index, a bad events table) stops the whole run.

    It subclasses ValueError so code that catches ValueError still catches it.
    """
