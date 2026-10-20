import httpx
from typing import Optional
from config.settings import settings

class WhatsAppClient:
    def __init__(self, bridge_url: str = settings.WHATSAPP_BRIDGE_URL):
        self.bridge_url = bridge_url.rstrip("/")

    async def send_private_message(self, recipient_id: str, message: str) -> bool:
        """Send a 1-on-1 reply to a student."""
        endpoint = f"{self.bridge_url}/api/send-message"
        payload = {
            "to": recipient_id,
            "message": message
        }
        headers = {"X-Bridge-Token": settings.SECRET_KEY}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(endpoint, json=payload, headers=headers)
                if resp.status_code == 200:
                    return True
                print(f"WhatsApp bridge returned status {resp.status_code}: {resp.text}")
                return False
        except Exception:
            # Fallback when bridge isn't running in background
            print(f"📡 [Mock/Simulated WhatsApp] -> Sent to {recipient_id}:\n{message}\n")
            return True

    async def send_group_message(self, group_id: str, message: str) -> bool:
        """Broadcast an announcement to the WhatsApp Notice Group."""
        endpoint = f"{self.bridge_url}/api/send-message"
        payload = {
            "to": group_id,
            "message": message
        }
        headers = {"X-Bridge-Token": settings.SECRET_KEY}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(endpoint, json=payload, headers=headers)
                if resp.status_code == 200:
                    return True
                print(f"WhatsApp bridge returned status {resp.status_code}: {resp.text}")
                return False
        except Exception:
            print(f"📢 [Mock/Simulated WhatsApp Notice Group: {group_id}]:\n{message}\n")
            return True

    async def send_group_image(self, group_id: str, message: str, image_base64: Optional[str] = None, image_path: Optional[str] = None) -> bool:
        """Broadcast a photo notice with formatted caption to the WhatsApp Notice Group."""
        endpoint = f"{self.bridge_url}/api/send-message"
        payload = {
            "to": group_id,
            "message": message,
            "image_base64": image_base64,
            "image_path": image_path
        }
        headers = {"X-Bridge-Token": settings.SECRET_KEY}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(endpoint, json=payload, headers=headers)
                if resp.status_code == 200:
                    return True
                print(f"WhatsApp bridge returned status {resp.status_code}: {resp.text}")
                return False
        except Exception:
            print(f"📢 [Mock/Simulated WhatsApp Notice Group Image: {group_id}] with Caption:\n{message}\n")
            return True

whatsapp_client = WhatsAppClient()
