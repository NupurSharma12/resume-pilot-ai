"""Optional disposal capability for a `PersistenceStore` backend.

Not every `PersistenceStore` implementation owns a resource that needs
releasing at shutdown — `InMemoryPersistenceStore` is a plain dict, with
nothing to dispose. `PostgresPersistenceStore` owns a pooled `AsyncEngine`
that does need releasing (`await engine.dispose()`) when the application
shuts down, so it frees its connections cleanly rather than leaving them
to the OS/driver's own idle timeout.

`Disposable` lets `app.py`'s `lifespan` express "release this store's
resources, if it has any to release" without either (a) making
`dispose()` part of `PersistenceStore` itself — forcing every backend,
including `InMemoryPersistenceStore`, to implement a meaningless no-op
just for symmetry — or (b) hardcoding an
`isinstance(store, PostgresPersistenceStore)` check into `app.py`, which
would leak a database-specific type into application-lifecycle code that
has no other reason to know which backend is configured. A
`runtime_checkable` structural check (`isinstance(store, Disposable)`) is
enough: whichever store actually defines an async `dispose()` method
satisfies it, with no explicit inheritance required — the same
structural-typing choice `PersistenceStore` itself already makes (see
`app.persistence.store`).
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Disposable(Protocol):
    """Something that owns a resource it can release once, at application shutdown."""

    async def dispose(self) -> None:
        """Release this object's underlying resources (e.g. a connection pool)."""
        ...
