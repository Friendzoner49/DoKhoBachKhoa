"""PyInstaller entry point. Kept separate from shop/ui/app.py so the
spec has one obvious, stable thing to point Analysis() at."""
from shop.ui.app import main

if __name__ == "__main__":
    main()
