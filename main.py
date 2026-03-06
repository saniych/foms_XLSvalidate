"""Точка входа. Запуск: py main.py"""

import sys


def main():
    try:
        from lxml import etree  # noqa: F401
    except ImportError:
        print("ОШИБКА: pip install lxml")
        input("Enter для выхода...")
        sys.exit(1)

    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("ОШИБКА: tkinter не найден")
        input("Enter для выхода...")
        sys.exit(1)

    from gui.gui import ValidatorApp
    app = ValidatorApp()
    app.run()


if __name__ == "__main__":
    main()

