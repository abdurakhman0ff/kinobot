"""Zaxira bazani tiklash: /restoredb fayli <DB_PATH>.restore ga yoziladi, keyingi ishga tushishda almashtiriladi."""
from __future__ import annotations

import os


def apply_pending_restore(path: str) -> bool:
    pending = path + ".restore"
    if not os.path.exists(pending):
        return False
    for suffix in ("-wal", "-shm"):
        try:
            os.remove(path + suffix)
        except FileNotFoundError:
            pass
    if os.path.exists(path):
        os.replace(path, path + ".old")
    os.replace(pending, path)
    return True
