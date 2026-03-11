import tkinter as tk
from tkinter import messagebox, filedialog

# Глобальная ссылка на GUI
_gui = None

def set_gui(gui_instance):
    """Устанавливает ссылку на экземпляр GUI"""
    global _gui
    _gui = gui_instance



def on_clear():
    """Очищает таблицу результатов и панель деталей."""
    if _gui:
        _gui._tree.delete(*_gui._tree.get_children())
        _gui._results.clear()
        _gui._detail.configure(state=tk.NORMAL)
        _gui._detail.delete("1.0", tk.END)
        _gui._detail.configure(state=tk.DISABLED)
        _gui._progress_var.set(0)
        _gui._status_var.set("Cleared")
