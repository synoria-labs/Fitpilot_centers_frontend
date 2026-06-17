"""
Servicio de autenticacion con backend GraphQL.
"""
import json
import base64
from typing import Optional, Dict, Any, Tuple

from ..core.logging import get_logger

logger = get_logger(__name__)


def _first_present(data: Dict[str, Any], *keys: str) -> Optional[Any]:
    """Devuelve el primer valor disponible entre varias claves."""
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _decode_jwt_payload(token: str) -> Optional[Dict[str, Any]]:
    """Decodifica el payload de un JWT sin verificar la firma."""
    try:
        # JWT tiene 3 partes separadas por puntos: header.payload.signature
        parts = token.split('.')
        if len(parts) != 3:
            return None

        # Decodificar el payload (segunda parte)
        payload_part = parts[1]

        # Agregar padding si es necesario
        padding = 4 - (len(payload_part) % 4)
        if padding != 4:
            payload_part += '=' * padding

        # Decodificar base64
        payload_bytes = base64.urlsafe_b64decode(payload_part)
        payload = json.loads(payload_bytes.decode('utf-8'))

        return payload
    except Exception as e:
        logger.debug(f"Error decoding JWT payload: {e}")
        return None


class AuthService:
    """Servicio de autenticacion con JWT."""

    def __init__(self, graphql_client, session_store):
        self.client = graphql_client
        self.session = session_store

    def clear_local_session(self) -> None:
        """Limpia todos los rastros locales de autenticacion."""
        self.session.clear()

        from ..graphql.client import GraphQLClient
        GraphQLClient.clear_cookies()

        from .persistent_storage import clear_refresh_token
        if clear_refresh_token():
            logger.info("Persistent tokens cleared")

    async def login(self, email: str, password: str, remember_me: bool = False) -> Tuple[bool, str]:
        """Realiza login con email y password."""
        try:
            mutation = """
                mutation Login($data: LoginInput!) {
                    login(data: $data) {
                        accessToken
                    }
                }
            """

            variables = {
                "data": {
                    "identifier": email,
                    "password": password,
                }
            }

            result = await self.client.execute(mutation, variables, use_auth=False)

            if result and "login" in result:
                login_data = result["login"]

                access_token = login_data.get("accessToken")

                if not access_token:
                    logger.error("Login mutation did not return access_token")
                    return False, "Respuesta invalida del servidor"

                # Extraer datos del usuario del JWT
                user_payload = _decode_jwt_payload(access_token)
                user_data = {}
                if user_payload:
                    user_data = {
                        'username': user_payload.get('username'),
                        'person_id': user_payload.get('person_id'),
                        'session_id': user_payload.get('session_id'),
                        'role': 'admin',  # Por defecto admin, se puede mejorar después
                    }

                # Intentar extraer refresh_token de las cookies (si está disponible)
                refresh_token = None
                try:
                    # El cliente GraphQL almacena cookies en _shared_cookies
                    from ..graphql.client import GraphQLClient
                    cookies_dict = dict(GraphQLClient._shared_cookies)
                    refresh_token = cookies_dict.get('refresh_token')
                    if refresh_token:
                        logger.debug("Refresh token extracted from cookie jar")
                except Exception as e:
                    logger.debug(f"Could not extract refresh_token from cookies: {e}")

                # Guardar tokens como fallback (cookies HTTP-only son primarias)
                self.session.save_session(
                    access_token=access_token,  # Almacenar como fallback
                    refresh_token=refresh_token,  # Almacenar si está disponible
                    user_data=user_data,
                )

                # Si remember_me está activado, guardar refresh_token de forma persistente
                if remember_me and refresh_token:
                    from .persistent_storage import save_refresh_token
                    username = user_data.get('username', email)
                    if save_refresh_token(username, refresh_token):
                        logger.info(f"Refresh token saved persistently for user: {username}")
                    else:
                        logger.warning(f"Failed to save refresh token persistently for user: {username}")
                elif remember_me and not refresh_token:
                    logger.warning("Remember me is enabled but no refresh token available to save")

                logger.info(f"User logged in: {email}")
                return True, "Login exitoso"
            else:
                return False, "Credenciales invalidas"

        except Exception as e:
            logger.error(f"Login error: {e}")
            return False, str(e)

    async def refresh_token(self) -> bool:
        """Renueva el token usando la mutation manual (para casos edge)."""
        try:
            logger.debug("Starting refresh_token mutation")
            mutation = """
                mutation RefreshToken {
                    refreshToken {
                        accessToken
                    }
                }
            """

            logger.debug("Executing refresh_token mutation")
            result = await self.client.execute(mutation, use_auth=False)
            logger.debug(f"refresh_token mutation result: {result}")

            if result and "refreshToken" in result:
                logger.debug("refreshToken found in result")
                refresh_data = result["refreshToken"]
                access_token = refresh_data.get("accessToken")

                if not access_token:
                    logger.error("RefreshToken mutation did not return access_token")
                    return False

                # Extraer datos del usuario del JWT
                user_payload = _decode_jwt_payload(access_token)
                user_data = {}
                if user_payload:
                    user_data = {
                        'username': user_payload.get('username'),
                        'person_id': user_payload.get('person_id'),
                        'session_id': user_payload.get('session_id'),
                        'role': 'admin',  # Por defecto admin
                    }

                # Intentar extraer refresh_token de las cookies (si está disponible)
                refresh_token = None
                try:
                    from ..graphql.client import GraphQLClient
                    cookies_dict = dict(GraphQLClient._shared_cookies)
                    refresh_token = cookies_dict.get('refresh_token')
                    if refresh_token:
                        logger.debug("Refresh token extracted from cookie jar")
                except Exception as e:
                    logger.debug(f"Could not extract refresh_token from cookies: {e}")

                # Actualizar la sesión con los nuevos tokens
                self.session.save_session(
                    access_token=access_token,
                    refresh_token=refresh_token,
                    user_data=user_data,
                )

                logger.info("Token refreshed successfully via manual mutation")
                return True
            else:
                logger.warning(f"refresh_token mutation failed - result: {result}")

        except Exception as e:
            logger.exception(f"Token refresh error: {e}")

        logger.debug("refresh_token returning False")
        return False

    async def logout(self) -> bool:
        """Cierra la sesion actual."""
        logout_confirmed = False
        try:
            mutation = """
                mutation Logout {
                    logout
                }
            """

            result = await self.client.execute(mutation)
            logout_confirmed = bool(result and result.get("logout"))
            if not logout_confirmed:
                logger.warning("Logout mutation did not confirm server-side logout")

        except Exception as e:
            logger.error(f"Logout error: {e}")
        finally:
            self.clear_local_session()
            logger.info("User logged out")
        return logout_confirmed

    def is_authenticated(self) -> bool:
        """Verifica si el usuario esta autenticado."""
        return self.session.is_authenticated()

    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """Obtiene los datos del usuario actual."""
        return self.session.get_current_user()

    def has_permission(self, required_role: str) -> bool:
        """Verifica si el usuario tiene el rol requerido."""
        return self.session.has_permission(required_role)

    async def auto_refresh_if_needed(self) -> bool:
        """Verifica estado de autenticación - el backend maneja renovación automática."""
        # Con cookies HTTP-only, el backend maneja la renovación automática
        # Solo verificamos si el usuario sigue autenticado
        return self.session.is_authenticated()
