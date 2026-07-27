import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_store


class _FakeCursor:
    def __init__(self, store, log):
        self.store = store
        self.log = log
        self._last = None

    def execute(self, sql, params=None):
        self.log.append((sql.strip().split()[0], params))
        s = sql.strip().upper()
        if s.startswith("SELECT QUOTE_ID FROM FAVORITES"):
            username = params[0]
            self._last = [{"quote_id": qid} for (u, qid) in self.store if u == username]
        elif s.startswith("SELECT 1 FROM FAVORITES"):
            username, quote_id = params
            self._last = [{"?": 1}] if (username, quote_id) in self.store else []
        elif s.startswith("INSERT INTO FAVORITES"):
            self.store.add(tuple(params))
            self._last = None
        elif s.startswith("DELETE FROM FAVORITES"):
            self.store.discard(tuple(params))
            self._last = None
        else:
            self._last = []

    def fetchone(self):
        rows = self._last or []
        return rows[0] if rows else None

    def fetchall(self):
        return self._last or []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeGetCursor:
    def __init__(self, store):
        self.store = store
        self.log = []

    def __call__(self, commit=False):
        return _FakeCursor(self.store, self.log)


def test_add_and_list_favorite(monkeypatch):
    store = set()
    monkeypatch.setattr(data_store.db, "get_cursor", _FakeGetCursor(store))

    data_store.add_favorite("lpavanel", "q1")

    assert data_store.list_favorites("lpavanel") == ["q1"]
    assert data_store.is_favorite("lpavanel", "q1") is True
    assert data_store.is_favorite("lpavanel", "q2") is False


def test_remove_favorite(monkeypatch):
    store = {("lpavanel", "q1")}
    monkeypatch.setattr(data_store.db, "get_cursor", _FakeGetCursor(store))

    data_store.remove_favorite("lpavanel", "q1")

    assert data_store.list_favorites("lpavanel") == []


def test_toggle_favorite_adiciona_quando_nao_existe(monkeypatch):
    store = set()
    monkeypatch.setattr(data_store.db, "get_cursor", _FakeGetCursor(store))

    result = data_store.toggle_favorite("lpavanel", "q1")

    assert result is True
    assert ("lpavanel", "q1") in store


def test_toggle_favorite_remove_quando_ja_existe(monkeypatch):
    store = {("lpavanel", "q1")}
    monkeypatch.setattr(data_store.db, "get_cursor", _FakeGetCursor(store))

    result = data_store.toggle_favorite("lpavanel", "q1")

    assert result is False
    assert ("lpavanel", "q1") not in store


def test_favorites_sao_isolados_por_usuario(monkeypatch):
    store = {("lpavanel", "q1"), ("outro_user", "q2")}
    monkeypatch.setattr(data_store.db, "get_cursor", _FakeGetCursor(store))

    assert data_store.list_favorites("lpavanel") == ["q1"]
    assert data_store.list_favorites("outro_user") == ["q2"]
