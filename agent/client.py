"""GLM 5.1 API client for trading agent."""
import os
import json
import logging
import requests
from typing import Optional, Dict, Any
from agent.state_manager import StateManager

logger = logging.getLogger(__name__)

class GLMClient:
    """Client for Zhipu GLM 5.1 API with multimodal support."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ZHIPU_GLM_API_KEY")
        self.base_url = "https://open.bigmodel.cn/api/paas/v4"
        self.session = requests.Session()
        self.state = StateManager()
        
    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Request-ID": self._generate_request_id()
        }
    
    def _generate_request_id(self) -> str:
        import time
        return f"req-{int(time.time())}-{hash(self.api_key) % 10000}"
    
    def call(self, messages: list, model: str = "glm-5.1", 
             temperature: float = 0.7, max_tokens: int = 2048) -> Optional[Dict]:
        """
        Call GLM API with message history.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name (glm-5.1, glm-4-flash, etc.)
            temperature: Sampling temperature
            max_tokens: Max response tokens
            
        Returns:
            Dict with 'choices' containing response, or None on error
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._get_headers(),
                timeout=30
            )
            
            # Check for rate limit before raising exception
            if response.status_code == 429:
                return {"error": "rate_limit", "status_code": 429}
            
            response.raise_for_status()
            data = response.json()
            
            if data.get("choices"):
                return {
                    "content": data["choices"][0].get("message", {}).get("content", ""),
                    "usage": data.get("usage", {}),
                    "model": model
                }
            return None
            
        except Exception:
            logger.exception("GLM API error")
            return None
    
    def call_vision(self, messages: list, image_url: str = None,
                    **kwargs) -> Optional[Dict]:
        """
        Call GLM with vision support.
        
        Args:
            messages: Message history
            image_url: URL of image to analyze
            **kwargs: Additional params (model, temperature, etc.)
            
        Returns:
            Response dict or None
        """
        if image_url:
            # Add image to last user message if not already present
            if messages and messages[-1]["role"] == "user":
                content = messages[-1]["content"]
                if isinstance(content, list):
                    content.append({"type": "image_url", "image_url": {"url": image_url}})
                else:
                    messages[-1]["content"] = [{"type": "text", "text": content},
                                               {"type": "image_url", "image_url": {"url": image_url}}]
        
        return self.call(messages, **kwargs)
    
    def get_cost(self, response: Optional[Dict]) -> float:
        """Calculate API cost in USD."""
        if not response or "usage" not in response:
            return 0.0
        
        usage = response["usage"]
        # GLM 5.1 pricing: input $0.0055/tk, output $0.011/tk (approximate)
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        
        cost = (input_tokens * 0.0055 + output_tokens * 0.011) / 1000
        return cost
    
    def is_rate_limited(self, response: Optional[Dict]) -> bool:
        """Check if API returned rate limit error."""
        if not response:
            return False
        return response.get("status_code") == 429
