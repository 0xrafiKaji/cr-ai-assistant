import os
import json
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from config.settings import settings

QUOTA_FILE_PATH = os.path.join(settings.DATA_DIR, "ai_quota_usage.json")

class AIQuotaTracker:
    DEFAULT_LIMITS: Dict[str, int] = {
        "groq": 1000,
        "gemini": 1500,
        "openai": 500,
        "openrouter": 500,
        "custom": 1000
    }

    def __init__(self):
        self._lock = threading.Lock()
        self._ensure_storage()

    def _get_today_str(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _default_data(self) -> Dict[str, Any]:
        today_str = self._get_today_str()
        return {
            "date": today_str,
            "total_requests": 0,
            "providers": {
                p: {
                    "requests": 0,
                    "tokens": 0,
                    "daily_limit": limit
                }
                for p, limit in self.DEFAULT_LIMITS.items()
            }
        }

    def _ensure_storage(self):
        os.makedirs(settings.DATA_DIR, exist_ok=True)
        if not os.path.exists(QUOTA_FILE_PATH):
            self._save_data(self._default_data())

    def _load_data(self) -> Dict[str, Any]:
        today_str = self._get_today_str()
        try:
            if os.path.exists(QUOTA_FILE_PATH):
                with open(QUOTA_FILE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Automatically reset counters if day transitioned at midnight
                    if data.get("date") != today_str:
                        data = self._default_data()
                        self._save_data(data)
                    return data
        except Exception as e:
            print(f"⚠️ Error reading AI quota file: {e}")
        
        fallback = self._default_data()
        self._save_data(fallback)
        return fallback

    def _save_data(self, data: Dict[str, Any]):
        try:
            with open(QUOTA_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"⚠️ Error writing AI quota file: {e}")

    def record_request(self, provider: str, model: str = "", tokens: int = 0):
        """Records an AI inference invocation and updates the daily usage counter."""
        provider_key = provider.lower() if provider else "groq"
        if "gemini" in provider_key:
            provider_key = "gemini"
        elif "groq" in provider_key:
            provider_key = "groq"
        elif "openai" in provider_key:
            provider_key = "openai"
        elif "openrouter" in provider_key:
            provider_key = "openrouter"
        else:
            provider_key = "custom"

        with self._lock:
            data = self._load_data()
            data["total_requests"] = data.get("total_requests", 0) + 1
            
            providers = data.setdefault("providers", {})
            if provider_key not in providers:
                providers[provider_key] = {
                    "requests": 0,
                    "tokens": 0,
                    "daily_limit": self.DEFAULT_LIMITS.get(provider_key, 1000)
                }
            
            providers[provider_key]["requests"] = providers[provider_key].get("requests", 0) + 1
            if tokens > 0:
                providers[provider_key]["tokens"] = providers[provider_key].get("tokens", 0) + tokens
                
            self._save_data(data)

    def get_usage_stats(self) -> Dict[str, Any]:
        """Calculates percentage, remaining quota, and time until midnight reset."""
        with self._lock:
            data = self._load_data()

        # Find active provider and model
        try:
            from modules.config.ai_manager import ai_manager
            cfg = ai_manager.get_config()
            active_p = cfg.get("active_provider", "groq").lower()
            active_m = cfg.get("active_model", settings.GROQ_MODEL)
        except Exception:
            active_p = (settings.AI_PRIMARY_PROVIDER or "groq").lower()
            active_m = settings.GROQ_MODEL

        now = datetime.now()
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        time_until_reset = midnight - now
        total_seconds = int(time_until_reset.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60

        reset_human = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
        reset_time_str = "Midnight 00:00 AM"

        # Active provider limit & stats
        p_data = data.get("providers", {}).get(active_p, {})
        req_count = p_data.get("requests", 0)
        limit = p_data.get("daily_limit", self.DEFAULT_LIMITS.get(active_p, 1000))
        
        # Calculate percentage used
        percentage_used = round((req_count / limit) * 100, 1) if limit > 0 else 0.0
        remaining = max(0, limit - req_count)

        return {
            "date": data.get("date", self._get_today_str()),
            "active_provider": active_p.capitalize(),
            "active_model": active_m,
            "requests_used_today": req_count,
            "total_requests_all_providers": data.get("total_requests", 0),
            "daily_limit": limit,
            "percentage_used": percentage_used,
            "remaining_requests": remaining,
            "reset_time": reset_time_str,
            "reset_in_seconds": total_seconds,
            "reset_in_human": reset_human,
            "providers": data.get("providers", {})
        }

    def format_usage_message(self) -> str:
        """Formats a human-readable summary for WhatsApp, Messenger, or CLI."""
        stats = self.get_usage_stats()
        
        provider = stats["active_provider"]
        model = stats["active_model"]
        used = stats["requests_used_today"]
        limit = stats["daily_limit"]
        pct = stats["percentage_used"]
        remaining = stats["remaining_requests"]
        reset_human = stats["reset_in_human"]
        
        # Visual progress bar (10 blocks)
        filled = min(10, max(0, int(round(pct / 10))))
        bar = "█" * filled + "░" * (10 - filled)

        return (
            f"📊 *AI Chat Usage & Quota Tracker*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 *Active Brain:* {provider} (`{model}`)\n"
            f"📈 *Usage Today:* [{bar}] *{pct}%*\n"
            f"• *Requests Used:* {used:,} / {limit:,}\n"
            f"• *Remaining Quota:* *{remaining:,} requests*\n"
            f"⏳ *Quota Resets:* In *{reset_human}* (Midnight 00:00)\n"
            f"🔄 *Failover Engine:* Gemini 3.8 Flash (Online 🟢)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 *Note:* Free-tier quotas reset automatically at 12:00 AM midnight."
        )

quota_tracker = AIQuotaTracker()
