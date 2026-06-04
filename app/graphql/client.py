"""
GraphQL client (refactor seguro para entornos con múltiples hilos/loops).
- Un cliente httpx por *event loop* (no se comparte entre hilos).
- Un jar de cookies compartido para preservar la sesión al recrear clientes.
- Sin introspección de atributos privados de httpx (robusto a cambios).
"""

import asyncio
from typing import Any, Dict, Optional, ClassVar
import threading
import httpx

from ..core.config import Config
from ..core.logging import get_logger

logger = get_logger(__name__)


class GraphQLClient:
    """
    Cliente para comunicar con la API GraphQL.

    Principios:
    - Un AsyncClient por event loop (clave para evitar 'Event loop is closed').
    - Reutilizamos un único jar de cookies (httpx.Cookies) para mantener sesión
      cuando se crean clientes nuevos (p. ej., en otro hilo).
    """

    # Jar y lock COMPARTIDOS entre TODAS las instancias (y por ende, entre hilos/loops)
    _shared_cookies: ClassVar[httpx.Cookies] = httpx.Cookies()
    _cookies_lock: ClassVar[threading.RLock] = threading.RLock()

    # Clients shared across instances
    _clients_by_loop: ClassVar[Dict[int, httpx.AsyncClient]] = {}
    _clients_lock: ClassVar[threading.RLock] = threading.RLock()

    # Semaphore for refresh serialization (per event loop)
    _refresh_semaphores: ClassVar[Dict[int, asyncio.Semaphore]] = {}
    _refresh_sem_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, timeout: float = 30.0) -> None:
        if not hasattr(Config, 'GRAPHQL_URL') or not isinstance(Config.GRAPHQL_URL, str):
            raise ValueError("Config.GRAPHQL_URL must be a valid string")
        self.url: str = Config.GRAPHQL_URL
        self._timeout: float = timeout

        # Jar de cookies compartido entre clientes (sesión vía cookies HttpOnly)
        self._cookies = GraphQLClient._shared_cookies

        # Inyectado externamente si tu app lo usa (unused for now)
        self.session_store: Optional[object] = None

    def set_session_store(self, store: object) -> None:
        """Permite inyectar/persistir el SessionStore desde el contenedor DI."""
        self.session_store = store

    # -------------------------------
    # Cookie restoration
    # -------------------------------

    @classmethod
    def restore_refresh_token(cls, refresh_token: str) -> None:
        """
        Restaura el refresh token en el jar de cookies compartido.

        Este método se usa para restaurar la sesión desde el almacenamiento persistente
        al inicio de la aplicación.

        Args:
            refresh_token: El refresh token a restaurar
        """
        try:
            with cls._cookies_lock:
                # Limpiar cookies existentes
                cls._shared_cookies.clear()

                # Agregar el refresh token como cookie
                # Nota: httpx.Cookies acepta un dict para set()
                cls._shared_cookies.set("refresh_token", refresh_token)

                logger.info("Refresh token restored to shared cookie jar")
        except Exception as e:
            logger.error(f"Failed to restore refresh token to cookies: {e}")

    @classmethod
    def current_access_token(cls) -> Optional[str]:
        """Devuelve el access_token actual del jar compartido (para auth del WebSocket).

        El backend setea la cookie ``access_token`` (y el header x-access-token) al
        autenticar/refrescar; el cookie hook la propaga al jar compartido.
        """
        try:
            with cls._cookies_lock:
                return cls._shared_cookies.get("access_token")
        except Exception:
            return None

    @classmethod
    def clear_cookies(cls) -> None:
        """Limpia todas las cookies del jar compartido."""
        try:
            with cls._cookies_lock:
                cls._shared_cookies.clear()
                logger.info("Shared cookie jar cleared")
        except Exception as e:
            logger.error(f"Failed to clear cookies: {e}")

    # -------------------------------
    # Infra: cliente por event loop
    # -------------------------------

    async def _get_refresh_semaphore(self) -> asyncio.Semaphore:
        """Obtiene/crea semáforo de refresh para el event loop actual."""
        loop = asyncio.get_running_loop()
        key = id(loop)

        with GraphQLClient._refresh_sem_lock:
            if key not in self._refresh_semaphores:
                self._refresh_semaphores[key] = asyncio.Semaphore(1)
            return self._refresh_semaphores[key]

    async def _get_client(self) -> httpx.AsyncClient:
        """Devuelve un AsyncClient asociado al event loop actual."""
        loop = asyncio.get_running_loop()
        key = id(loop)

        with GraphQLClient._clients_lock:
            client = self._clients_by_loop.get(key)
            if client is None or client.is_closed:
                logger.debug("GraphQLClient: creando httpx.AsyncClient para el loop %s", key)
                client = httpx.AsyncClient(
                    timeout=self._timeout,
                    follow_redirects=True,
                    cookies=self._cookies,
                    event_hooks={"response": [self._response_cookie_hook]},
                )
                self._clients_by_loop[key] = client
            return client  # Note: return outside lock for async safety

    async def _response_cookie_hook(self, response: httpx.Response) -> None:
        # Propaga cookies del cliente de este loop → jar compartido
        try:
            with GraphQLClient._cookies_lock:
                self._cookies.update(response.cookies)
        except Exception as e:
            logger.debug("Cookie hook error: %s", e)

    async def close(self) -> None:
        """Cierra todos los AsyncClient vivos."""
        with GraphQLClient._clients_lock:
            for key, c in list(self._clients_by_loop.items()):
                try:
                    if not c.is_closed:
                        await c.aclose()
                except Exception as e:  # pragma: no cover
                    logger.debug("Error cerrando cliente httpx (%s): %s", key, e)
                finally:
                    self._clients_by_loop.pop(key, None)

    # -------------------------------
    # Helpers
    # -------------------------------

    def _build_headers(self, use_auth: bool = True) -> Dict[str, str]:
        """
        Construye headers base. La autenticación va por cookies HttpOnly,
        así que aquí no añadimos Authorization.
        """
        base = Config.get_api_headers()
        if not use_auth:
            # If no auth, perhaps remove auth-related headers if any, but for now same
            pass
        # Nada adicional; las cookies viajarán automáticamente
        return base

    # -------------------------------
    # GraphQL
    # -------------------------------

    async def execute(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        use_auth: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Ejecuta una query/mutation GraphQL y devuelve `data` o None en error."""
        payload: Dict[str, Any] = {"query": query, "variables": variables or {}}
        headers = self._build_headers(use_auth=use_auth)

        try:
            client = await self._get_client()
            # --- PRE: copia jar compartido → cliente del loop actual ---
            if use_auth:
                with GraphQLClient._cookies_lock:
                    try:
                        client.cookies.update(self._cookies)
                    except Exception:
                        pass

            resp = await client.post(self.url, json=payload, headers=headers)

            # --- POST: Propaga cualquier Set-Cookie del cliente → jar compartido ---
            # Note: hook should handle this, but manual for safety
            with GraphQLClient._cookies_lock:
                try:
                    self._cookies.update(client.cookies)
                except Exception:
                    pass

            # Retry logic con exponential backoff si 401
            max_retries = Config.GRAPHQL_MAX_RETRIES
            retry_delays = Config.GRAPHQL_RETRY_DELAYS
            attempt = 0

            while resp.status_code == 401 and use_auth and attempt < max_retries:
                attempt += 1
                logger.info("401 recibido en intento %d/%d; reintentando...", attempt, max_retries)

                # Usar semáforo para serializar refreshes entre workers concurrentes
                semaphore = await self._get_refresh_semaphore()
                async with semaphore:
                    # Delay con backoff exponencial
                    delay = retry_delays[min(attempt - 1, len(retry_delays) - 1)]
                    await asyncio.sleep(delay)

                    # Sincronizar cookies SIN limpiar (evitar perder cookies válidas)
                    with GraphQLClient._cookies_lock:
                        client.cookies.update(self._cookies)

                    # Reintentar request
                    resp = await client.post(self.url, json=payload, headers=headers)

                    # Propagar nuevas cookies del refresh
                    with GraphQLClient._cookies_lock:
                        self._cookies.update(client.cookies)

            if resp.status_code == 200:
                try:
                    data = resp.json()

                    # Verificar si hay errores GraphQL de autenticación
                    if "errors" in data and use_auth:
                        errors = data["errors"]
                        
                        # Log GraphQL errors for debugging
                        logger.warning(f"GraphQL errors in response: {errors}")
                        
                        is_auth_error = any(
                            "authentication required" in str(err.get("message", "")).lower()
                            for err in errors
                        )

                        # Si es error de auth y aún tenemos reintentos, hacer retry
                        if is_auth_error and attempt < max_retries:
                            attempt += 1
                            logger.info("GraphQL auth error en intento %d/%d; reintentando...", attempt, max_retries)

                            # Usar semáforo para serializar refreshes
                            semaphore = await self._get_refresh_semaphore()
                            async with semaphore:
                                delay = retry_delays[min(attempt - 1, len(retry_delays) - 1)]
                                await asyncio.sleep(delay)

                                # Sincronizar cookies
                                with GraphQLClient._cookies_lock:
                                    client.cookies.update(self._cookies)

                                # Reintentar request
                                resp = await client.post(self.url, json=payload, headers=headers)

                                # Propagar cookies
                                with GraphQLClient._cookies_lock:
                                    self._cookies.update(client.cookies)

                                # Volver a verificar el response
                                if resp.status_code == 200:
                                    try:
                                        data = resp.json()
                                        if "errors" not in data:
                                            logger.info("Request succeeded after %d retries (GraphQL auth error)", attempt)
                                            return data.get("data")
                                    except ValueError:
                                        pass

                        # Si ya no hay más reintentos o no es error de auth, loguear y retornar None
                        if attempt > 0:
                            logger.error("GraphQL errors (after %d retries): %s", attempt, data["errors"])
                        else:
                            logger.error("GraphQL errors: %s", data["errors"])
                        return None
                    
                    # Si no hay errores en data pero use_auth es False, también verificar errores
                    if "errors" in data and not use_auth:
                        logger.error("GraphQL errors (no auth): %s", data["errors"])
                        return None

                    if attempt > 0:
                        logger.info("Request succeeded after %d retries", attempt)
                    return data.get("data")
                except ValueError as e:
                    logger.error("JSON decode error: %s", e)
                    return None

            if attempt > 0:
                logger.error("HTTP %s (after %d retries): %s", resp.status_code, attempt, resp.text)
            else:
                logger.error("HTTP %s: %s", resp.status_code, resp.text)
            return None

        except httpx.TimeoutException as e:
            logger.error("Timeout en execute: %s", e)
            return None
        except httpx.RequestError as e:
            logger.error("Request error en execute: %s", e)
            return None
        except RuntimeError as e:
            # En teoría no volverá a pasar con cliente por loop, pero por si acaso:
            if "event loop is closed" in str(e).lower():
                logger.warning("Loop cerrado detectado. Invalidando cliente.")
                # Can't await in closed loop, so just clean up and return None
                try:
                    with GraphQLClient._clients_lock:
                        key = id(asyncio.get_event_loop())  # May fail, but try
                        c = self._clients_by_loop.pop(key, None)
                        if c:
                            # Can't await aclose here if loop closed
                            pass
                except Exception:
                    pass
                logger.error("Cannot recover from closed loop.")
                return None
            logger.error("RuntimeError en execute: %s", e)
            return None
        except TypeError as e:
            # Específicamente capturar errores de serialización JSON
            if "not JSON serializable" in str(e):
                logger.error("JSON serialization error - datetime object not serialized: %s", e)
                logger.error("This usually means a datetime object was passed without .isoformat() conversion")
            else:
                logger.error("TypeError en execute: %s", e)
            return None
        except Exception as e:
            logger.error("Error en execute: %s", e)
            return None

    # -------------------------------
    # REST (si aún tienes endpoints legacy)
    # -------------------------------

    async def fetch_rest(
        self,
        endpoint: str,
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        # Use GRAPHQL_URL base for consistency? Or keep API_BASE_URL
        base_url = getattr(Config, 'API_BASE_URL', self.url)
        url = f"{base_url}{endpoint}"
        headers = self._build_headers(use_auth=True)

        try:
            client = await self._get_client()
            m = method.upper()
            if m == "GET":
                resp = await client.get(url, headers=headers)
            elif m == "POST":
                resp = await client.post(url, json=data, headers=headers)
            elif m == "PUT":
                resp = await client.put(url, json=data, headers=headers)
            elif m == "DELETE":
                resp = await client.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            if resp.status_code == 200:
                # Puede ser JSON o no; depende del endpoint
                try:
                    return resp.json()
                except ValueError:
                    return resp.text

            logger.error("REST %s %s → HTTP %s: %s", method, endpoint, resp.status_code, resp.text)
            return None

        except httpx.TimeoutException as e:
            logger.error("Timeout en fetch_rest: %s", e)
            return None
        except httpx.RequestError as e:
            logger.error("Request error en fetch_rest: %s", e)
            return None
        except Exception as e:
            logger.error("Error en fetch_rest: %s", e)
            return None

    # -------------------------------
    # Utilidades de app
    # -------------------------------

    async def current_user(self) -> Optional[Dict[str, Any]]:
        query = """
        query CurrentUser {
            currentUser {
                id
                username
                email
                role
            }
        }
        """
        data = await self.execute(query)
        return data.get("currentUser") if data else None

    async def check_health(self) -> bool:
        try:
            base_url = getattr(Config, 'API_BASE_URL', self.url)
            client = await self._get_client()
            resp = await client.get(f"{base_url}/")
            return resp.status_code == 200
        except Exception:
            return False