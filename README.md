# Stage 1

## Core actions

The notification platform should support these actions:

- create a notification
- fetch notifications for a student
- fetch unread notifications
- mark one notification as read
- mark all notifications as read
- fetch priority notifications
- deliver real-time updates to connected users

I would keep the API small and predictable. The frontend should not need to understand internal database details. It should receive notification objects in one consistent shape.

## REST API design

### Create notification

`POST /notifications`

Headers:

```http
Content-Type: application/json
Authorization: Bearer <token>
```

Request:

```json
{
  "studentId": 1042,
  "type": "Placement",
  "message": "CSX Corporation hiring",
  "metadata": {
    "company": "CSX Corporation",
    "deadline": "2026-04-30"
  }
}
```

Response:

```json
{
  "id": "b283218f-ea5a-4b7c-93a9-1f2f240d64b0",
  "studentId": 1042,
  "type": "Placement",
  "message": "CSX Corporation hiring",
  "metadata": {
    "company": "CSX Corporation",
    "deadline": "2026-04-30"
  },
  "isRead": false,
  "createdAt": "2026-04-22T17:51:18Z"
}
```

### Fetch notifications

`GET /students/{studentId}/notifications?unread=true&limit=20&cursor=<cursor>`

Response:

```json
{
  "items": [
    {
      "id": "b283218f-ea5a-4b7c-93a9-1f2f240d64b0",
      "type": "Placement",
      "message": "CSX Corporation hiring",
      "isRead": false,
      "createdAt": "2026-04-22T17:51:18Z"
    }
  ],
  "nextCursor": "2026-04-22T17:50:54Z"
}
```

### Mark notification as read

`PATCH /students/{studentId}/notifications/{notificationId}/read`

Response:

```json
{
  "id": "b283218f-ea5a-4b7c-93a9-1f2f240d64b0",
  "isRead": true
}
```

### Mark all as read

`PATCH /students/{studentId}/notifications/read-all`

Response:

```json
{
  "updatedCount": 18
}
```

### Priority inbox

`GET /students/{studentId}/notifications/priority?limit=10`

Response:

```json
{
  "items": [
    {
      "id": "b283218f-ea5a-4b7c-93a9-1f2f240d64b0",
      "type": "Placement",
      "message": "CSX Corporation hiring",
      "isRead": false,
      "createdAt": "2026-04-22T17:51:18Z"
    }
  ]
}
```

## Real-time mechanism

I would use WebSockets for real-time in-app notifications. When a student logs in, the client opens a socket connection and joins a room such as `student:1042`. When a new notification is created, the backend saves it first and then publishes it to the student's room.

For reliability, WebSockets should be treated as a fast delivery path, not the source of truth. If the socket is disconnected, the student still gets the notification from the normal `GET /notifications` API after reconnecting.

# Stage 2

## Storage choice

I would use PostgreSQL. Notifications have clear relationships with students, reads, types, timestamps, and delivery status. A relational database gives strong consistency, indexing, pagination, and simple querying for unread notifications.

## Schema

```sql
CREATE TYPE notification_type AS ENUM ('Event', 'Result', 'Placement');

CREATE TABLE students (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255)
);

CREATE TABLE notifications (
    id UUID PRIMARY KEY,
    type notification_type NOT NULL,
    message TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE student_notifications (
    student_id BIGINT NOT NULL REFERENCES students(id),
    notification_id UUID NOT NULL REFERENCES notifications(id),
    is_read BOOLEAN NOT NULL DEFAULT false,
    read_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    PRIMARY KEY (student_id, notification_id)
);
```

## Queries

Create notification:

```sql
INSERT INTO notifications (id, type, message, metadata)
VALUES ($1, $2, $3, $4);
```

Assign notification to students:

```sql
INSERT INTO student_notifications (student_id, notification_id)
SELECT id, $1
FROM students
WHERE id = ANY($2);
```

Fetch unread notifications:

```sql
SELECT n.id, n.type, n.message, n.metadata, n.created_at
FROM student_notifications sn
JOIN notifications n ON n.id = sn.notification_id
WHERE sn.student_id = $1
  AND sn.is_read = false
ORDER BY n.created_at DESC
LIMIT $2;
```

Mark as read:

```sql
UPDATE student_notifications
SET is_read = true, read_at = now()
WHERE student_id = $1
  AND notification_id = $2;
```

