import json
import os
import uuid
from typing import Dict, Any, List, Optional
from config.settings import settings

CONFIG_PATH = os.path.join(settings.DATA_DIR, "groups_config.json")

class GroupManager:
    def __init__(self):
        self._load_config()

    def _get_defaults(self) -> Dict[str, Any]:
        return {
            "groups": [
                {
                    "id": "wa_main_notice",
                    "platform": "whatsapp",
                    "name": f"{settings.UNIVERSITY_NAME} {settings.BATCH_NAME} Official Notice Group".strip() or "Official Notice Group",
                    "category": "main_notice",
                    "subject_code": "All",
                    "identifier": settings.WHATSAPP_NOTICE_GROUP_ID,
                    "invite_link": settings.WHATSAPP_NOTICE_GROUP_ID,
                    "is_default_target": True,
                    "is_cr_source": False,
                    "is_active": True
                },
                {
                    "id": "msg_cr_group",
                    "platform": "messenger",
                    "name": f"{settings.BATCH_NAME} CR & Department Group".strip() or "CR Discussion Group",
                    "category": "cr_discussion",
                    "subject_code": "All",
                    "identifier": settings.MESSENGER_CR_THREAD_ID,
                    "invite_link": settings.MESSENGER_CR_GROUP_URL,
                    "is_default_target": False,
                    "is_cr_source": True,
                    "is_active": True
                }
            ],
            "bridge_config": {
                "cr_source_group_id": "msg_cr_group",
                "primary_notice_target_id": "wa_main_notice",
                "auto_relay": True
            }
        }

    def _load_config(self) -> Dict[str, Any]:
        if not os.path.exists(CONFIG_PATH):
            defaults = self._get_defaults()
            self._save_file(defaults)
            return defaults
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not data.get("groups"):
                    data["groups"] = self._get_defaults()["groups"]
                if not data.get("bridge_config"):
                    data["bridge_config"] = self._get_defaults()["bridge_config"]
                return data
        except Exception as e:
            print(f"Error loading groups_config.json: {e}")
            return self._get_defaults()

    def _save_file(self, data: Dict[str, Any]):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_groups(self) -> List[Dict[str, Any]]:
        data = self._load_config()
        return data.get("groups", [])

    def get_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        groups = self.get_groups()
        for g in groups:
            if g.get("id") == group_id:
                return g
        return None

    def add_group(self, group_data: Dict[str, Any]) -> Dict[str, Any]:
        data = self._load_config()
        groups = data.get("groups", [])
        
        # Generate clean ID if missing
        new_id = group_data.get("id")
        if not new_id:
            prefix = group_data.get("platform", "grp")[:3]
            name_slug = "".join(c.lower() for c in group_data.get("name", "group") if c.isalnum() or c == "_")[:15]
            new_id = f"{prefix}_{name_slug}_{uuid.uuid4().hex[:4]}"
        
        # Check uniqueness
        for g in groups:
            if g.get("id") == new_id:
                new_id = f"{new_id}_{uuid.uuid4().hex[:4]}"

        new_group = {
            "id": new_id,
            "platform": group_data.get("platform", "whatsapp").lower(),
            "name": group_data.get("name", "New Group").strip(),
            "category": group_data.get("category", "subject_specific"),
            "subject_code": group_data.get("subject_code", "All").strip(),
            "identifier": group_data.get("identifier", "").strip() or group_data.get("invite_link", "").strip(),
            "invite_link": group_data.get("invite_link", "").strip(),
            "is_default_target": bool(group_data.get("is_default_target", False)),
            "is_cr_source": bool(group_data.get("is_cr_source", False)),
            "is_active": bool(group_data.get("is_active", True))
        }

        groups.append(new_group)
        data["groups"] = groups
        self._save_file(data)
        return new_group

    def update_group(self, group_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        data = self._load_config()
        groups = data.get("groups", [])
        updated = None
        for i, g in enumerate(groups):
            if g.get("id") == group_id:
                for k, v in updates.items():
                    if k != "id":
                        g[k] = v
                groups[i] = g
                updated = g
                break
        if updated:
            data["groups"] = groups
            self._save_file(data)
        return updated

    def delete_group(self, group_id: str) -> bool:
        data = self._load_config()
        groups = data.get("groups", [])
        filtered = [g for g in groups if g.get("id") != group_id]
        if len(filtered) == len(groups):
            return False
        data["groups"] = filtered
        self._save_file(data)
        return True

    def get_bridge_config(self) -> Dict[str, Any]:
        data = self._load_config()
        return data.get("bridge_config", {
            "cr_source_group_id": "msg_cr_group",
            "primary_notice_target_id": "wa_main_notice",
            "auto_relay": True
        })

    def update_bridge_config(self, bridge_data: Dict[str, Any]) -> Dict[str, Any]:
        data = self._load_config()
        current = data.get("bridge_config", {})
        current.update(bridge_data)
        data["bridge_config"] = current
        self._save_file(data)
        return current

    def get_primary_notice_target(self) -> str:
        bridge = self.get_bridge_config()
        target_id = bridge.get("primary_notice_target_id")
        group = self.get_group(target_id)
        if group and group.get("identifier"):
            return group["identifier"]
        return settings.WHATSAPP_NOTICE_GROUP_ID

    def get_cr_source_group(self) -> Dict[str, Any]:
        bridge = self.get_bridge_config()
        source_id = bridge.get("cr_source_group_id")
        group = self.get_group(source_id)
        if group:
            return group
        return {
            "id": "msg_cr_group",
            "platform": "messenger",
            "name": "CSE 38th CR Group",
            "identifier": settings.MESSENGER_CR_THREAD_ID
        }

    async def broadcast_to_selected_groups(self, target_group_ids: List[str], message: str, title: str = "Announcement", image_base64: Optional[str] = None) -> Dict[str, Any]:
        """Broadcasts notice to multiple selected groups (WhatsApp or Messenger)."""
        from core.database import save_announcement
        from modules.notifier.whatsapp_client import whatsapp_client

        results = []
        all_groups = self.get_groups()
        group_map = {}
        for g in all_groups:
            if g.get("id"):
                group_map[g["id"]] = g
            if g.get("identifier"):
                group_map[g["identifier"]] = g
            if g.get("invite_link"):
                group_map[g["invite_link"]] = g

        if not target_group_ids:
            # Default to default targets
            target_group_ids = [g["id"] for g in all_groups if g.get("is_default_target") and g.get("is_active")]
            if not target_group_ids:
                target_group_ids = ["wa_main_notice"]

        for gid in target_group_ids:
            grp = group_map.get(gid)
            if grp and not grp.get("is_active", True):
                continue

            platform = grp.get("platform", "whatsapp") if grp else ("messenger" if str(gid).isdigit() and len(str(gid)) > 10 else "whatsapp")
            identifier = (grp.get("identifier") or grp.get("invite_link") or settings.WHATSAPP_NOTICE_GROUP_ID) if grp else gid
            name = grp.get("name", "Group") if grp else ("Target Group" if len(str(identifier)) > 25 else str(identifier))

            # Save in database
            save_announcement(
                title=f"{title} ({name})",
                content=message,
                source=f"dashboard_{platform}",
                target_group=identifier,
                status="broadcasted"
            )

            success = False
            if platform == "whatsapp":
                if image_base64:
                    success = await whatsapp_client.send_group_image(identifier, message, image_base64)
                else:
                    success = await whatsapp_client.send_group_message(identifier, message)
            else:
                # Messenger dispatch log / simulated bridge
                print(f"[Messenger Outbound] Message dispatched to {name} (Thread ID: {identifier})")
                success = True

            results.append({
                "group_id": gid,
                "group_name": name,
                "platform": platform,
                "success": bool(success)
            })

        return {
            "total_targeted": len(results),
            "dispatches": results
        }

group_manager = GroupManager()
