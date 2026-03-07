import json
import os
from collections import defaultdict

TRACKER_FILE = "kick_tracker_data.json"

class KickTracker:
    def __init__(self):
        self.data = {}  # {chat_id: {admin_id: count}}
        self._load()

    def _load(self):
        if os.path.exists(TRACKER_FILE):
            try:
                with open(TRACKER_FILE, "r") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}

    def _save(self):
        with open(TRACKER_FILE, "w") as f:
            json.dump(self.data, f, indent=2)

    def add_action(self, admin_id: int, chat_id: int, action_type: str) -> int:
        """أضف عملية طرد/حظر وارجع العدد الكلي"""
        chat_key = str(chat_id)
        admin_key = str(admin_id)

        if chat_key not in self.data:
            self.data[chat_key] = {}

        if admin_key not in self.data[chat_key]:
            self.data[chat_key][admin_key] = 0

        self.data[chat_key][admin_key] += 1
        self._save()
        return self.data[chat_key][admin_key]

    def reset(self, admin_id: int, chat_id: int):
        """إعادة العداد لصفر"""
        chat_key = str(chat_id)
        admin_key = str(admin_id)
        if chat_key in self.data and admin_key in self.data[chat_key]:
            self.data[chat_key][admin_key] = 0
            self._save()

    def get_stats(self, chat_id: int) -> dict:
        """إرجاع إحصائيات الجروب"""
        return self.data.get(str(chat_id), {})

    def get_count(self, admin_id: int, chat_id: int) -> int:
        """إرجاع عدد معين"""
        return self.data.get(str(chat_id), {}).get(str(admin_id), 0)
