import asyncio
from contextlib import aclosing, asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from .config import Settings
from .discovery.catalog import CATALOG
from .discovery.web_search import search_available
from .geography.places import PlaceTokens, SearchLimiter, search_places
from .http import ProviderError, SafeHTTP
from .models import AnalysisRequest, Event
from .pipeline import analysis_events, encode_event, event


class BodyLimitMiddleware:
    def __init__(self, app, limit=16384):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        # Read only POST bodies, bounded even when Content-Length is missing/incorrect.
        if scope["method"] == "POST":
            messages, count = [], 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                count += len(message.get("body", b""))
                if count > self.limit:
                    return await JSONResponse(
                        {"detail": "Request body too large"}, status_code=413
                    )(scope, receive, send)
                messages.append(message)
                if not message.get("more_body", False):
                    break

            async def replay():
                if messages:
                    return messages.pop(0)
                return await receive()

            return await self.app(scope, replay, send)
        return await self.app(scope, receive, send)


def create_app(settings: Settings | None = None, http_factory=SafeHTTP):
    settings = settings or Settings()
    tokens = PlaceTokens(settings.place_token_secret.get_secret_value())
    limiter = SearchLimiter()
    active = 0

    @asynccontextmanager
    async def lifespan(app):
        yield

    app = FastAPI(title="Global Segregation Atlas", version="0.1.0", lifespan=lifespan)
    app.state.tokens = tokens
    app.state.settings = settings
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins.split(","),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
    )

    @app.middleware("http")
    async def privacy_headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Accel-Buffering"] = "no"
        return response

    @app.exception_handler(ProviderError)
    async def provider_error(request, exc):
        return JSONResponse(
            {"detail": exc.message, "code": exc.code},
            status_code=429 if exc.code == "search_rate_limit" else 502,
        )

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "persistence": "none",
            "census_key_configured": bool(settings.census_api_key.get_secret_value()),
            "geocoder": settings.geocoder,
            "ai_discovery_enabled": settings.enable_ai_discovery,
            "ai_provider": settings.ai_provider,
            "ai_model": settings.ai_model
            if settings.ai_provider == "compatible"
            else settings.openai_discovery_model,
            "ai_free_only": settings.ai_free_only,
            "web_discovery_configured": bool(search_available(settings)),
            "web_search_provider": settings.web_search_provider,
            "tavily_key_configured": bool(settings.tavily_api_key.get_secret_value()),
        }

    @app.get("/providers")
    async def providers():
        return {"providers": CATALOG, "worldwide_search": True, "worldwide_measurement": False}

    @app.get("/places/search")
    async def places(q: str = Query(min_length=2, max_length=120)):
        query = q.strip()
        if len(query) < 2:
            raise HTTPException(422, "Enter at least two characters")
        await limiter.acquire()
        try:
            async with asyncio.timeout(35), http_factory(settings) as http:
                results = await search_places(query, http, settings, tokens)
            return {
                "places": results,
                "attribution": "© OpenStreetMap contributors · Photon"
                if settings.geocoder == "photon"
                else "GeoNames · CC BY 4.0",
                "provider_notice": "Service de démonstration à trafic modéré"
                if settings.geocoder == "photon"
                else "Compte GeoNames de l’opérateur",
            }
        except TimeoutError as exc:
            raise ProviderError(
                "provider_timeout", "La recherche mondiale a dépassé son délai"
            ) from exc
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise ProviderError(
                "geocoder_schema", "Le fournisseur de recherche a renvoyé un format incompatible"
            ) from exc

    @app.post(
        "/analysis",
        response_class=StreamingResponse,
        responses={
            200: {
                "content": {"application/x-ndjson": {"schema": Event.model_json_schema()}},
                "description": "One typed Event JSON object per line; complete is terminal",
            }
        },
    )
    async def analysis(payload: AnalysisRequest, request: Request):
        nonlocal active
        try:
            place = tokens.decode(payload.city_id)
        except ProviderError as exc:
            raise HTTPException(422, exc.message) from exc
        if active >= settings.max_concurrent_analyses:
            raise HTTPException(
                429,
                "Le serveur analyse déjà le maximum de villes. Réessayez bientôt.",
                headers={"Retry-After": "5"},
            )

        async def stream():
            nonlocal active
            size = 0
            try:
                async with http_factory(settings) as http:
                    async with aclosing(analysis_events(place, payload, settings, http)) as events:
                        async for item in events:
                            if await request.is_disconnected():
                                return
                            encoded = encode_event(item)
                            size += len(encoded)
                            if size > settings.max_response_bytes:
                                yield encode_event(
                                    event(
                                        "failed",
                                        code="response_limit",
                                        reason="Analyse trop volumineuse pour le budget de réponse",
                                        status="failed",
                                    )
                                )
                                yield encode_event(event("complete", status="failed"))
                                return
                            yield encoded
            except asyncio.CancelledError:
                raise
            except Exception:
                # Never leak upstream URL query strings, keys, raw data or traceback.
                yield encode_event(
                    event(
                        "failed",
                        code="internal_error",
                        reason="L’analyse a échoué à une validation interne ; aucun résultat supplémentaire n’est publié.",
                        status="failed",
                    )
                )
                yield encode_event(event("complete", status="failed"))
            finally:
                active -= 1

        active += 1  # No await between capacity check and reservation.
        return StreamingResponse(
            stream(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
