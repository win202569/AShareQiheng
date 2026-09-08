"""Constructor identity bookkeeping used only by the metric trust boundary."""

from functools import wraps
import weakref


def _constructor_identity():
    initialized = {}

    def track(constructor):
        @wraps(constructor)
        def initialize(instance, *args, **kwargs):
            identity = id(instance)
            # A failed explicit reinitialization must not retain an earlier seal.
            initialized.pop(identity, None)
            result = constructor(instance, *args, **kwargs)
            initialized[identity] = (weakref.ref(instance, lambda _: initialized.pop(identity, None)), initialize)
            return result
        return initialize

    def require(instance):
        record = initialized.get(id(instance))
        if record is None or record[0]() is not instance or record[1] is not type(instance).__init__:
            raise ValueError("metric dependency requires its genuine constructor identity; copies are not eligible")

    return track, require


_track_repository_constructor, _require_repository_initialization = _constructor_identity()
del _constructor_identity
