import os
import sys
from datetime import datetime, timezone
from uuid import uuid4

from flask import Flask, jsonify, request

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging_middleware import Log
from logging_middleware.middleware import log_request, log_response
from notification_app_be.priority import top_priority_notifications


app = Flask(__name__)

notifications = []


@app.before_request
def before():
    log_request()


@app.after_request
def after(response):
    return log_response(response)


@app.get("/")
def health():
    return jsonify(
        {
            "service": "campus-notification-backend",
            "status": "running",
            "endpoints": [
                "POST /notifications",
                "GET /notifications",
                "PATCH /notifications/<notification_id>/read",
                "GET /notifications/priority?limit=10",
            ],
        }
    )


@app.post("/notifications")
def create_notification():
    data = request.get_json(silent=True) or {}
    notification_type = data.get("type")
    message = data.get("message")

    if notification_type not in {"Placement", "Result", "Event"}:
        Log("backend", "warn", "handler", "Rejected notification with invalid type")
        return jsonify({"error": "type must be Placement, Result, or Event"}), 400
    if not message:
        Log("backend", "warn", "handler", "Rejected notification without message")
        return jsonify({"error": "message is required"}), 400

    notification = {
        "id": str(uuid4()),
        "studentId": data.get("studentId"),
        "type": notification_type,
        "message": message,
        "timestamp": data.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        "isRead": False,
    }
    notifications.append(notification)
    Log("backend", "info", "controller", f"Created notification {notification['id']}")
    return jsonify(notification), 201


@app.get("/notifications")
def get_notifications():
    student_id = request.args.get("studentId")
    only_unread = request.args.get("unread", "").lower() == "true"

    result = notifications
    if student_id:
        result = [item for item in result if str(item.get("studentId")) == student_id]
    if only_unread:
        result = [item for item in result if not item.get("isRead")]

    result = sorted(result, key=lambda item: item.get("timestamp", ""), reverse=True)
    Log("backend", "info", "controller", f"Fetched {len(result)} notifications")
    return jsonify({"notifications": result, "count": len(result)}), 200


@app.patch("/notifications/<notification_id>/read")
def mark_read(notification_id):
    for notification in notifications:
        if notification["id"] == notification_id:
            notification["isRead"] = True
            Log("backend", "info", "controller", f"Marked notification {notification_id} as read")
            return jsonify(notification), 200

    Log("backend", "warn", "handler", f"Notification {notification_id} was not found")
    return jsonify({"error": "notification not found"}), 404


@app.get("/notifications/priority")
def priority_inbox():
    limit = int(request.args.get("limit", 10))
    student_id = request.args.get("studentId")

    result = notifications
    if student_id:
        result = [item for item in result if str(item.get("studentId")) == student_id]

    priority_items = top_priority_notifications(result, limit)
    Log("backend", "info", "service", f"Built priority inbox with {len(priority_items)} items")
    return jsonify({"notifications": priority_items, "count": len(priority_items)}), 200


if __name__ == "__main__":
    app.run(debug=True, port=5002)
