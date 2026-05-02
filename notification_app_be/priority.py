from datetime import datetime, timezone
from heapq import heappush, heappushpop
from typing import Any, Dict, Iterable, List


TYPE_WEIGHT = {
    "Placement": 3,
    "Result": 2,
    "Event": 1,
}


def _parse_time(value: str) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def _score(notification: Dict[str, Any]) -> tuple:
    notification_type = notification.get("type") or notification.get("Type")
    timestamp = notification.get("timestamp") or notification.get("Timestamp")
    return (
        TYPE_WEIGHT.get(notification_type, 0),
        _parse_time(timestamp).timestamp(),
    )


def top_priority_notifications(
    notifications: Iterable[Dict[str, Any]],
    limit: int = 10,
) -> List[Dict[str, Any]]:
    heap = []

    for notification in notifications:
        if notification.get("isRead") is True:
            continue

        item = (_score(notification), str(notification.get("id", "")), notification)
        if len(heap) < limit:
            heappush(heap, item)
        else:
            heappushpop(heap, item)

    return [
        notification
        for _, _, notification in sorted(heap, key=lambda item: item[0], reverse=True)
    ]


if __name__ == "__main__":
    sample_notifications = [
        {
            "id": "1",
            "type": "Event",
            "message": "farewell",
            "timestamp": "2026-04-22T17:51:06+00:00",
            "isRead": False,
        },
        {
            "id": "2",
            "type": "Placement",
            "message": "CSX Corporation hiring",
            "timestamp": "2026-04-22T17:51:18+00:00",
            "isRead": False,
        },
        {
            "id": "3",
            "type": "Result",
            "message": "mid-sem",
            "timestamp": "2026-04-22T17:51:30+00:00",
            "isRead": False,
        },
    ]

    for item in top_priority_notifications(sample_notifications):
        print(f"{item['type']} | {item['timestamp']} | {item['message']}")
