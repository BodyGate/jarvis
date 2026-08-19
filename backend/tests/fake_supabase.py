"""Doppio minimale del client supabase-py, sufficiente a coprire le catene
`.table().select/insert/update/delete().eq().order().limit().execute()`
usate da `app.chat_service` — evita di dover colpire un Supabase reale nei
test unitari.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, table_name, mode, payload=None):
        self._store = store
        self._table = table_name
        self._mode = mode  # 'select' | 'insert' | 'update' | 'delete'
        self._payload = payload
        self._filters = []
        self._order_by = None
        self._desc = False
        self._limit = None

    def eq(self, field, value):
        self._filters.append((field, value))
        return self

    def order(self, field, desc: bool = False):
        self._order_by = field
        self._desc = desc
        return self

    def limit(self, n):
        self._limit = n
        return self

    def select(self, *_args, **_kwargs):
        return self

    def _matching_rows(self):
        rows = self._store.setdefault(self._table, [])
        for field, value in self._filters:
            rows = [r for r in rows if r.get(field) == value]
        return rows

    def execute(self):
        rows = self._store.setdefault(self._table, [])

        if self._mode == "insert":
            now = datetime.now(timezone.utc).isoformat()
            new_row = {
                "id": str(uuid.uuid4()),
                "created_at": now,
                "updated_at": now,
                "user_id": "default",
                "intent": None,
                "target": None,
                "source": None,
                "action_type": None,
                "action_payload": None,
                "has_image": False,
                "image_url": None,
                **self._payload,
            }
            rows.append(new_row)
            return _Result([new_row])

        matching = self._matching_rows()

        if self._mode == "update":
            for row in matching:
                row.update(self._payload)
            return _Result(matching)

        if self._mode == "delete":
            remaining = [r for r in rows if r not in matching]
            self._store[self._table] = remaining
            return _Result(matching)

        # select
        if self._order_by:
            matching = sorted(
                matching, key=lambda r: r.get(self._order_by) or "", reverse=self._desc
            )
        if self._limit is not None:
            matching = matching[: self._limit]
        return _Result(matching)


class FakeTable:
    def __init__(self, store, name):
        self._store = store
        self._name = name

    def select(self, *_args, **_kwargs):
        return _Query(self._store, self._name, "select")

    def insert(self, payload):
        return _Query(self._store, self._name, "insert", payload)

    def update(self, payload):
        return _Query(self._store, self._name, "update", payload)

    def delete(self):
        return _Query(self._store, self._name, "delete")


class FakeSupabaseClient:
    def __init__(self):
        self._store: dict[str, list[dict]] = {}

    def table(self, name):
        return FakeTable(self._store, name)
