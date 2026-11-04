import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # no display needed to run the UI smoke test

import pytest

from shop.db.migrate import connect


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
