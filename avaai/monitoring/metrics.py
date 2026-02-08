from typing import List, Dict

from .db import fetch_all


def get_recent_requests(db_path: str, limit: int = 20) -> List[Dict]:
    return fetch_all(
        db_path,
        """
        SELECT ts, model, latency_ms, total_tokens, cost_usd, status, error
        FROM requests
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,)
    )


def get_error_counts(db_path: str) -> List[Dict]:
    return fetch_all(
        db_path,
        """
        SELECT status, COUNT(*) as count
        FROM requests
        GROUP BY status
        ORDER BY count DESC
        """
    )


def get_top_models(db_path: str, limit: int = 5) -> List[Dict]:
    return fetch_all(
        db_path,
        """
        SELECT model, COUNT(*) as count
        FROM requests
        GROUP BY model
        ORDER BY count DESC
        LIMIT ?
        """,
        (limit,)
    )


def get_admin_audit(db_path: str, limit: int = 50) -> List[Dict]:
    return fetch_all(
        db_path,
        """
        SELECT ts, actor, action, details
        FROM admin_audit
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,)
    )


def get_usage_summary(db_path: str) -> List[Dict]:
    return fetch_all(
        db_path,
        """
        SELECT
            COUNT(*) as request_count,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(cost_usd), 0) as total_cost,
            COALESCE(AVG(latency_ms), 0) as avg_latency
        FROM requests
        """
    )


def get_daily_costs(db_path: str, limit: int = 14) -> List[Dict]:
    return fetch_all(
        db_path,
        """
        SELECT SUBSTR(ts, 1, 10) as day, COALESCE(SUM(cost_usd), 0) as total_cost
        FROM requests
        GROUP BY day
        ORDER BY day DESC
        LIMIT ?
        """,
        (limit,)
    )
