import logging
from .ai_agent import AIAgent
from .groq_service import GroqService

logger = logging.getLogger(__name__)

class AIService:
    """
    Unified AI Service adapter delegating directly to AIAgent and GroqService.
    Provides backwards compatibility for existing endpoints and templates.
    """
    def __init__(self):
        self.agent = AIAgent()
        self.groq = GroqService()

    def generate_response(self, user, query, conversation_history=None, context=None, confirmed_action=None):
        """
        Processes an AI assistant request through the Action-Based AI Agent.
        Returns formatted HTML / markdown text and supports action execution.
        """
        res = self.agent.process_request(
            user=user,
            query=query,
            conversation_history=conversation_history,
            current_context=context,
            confirmed_action=confirmed_action
        )
        return res

# Global Singleton
ai_service = AIService()
