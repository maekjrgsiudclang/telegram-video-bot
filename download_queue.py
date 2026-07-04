import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class QueueItem:
    url: str
    status: str = "pending"


@dataclass
class UserQueue:
    user_id: int
    items: List[QueueItem] = field(default_factory=list)
    processing: bool = False


class DownloadQueue:
    def __init__(self):
        self.queues: Dict[int, UserQueue] = {}

    def add(self, user_id: int, url: str) -> int:
        if user_id not in self.queues:
            self.queues[user_id] = UserQueue(user_id=user_id)
        item = QueueItem(url=url)
        self.queues[user_id].items.append(item)
        return len(self.queues[user_id].items)

    def get_pending(self, user_id: int) -> Optional[QueueItem]:
        if user_id not in self.queues:
            return None
        for item in self.queues[user_id].items:
            if item.status == "pending":
                return item
        return None

    def mark_processing(self, user_id: int, url: str):
        if user_id in self.queues:
            for item in self.queues[user_id].items:
                if item.url == url and item.status == "pending":
                    item.status = "processing"
                    self.queues[user_id].processing = True
                    break

    def mark_done(self, user_id: int, url: str):
        if user_id in self.queues:
            for item in self.queues[user_id].items:
                if item.url == url and item.status == "processing":
                    item.status = "done"
                    self.queues[user_id].processing = False
                    break

    def mark_failed(self, user_id: int, url: str):
        if user_id in self.queues:
            for item in self.queues[user_id].items:
                if item.url == url and item.status == "processing":
                    item.status = "failed"
                    self.queues[user_id].processing = False
                    break

    def get_status(self, user_id: int) -> dict:
        if user_id not in self.queues:
            return {"total": 0, "pending": 0, "processing": 0, "done": 0, "failed": 0, "items": []}
        items = self.queues[user_id].items
        return {
            "total": len(items),
            "pending": sum(1 for i in items if i.status == "pending"),
            "processing": sum(1 for i in items if i.status == "processing"),
            "done": sum(1 for i in items if i.status == "done"),
            "failed": sum(1 for i in items if i.status == "failed"),
            "items": items,
        }

    def clear(self, user_id: int):
        if user_id in self.queues:
            self.queues[user_id].items = []
            self.queues[user_id].processing = False

    def remove_done(self, user_id: int):
        if user_id in self.queues:
            self.queues[user_id].items = [
                i for i in self.queues[user_id].items if i.status not in ("done", "failed")
            ]


queue = DownloadQueue()
