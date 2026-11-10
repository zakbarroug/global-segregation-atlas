"""Connector routing contains metadata and factories, never fetched city records."""

from ..config import Settings
from ..http import SafeHTTP
from ..models import Place
from .base import IncomeConnector
from .census import CensusNYCConnector

CONNECTOR_FACTORIES = (CensusNYCConnector,)


def select_connector(
    place: Place, http: SafeHTTP, settings: Settings
) -> tuple[IncomeConnector | None, str]:
    candidates = []
    for factory in CONNECTOR_FACTORIES:
        connector = factory(http, settings)
        confidence, reason = connector.supports(place)
        if confidence > 0:
            candidates.append((confidence, reason, connector))
    if not candidates:
        return None, "No reviewed connector for this place"
    _, reason, connector = max(candidates, key=lambda item: item[0])
    return connector, reason