## Scaling issues

As volume grows, the biggest issues will be slow unread queries, too many rows for broadcast notifications, and high write load during mass sends. I would solve this with proper composite indexes, cursor pagination, batching, background jobs, and possibly table partitioning by date for old notifications.

# Stage 3

The given query is logically correct if the table has one row per student notification and `createdAt` belongs to that same row:

```sql
SELECT *
FROM notifications
WHERE studentID = 1042
  AND isRead = false
ORDER BY createdAt DESC;
```

It is slow because the database may scan many rows before finding unread rows for one student, then sort the result by `createdAt`. At 5,000,000 notifications this becomes expensive without the right index.

I would avoid `SELECT *` and add a composite index that matches the filter and ordering:

```sql
CREATE INDEX idx_notifications_student_unread_created
ON notifications (studentID, isRead, createdAt DESC);
```

Better query:

```sql
SELECT id, notificationType, message, createdAt
FROM notifications
WHERE studentID = 1042
  AND isRead = false
ORDER BY createdAt DESC
LIMIT 20;
```

The cost becomes roughly `O(log n + k)` where `k` is the number of rows returned, instead of scanning and sorting a large part of the table.

Adding indexes on every column is not effective. It slows inserts and updates, uses extra disk, and many indexes will never be used. Indexes should follow actual query patterns.

Students who got placement notifications in the last 7 days:

```sql
SELECT DISTINCT studentID
FROM notifications
WHERE notificationType = 'Placement'
  AND createdAt >= now() - interval '7 days';
```

Useful index:

```sql
CREATE INDEX idx_notifications_type_created_student
ON notifications (notificationType, createdAt DESC, studentID);
```

# Stage 4

Fetching notifications on every page load puts avoidable pressure on the database. I would combine multiple strategies:

- cache unread count and latest notifications in Redis
- use WebSockets for new notifications
- use cursor pagination instead of loading all notifications
- poll only as a fallback when WebSocket is unavailable
- add CDN/browser caching only for static metadata, not user-specific unread state

The best user experience is: load the first page from the API, receive new items through WebSocket, and refresh from the API only when reconnecting or opening the inbox.

Tradeoffs:

- Redis improves speed but adds cache invalidation work.
- WebSockets improve real-time UX but need connection management.
- Pagination reduces query cost but requires cursor handling in the frontend.
- Polling is simple but wasteful at scale.

# Stage 5

The proposed implementation is not reliable:

```text
for student_id in student_ids:
    send_email(student_id, message)
    save_to_db(student_id, message)
    push_to_app(student_id, message)
```

Problems:

- one failed email can stop the whole loop
- DB save and email send are mixed together
- no retry strategy
- no idempotency key
- no batching
- no delivery status tracking
- user-facing notification can be lost if push fails

I would save the notification first, then enqueue delivery jobs. Email and in-app delivery should not happen in the same transaction. The database is the source of truth; email and push are delivery channels.

Revised pseudocode:

```text
function notify_all(student_ids, message):
    notification_id = create_notification(message, type="Placement")

    for batch in chunks(student_ids, 1000):
        create_student_notification_rows(notification_id, batch)
        enqueue_job("send_email_batch", notification_id, batch)
        enqueue_job("push_in_app_batch", notification_id, batch)

    return notification_id

worker send_email_batch(notification_id, student_ids):
    for student_id in student_ids:
        try:
            send_email(student_id, notification_id)
            mark_email_status(student_id, notification_id, "sent")
        except TemporaryError:
            retry_with_backoff(student_id, notification_id)
        except PermanentError:
            mark_email_status(student_id, notification_id, "failed")

worker push_in_app_batch(notification_id, student_ids):
    for student_id in student_ids:
        push_to_socket_if_connected(student_id, notification_id)
```

If 200 emails fail midway, the job queue retries only those failed students. The notification still exists in the database, so students can see it in-app even if email delivery is delayed.

# Stage 6

For the priority inbox, I rank unread notifications by type weight first and recency second:

- Placement = 3
- Result = 2
- Event = 1

For a stream of incoming notifications, I maintain a min-heap of size `n`. For top 10, the heap never grows beyond 10 items, so each new notification costs `O(log 10)`, which is effectively constant for this use case. This approach is implemented in `notification_app_be/priority.py`.
