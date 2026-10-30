import os

# GUI tests run without a display (CI, pre-commit); set before pytest-qt creates the QApplication
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
