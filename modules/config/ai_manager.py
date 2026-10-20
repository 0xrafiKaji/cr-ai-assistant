import json
import os
import time
import httpx
from typing import Dict, Any, List, Optional
from config.settings import settings

AI_CONFIG_PATH = os.path.join(settings.DATA_DIR, "ai_config.json")

class AIManager:
    def __init__(self):
        self._load_config()

    def _get_defaults(self) -> Dict[str, Any]:
        return {
            "active_provider": settings.AI_PRIMARY_PROVIDER or "groq",
            "active_model": settings.GROQ_MODEL or "openai/gpt-oss-120b",
            "providers": {
                "groq": {
                    "name": "Groq LPU (Ultra Fast)",
                    "api_key": settings.GROQ_API_KEY or "",
                    "base_url": "https://api.groq.com/openai/v1",
                    "default_model": settings.GROQ_MODEL or "openai/gpt-oss-120b",
                    "available_models": [
                        "openai/gpt-oss-120b",
                        "llama-3.3-70b-versatile",
                        "llama-3.1-8b-instant",
                        "mixtral-8x7b-32768"
                    ],
                    "enabled": True
                },
                "gemini": {
                    "name": "Google Gemini (Multimodal)",
                    "api_key": settings.GEMINI_API_KEY or "",
                    "base_url": "",
                    "default_model": settings.GEMINI_MODEL or "gemini-3.8-flash",
                    "available_models": [
                        "gemini-3.8-flash",
                        "gemini-2.0-flash-exp",
                        "gemini-1.5-flash",
                        "gemini-1.5-pro"
                    ],
                    "enabled": True
                },
                "openai": {
                    "name": "OpenAI Official",
                    "api_key": "",
                    "base_url": "https://api.openai.com/v1",
                    "default_model": "gpt-4o-mini",
                    "available_models": [
                        "gpt-4o-mini",
                        "gpt-4o",
                        "gpt-3.5-turbo"
                    ],
                    "enabled": False
                },
                "openrouter": {
                    "name": "OpenRouter AI (Aggregator)",
                    "api_key": "",
                    "base_url": "https://openrouter.ai/api/v1",
                    "default_model": "meta-llama/llama-3.3-70b-instruct:free",
                    "available_models": [
                        "meta-llama/llama-3.3-70b-instruct:free",
                        "deepseek/deepseek-chat",
                        "anthropic/claude-3.5-haiku"
                    ],
                    "enabled": False
                },
                "custom": {
                    "name": "Custom Endpoint (Ollama / Local / DeepSeek)",
                    "api_key": "",
                    "base_url": "http://localhost:11434/v1",
                    "default_model": "llama3",
                    "available_models": [
                        "llama3",
                        "deepseek-r1",
                        "mistral",
                        "qwen2.5"
                    ],
                    "enabled": False
                }
            }
        }

    def _load_config(self) -> Dict[str, Any]:
        if not os.path.exists(AI_CONFIG_PATH):
            defaults = self._get_defaults()
            self._save_file(defaults)
            return defaults
        try:
            with open(AI_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except Exception as e:
            print(f"Error loading ai_config.json: {e}")
            return self._get_defaults()

    def _save_file(self, data: Dict[str, Any]):
        os.makedirs(os.path.dirname(AI_CONFIG_PATH), exist_ok=True)
        with open(AI_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_config(self) -> Dict[str, Any]:
        return self._load_config()

    def update_active_selection(self, provider: str, model: str) -> Dict[str, Any]:
        data = self._load_config()
        data["active_provider"] = provider
        data["active_model"] = model
        self._save_file(data)
        return {"status": "success", "active_provider": provider, "active_model": model}

    def update_provider_details(self, provider_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        data = self._load_config()
        providers = data.get("providers", {})
        if provider_id not in providers:
            providers[provider_id] = {}
        providers[provider_id].update(updates)
        data["providers"] = providers
        self._save_file(data)
        return {"status": "success", "provider": providers[provider_id]}

    def add_custom_provider(self, provider_id: str, name: str, base_url: str, api_key: str, default_model: str) -> Dict[str, Any]:
        data = self._load_config()
        clean_id = "".join(c.lower() for c in provider_id if c.isalnum() or c == "_")
        if not clean_id:
            clean_id = f"provider_{int(time.time())}"
        
        data["providers"][clean_id] = {
            "name": name.strip(),
            "base_url": base_url.strip(),
            "api_key": api_key.strip(),
            "default_model": default_model.strip(),
            "available_models": [default_model.strip()],
            "enabled": True
        }
        self._save_file(data)
        return {"status": "success", "provider_id": clean_id, "provider": data["providers"][clean_id]}

    async def test_provider_connection(self, provider_id: str, model: Optional[str] = None, api_key: Optional[str] = None, base_url: Optional[str] = None) -> Dict[str, Any]:
        """Performs a live test probe against the selected AI provider."""
        config = self.get_config()
        p_info = config.get("providers", {}).get(provider_id, {})
        key = api_key if api_key is not None else p_info.get("api_key", "")
        target_model = model or p_info.get("default_model", "")
        url = base_url or p_info.get("base_url", "")

        start_time = time.time()

        try:
            if provider_id == "gemini":
                # Test with google-genai
                if not key:
                    return {"status": "error", "message": "Gemini API key is empty"}
                from google import genai
                client = genai.Client(api_key=key)
                resp = client.models.generate_content(
                    model=target_model or "gemini-1.5-flash",
                    contents="Reply with 'AI Active' in 2 words."
                )
                latency = round((time.time() - start_time) * 1000, 2)
                return {
                    "status": "success",
                    "latency_ms": latency,
                    "response": resp.text.strip() if resp and resp.text else "OK",
                    "provider": provider_id,
                    "model": target_model
                }
            else:
                # OpenAI-compatible test (Groq, OpenAI, OpenRouter, Custom)
                if not url:
                    if provider_id == "groq":
                        url = "https://api.groq.com/openai/v1"
                    elif provider_id == "openai":
                        url = "https://api.openai.com/v1"
                    elif provider_id == "openrouter":
                        url = "https://openrouter.ai/api/v1"
                    else:
                        url = "http://localhost:11434/v1"

                endpoint = f"{url.rstrip('/')}/chat/completions"
                headers = {
                    "Content-Type": "application/json"
                }
                if key:
                    headers["Authorization"] = f"Bearer {key}"

                payload = {
                    "model": target_model or "llama3",
                    "messages": [{"role": "user", "content": "Reply with 'AI Active' in 2 words."}],
                    "max_tokens": 15
                }

                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.post(endpoint, headers=headers, json=payload)
                    latency = round((time.time() - start_time) * 1000, 2)
                    if res.status_code in [200, 201]:
                        data = res.json()
                        reply = data["choices"][0]["message"]["content"].strip()
                        return {
                            "status": "success",
                            "latency_ms": latency,
                            "response": reply,
                            "provider": provider_id,
                            "model": target_model
                        }
                    else:
                        return {
                            "status": "error",
                            "status_code": res.status_code,
                            "message": f"HTTP {res.status_code}: {res.text[:120]}"
                        }
        except Exception as e:
            return {"status": "error", "message": str(e)}

ai_manager = AIManager()
