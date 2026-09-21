import os
import pytest

# Встановлюємо фіктивні змінні середовища ДО того, як pytest імпортує модулі.
# Це дозволяє уникнути RuntimeError під час "збору" тестів (collection phase),
# оскільки app.db.base шукає DATABASE_URL на рівні модуля (при імпорті).
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
