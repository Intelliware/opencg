"""Pipeline test helpers: the production guard with the shared test doubles."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from opencg_pipeline import security
from opencg_shared.auth import Authenticator
from opencg_shared.testing import FakeAuditPool, FakeOpa, authenticator, install

__all__ = ["FakeAuditPool", "FakeOpa", "authenticator", "guarded_app", "install"]


def guarded_app(*, opa: FakeOpa | None = None, auth: Authenticator | None = None) -> FastAPI:
    """A FastAPI app with the production guard and test doubles installed."""
    app = FastAPI(dependencies=[Depends(security.guard)])
    install(app, opa=opa, auth=auth)
    return app
