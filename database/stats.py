"""Admin statistikasi uchun so'rovlar."""
from __future__ import annotations

from typing import Any

from database.db import db
from utils.time import ago_db, local_day_start_db, now_db


async def summary() -> dict[str, Any]:
    now = now_db()
    params = {
        "now": now,
        "d7": ago_db(days=7),
        "d30": ago_db(days=30),
        "today": local_day_start_db(),
    }
    row = await db.fetchone(
        """SELECT
             (SELECT COUNT(*) FROM users) AS users,
             (SELECT COUNT(*) FROM users WHERE last_active >= :d7) AS active7,
             (SELECT COUNT(*) FROM users WHERE last_active >= :d30) AS active30,
             (SELECT COUNT(*) FROM users WHERE joined_at >= :today) AS new_today,
             (SELECT COUNT(*) FROM users WHERE joined_at >= :d7) AS new7,
             (SELECT COUNT(*) FROM users WHERE is_blocked_bot = 1) AS blocked,
             (SELECT COUNT(*) FROM users WHERE vip_until > :now) AS vip,
             (SELECT COUNT(*) FROM movies WHERE type != 'serial') AS films,
             (SELECT COUNT(*) FROM movies WHERE type = 'serial') AS serials,
             (SELECT COUNT(*) FROM episodes) AS episodes,
             (SELECT COUNT(*) FROM requests WHERE status = 'new') AS requests,
             (SELECT COUNT(*) FROM reports WHERE status = 'new') AS reports""",
        params,
    )
    data = dict(row or {})
    # limitga yetganlar (30 kun) va ulardan 7 kun ichida VIP olganlar
    conv = await db.fetchone(
        """WITH hits AS (
             SELECT user_id, MIN(created_at) AS first_hit FROM events
             WHERE kind = 'limit_hit' AND created_at >= :d30 GROUP BY user_id)
           SELECT COUNT(*) AS hit_users,
                  SUM(CASE WHEN EXISTS (
                      SELECT 1 FROM events p WHERE p.kind = 'vip_purchase' AND p.user_id = hits.user_id
                        AND p.created_at >= hits.first_hit
                        AND p.created_at <= datetime(hits.first_hit, '+7 days')) THEN 1 ELSE 0 END) AS converted
           FROM hits""",
        params,
    )
    data["limit_users"] = (conv or {}).get("hit_users") or 0
    data["limit_converted"] = (conv or {}).get("converted") or 0
    return data


async def revenue_by_month(months: int = 6) -> list[dict[str, Any]]:
    return await db.fetchall(
        """SELECT strftime('%Y-%m', created_at, '+5 hours') AS month, currency, SUM(amount) AS total,
                  COUNT(*) AS cnt
           FROM payments WHERE status = 'paid' AND created_at >= ?
           GROUP BY month, currency ORDER BY month DESC, currency""",
        (ago_db(days=31 * months),),
    )
