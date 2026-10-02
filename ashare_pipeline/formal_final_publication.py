"""Private preparation authority for one all-or-nothing Stage D publication.

Adapters can only consume a capability while this coordinator is preparing its
exact source batch. No capability, proof constructor or mint operation escapes.
The post-commit method contains only the prevalidated shared-state assignment.
"""

from weakref import ref as _reference
from sys import _getframe


def _install_authority():
    preparing, controls, repositories = {}, {}, {}
    writer_binding = []
    owner, frame_authority, reference_authority = globals(), _getframe, _reference

    def require_runtime_authority():
        if (owner.get("_getframe") is not frame_authority
                or owner.get("_reference") is not reference_authority):
            raise ValueError("publication frame authority dependency changed")

    def writer_owner(*, direct=False):
        require_runtime_authority()
        if not writer_binding:
            raise ValueError("publication requires the authenticated repository writer")
        repository_type, writer, initializer = writer_binding[0]
        frame = frame_authority(2)
        while frame is not None:
            if frame.f_code is writer.__code__:
                repository = frame.f_locals.get("self")
                saved = repositories.get(id(repository))
                if (type(repository) is repository_type and saved is not None and saved() is repository
                        and repository_type.commit_complete_run is writer
                        and repository_type.__init__ is initializer):
                    return repository
                break
            if direct:
                break
            frame = frame.f_back
        raise ValueError("publication requires the authenticated repository writer")

    def claim(capability, source, stage):
        saved = preparing.get(id(capability))
        if (saved is None or saved[0] is not capability
                or saved[1].get(stage) is not source or stage in saved[3]):
            raise ValueError("prepared adapter requires the active coordinator capability")
        saved[3].add(stage)
        return saved[2]

    class SealedMeta(type):
        def __setattr__(cls, name, value):
            raise TypeError("publication authority methods are immutable")

        def __delattr__(cls, name):
            raise TypeError("publication authority methods are immutable")

    class FormalFinalPublicationCoordinator(metaclass=SealedMeta):
        def __init__(self, *args, **kwargs):
            raise TypeError("publication coordinator is created only by prepare")

        @staticmethod
        def prepare(*, input_batch, score_batch, eligibility_batch, pool_batch):
            raise ValueError("publication is private to the authenticated repository writer")

    def prepare(*, input_batch, score_batch, eligibility_batch, pool_batch):
            repository = writer_owner()
            # Imports are intentionally deferred: each producer captures claim
            # at installation without importing the other Stage D producers.
            from .formal_final_score_inputs import _prepare_final_inputs
            from .formal_final_scoring import _prepare_final_scores
            from .formal_final_eligibility import _prepare_final_eligibility
            from .formal_pool import _prepare_final_pools

            sources = (input_batch, score_batch, eligibility_batch, pool_batch)
            for source in sources:
                source.require_verified()
            source_bytes = tuple(source.canonical_bytes() for source in sources)
            state = bytearray(1)  # 0 prepared, 1 armed, 2 committed, 3 revoked
            prevalidated = [False]
            armed, revoked = [False], [False]
            capability = object()
            gate = lambda: state[0] == 2 and armed[0] and not revoked[0]
            preparing[id(capability)] = (capability, dict(zip(
                ("inputs", "scores", "eligibility", "pools"), sources)), gate, set())
            try:
                inputs, input_rows, source_recheck, source_hold = _prepare_final_inputs(input_batch, capability)
                scores, cards = _prepare_final_scores(score_batch, inputs, input_rows, capability,
                    source_input=input_batch)
                eligibility, eligibility_rows = _prepare_final_eligibility(eligibility_batch,
                    inputs, scores, capability, source_inputs=input_batch, source_scores=score_batch)
                pools, decisions = _prepare_final_pools(pool_batch, eligibility, capability,
                    source_eligibility=eligibility_batch)
            except BaseException:
                state[0] = 3
                raise
            finally:
                preparing.pop(id(capability), None)
            batches = (inputs, scores, eligibility, pools)
            children = tuple(input_rows.values()) + tuple(c for c in cards.values() if c is not None)
            children += tuple(eligibility_rows.values()) + decisions
            owner = [None]

            def authentic(item):
                if owner[0]() is not item or type(item) is not PreparedPublication:
                    raise ValueError("publication is forged or copied")
                if any(tuple(vars(cls).items()) != members for cls, members in interfaces):
                    raise ValueError("publication methods changed")

            class PreparedPublication(metaclass=SealedMeta):
                __slots__ = ("__weakref__",)

                def __init__(self, *args, **kwargs):
                    raise TypeError("publication cannot be constructed")

                def __getattribute__(self, name):
                    authentic(self)
                    return object.__getattribute__(self, name)

                @property
                def batches(self):
                    return batches

                @property
                def children(self):
                    return children

                def __copy__(self):
                    raise TypeError("publication cannot be copied")

                def __deepcopy__(self, memo):
                    raise TypeError("publication cannot be copied")

                def __reduce_ex__(self, protocol):
                    raise TypeError("publication cannot be reconstructed")

            interfaces = ((PreparedPublication, tuple(vars(PreparedPublication).items())),)
            result = object.__new__(PreparedPublication)
            owner[0] = reference_authority(result)

            def recheck(connection=None):
                authentic(result)
                if state[0] == 3:
                    raise ValueError("publication was revoked")
                source_recheck(connection)
                for source, raw in zip(sources, source_bytes, strict=True):
                    source.require_verified()
                    if source.canonical_bytes() != raw:
                        raise ValueError("publication source changed")

            def prevalidate_commit():
                if state[0] != 0:
                    raise ValueError("publication commit is not preparable")
                recheck()
                prevalidated[0] = True

            def arm():
                if state[0] != 0 or not prevalidated[0]:
                    raise ValueError("publication cannot be armed")
                state[0] = 1
                armed[0] = True

            def mark_committed():
                state[0] = 2

            def revoke():
                revoked[0] = True
                state[0] = 3

            controls[id(result)] = (result, repository,
                (recheck, prevalidate_commit, arm, mark_committed, revoke, source_hold))
            return result

    def take_controls(publication):
        repository = writer_owner(direct=True)
        saved = controls.pop(id(publication), None)
        if saved is None or saved[0] is not publication or saved[1] is not repository:
            raise ValueError("publication has no repository-owned capability")
        return saved[2]

    def bind(repository_type):
        require_runtime_authority()
        frame = frame_authority(1)
        if (writer_binding or frame.f_globals.get("__name__") != "ashare_pipeline.formal_final_repository"
                or frame.f_globals.get("FormalFinalRunRepository") is not repository_type):
            raise ValueError("publication authority binds only the repository module")
        writer_binding.append((repository_type, repository_type.commit_complete_run, repository_type.__init__))

        def register(repository):
            require_runtime_authority()
            if (type(repository) is not repository_type
                    or frame_authority(1).f_code is not writer_binding[0][2].__code__):
                raise ValueError("publication requires an initialized repository")
            key = id(repository)
            repositories[key] = reference_authority(repository, lambda _: repositories.pop(key, None))
        return prepare, take_controls, register

    return claim, FormalFinalPublicationCoordinator, bind


_claim_preparation, FormalFinalPublicationCoordinator, _bind_repository_writer = _install_authority()
del _install_authority

__all__ = ["FormalFinalPublicationCoordinator"]
