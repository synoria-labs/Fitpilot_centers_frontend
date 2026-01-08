"""
Servicio de autenticacion con backend GraphQL.
"""
from typing import Optional, Dict, Any, Tuple

from ..core.logging import get_logger

logger = get_logger(__name__)


def _first_present(data: Dict[str, Any], *keys: str) -> Optional[Any]:
    """Devuelve el primer valor disponible entre varias claves."""
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


class AuthService:
    """Servicio de autenticacion con JWT."""

    def __init__(self, graphql_client, session_store):
        self.client = graphql_client
        self.session = session_store

    async def login(self, email: str, password: str) -> Tuple[bool, str]:
        """Realiza login con email y password."""
        try:
            mutation = """
                mutation Login($data: LoginInput!) {
                    login(data: $data) {
                        access_token
                    }
                }
            """

            variables = {
                "data": {
                    "identifier": email,
                    "password": password,
                }
            }

            result = await self.client.execute(mutation, variables)

            if result and "login" in result:
                login_data = result["login"]

                access_token = login_data.get("access_token")

                if not access_token:
                    logger.error("Login mutation did not return access_token")
                    return False, "Respuesta invalida del servidor"

                # El refresh token se envía como cookie HTTP-only, no en la respuesta GraphQL
                self.session.save_session(
                    access_token=access_token,
                    refresh_token=None,  # Se maneja por cookies
                    user_data={},  # Los datos del usuario no se devuelven en login
                )

                logger.info(f"User logged in: {email}")
                return True, "Login exitoso"
            else:
                return False, "Credenciales invalidas"

        except Exception as e:
            logger.error(f"Login error: {e}")
            return False, str(e)

    async def refresh_token(self) -> bool:
        """Renueva el token de acceso usando el refresh token."""
        try:
            refresh_token_value = self.session.get_refresh_token()
            if not refresh_token_value:
                return False

            mutation = """
                mutation RefreshToken($refreshToken: String!) {
                    refreshToken(refreshToken: $refreshToken) {
                        accessToken
                    }
                }
            """

            variables = {"refreshToken": refresh_token_value}

            result = await self.client.execute(mutation, variables, use_auth=False)

            if result and "refreshToken" in result:
                tokens = result["refreshToken"]
                new_token = _first_present(tokens, "accessToken", "access_token")
                if not new_token:
                    logger.error("Refresh mutation did not return access token")
                    return False

                self.session.update_access_token(new_token)
                logger.info("Token refreshed successfully")
                return True

        except Exception as e:
            logger.error(f"Token refresh error: {e}")

        return False

    async def logout(self):
        """Cierra la sesion actual."""
        try:
            mutation = """
                mutation Logout {
                    logout {
                        success
                    }
                }
            """

            await self.client.execute(mutation)

        except Exception as e:
            logger.error(f"Logout error: {e}")
        finally:
            self.session.clear()
            logger.info("User logged out")

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
        """Refresca el token automaticamente si esta por expirar."""
        if self.session.needs_refresh():
            return await self.refresh_token()
        return True
