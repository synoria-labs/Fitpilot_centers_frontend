"""
Servicio para gestión de plantillas WhatsApp.
"""
from typing import List, Optional, Dict, Any
from ..core.logging import get_logger

logger = get_logger(__name__)

class WhatsAppService:
    """Servicio para operaciones con WhatsApp."""
    
    def __init__(self, graphql_client):
        self.client = graphql_client
    
    async def get_templates(self) -> List[Dict[str, Any]]:
        """Obtiene las plantillas de WhatsApp."""
        try:
            query = """
                query GetTemplates {
                    whatsappTemplates {
                        id
                        template_name
                        template_namespace
                        template_language
                        template_status
                        components
                        created_at
                        updated_at
                    }
                }
            """
            
            result = await self.client.execute(query)
            
            if result and 'whatsappTemplates' in result:
                return result['whatsappTemplates']
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting WhatsApp templates: {e}")
            return []
    
    async def create_template(
        self,
        name: str,
        language: str,
        components: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Crea una nueva plantilla."""
        try:
            mutation = """
                mutation CreateTemplate($input: CreateTemplateInput!) {
                    createWhatsAppTemplate(input: $input) {
                        success
                        template {
                            id
                            template_name
                            template_status
                        }
                        message
                    }
                }
            """
            
            variables = {
                'input': {
                    'name': name,
                    'language': language,
                    'components': components
                }
            }
            
            result = await self.client.execute(mutation, variables)
            
            if result and 'createWhatsAppTemplate' in result:
                return result['createWhatsAppTemplate']
            
            return {'success': False, 'message': 'Error al crear plantilla'}
            
        except Exception as e:
            logger.error(f"Error creating template: {e}")
            return {'success': False, 'message': str(e)}
    
    async def send_message(
        self,
        phone_number: str,
        template_name: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Envía un mensaje usando una plantilla."""
        try:
            mutation = """
                mutation SendWhatsAppMessage($input: SendMessageInput!) {
                    sendWhatsAppMessage(input: $input) {
                        success
                        message_id
                        status
                        message
                    }
                }
            """
            
            variables = {
                'input': {
                    'phone_number': phone_number,
                    'template_name': template_name,
                    'parameters': parameters or {}
                }
            }
            
            result = await self.client.execute(mutation, variables)
            
            if result and 'sendWhatsAppMessage' in result:
                return result['sendWhatsAppMessage']
            
            return {'success': False, 'message': 'Error al enviar mensaje'}
            
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")
            return {'success': False, 'message': str(e)}
    
    async def get_conversations(
        self,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Obtiene las conversaciones recientes."""
        try:
            query = """
                query GetConversations($limit: Int!) {
                    conversations(limit: $limit) {
                        id
                        contact {
                            wa_id
                            phone_number
                            name
                        }
                        status
                        last_message {
                            text_content
                            timestamp
                            direction
                        }
                    }
                }
            """
            
            variables = {'limit': limit}
            result = await self.client.execute(query, variables)
            
            if result and 'conversations' in result:
                return result['conversations']
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting conversations: {e}")
            return []
    
    async def send_bulk_message(
        self,
        phone_numbers: List[str],
        template_name: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Envía mensajes masivos."""
        try:
            mutation = """
                mutation SendBulkMessages($input: SendBulkInput!) {
                    sendBulkWhatsApp(input: $input) {
                        success
                        sent_count
                        failed_count
                        failed_numbers
                        message
                    }
                }
            """
            
            variables = {
                'input': {
                    'phone_numbers': phone_numbers,
                    'template_name': template_name,
                    'parameters': parameters or {}
                }
            }
            
            result = await self.client.execute(mutation, variables)
            
            if result and 'sendBulkWhatsApp' in result:
                return result['sendBulkWhatsApp']
            
            return {'success': False, 'message': 'Error al enviar mensajes'}
            
        except Exception as e:
            logger.error(f"Error sending bulk messages: {e}")
            return {'success': False, 'message': str(e)}
