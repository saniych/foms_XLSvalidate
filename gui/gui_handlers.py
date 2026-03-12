import tkinter as tk
from tkinter import messagebox, filedialog
from pathlib import Path
from core.core import (
    load_xsd_schema,
    get_schema_root_elements,
    validate_batch,
    collect_xml_files,
    fix_and_save_xml,
    replace_element_value,
    upsert_element_value,
    replace_lpu1_for_specific_usl,
)

# Глобальная ссылка на GUI
_gui = None

def set_gui(gui_instance):
    """Устанавливает ссылку на экземпляр GUI"""
    global _gui
    _gui = gui_instance

def on_select_xsd():
    """Обрабатывает выбор XSD-файла через диалог."""
    if _gui:
        path = filedialog.askopenfilename(
            title="Select XSD schema",
            filetypes=[("XSD", "*.xsd"), ("All", "*.*")],
        )
        if not path:
            return
        xsd_path = Path(path)
        try:
            _gui._schema = load_xsd_schema(xsd_path)
            _gui._xsd_path = xsd_path
            _gui._xsd_var.set(xsd_path.name)
            elements = get_schema_root_elements(xsd_path)
            _gui._schema_elements = elements
            _gui._schema_info_var.set(
                f"Elements: {', '.join(elements) if elements else '(none)'}"
            )
            _gui._child_tag_combo["values"] = elements
            if elements:
                _gui._child_tag_var.set(elements[0])
            _gui._status_var.set(f"Schema loaded: {xsd_path.name}")
        except Exception as e:
            messagebox.showerror("XSD Error", str(e))
            _gui._schema = None


def on_validate_files():
    """Запускает валидацию выбранных пользователем XML-файлов."""
    if not _gui._check_schema():
        return
    paths = filedialog.askopenfilenames(
        title="Select XML files",
        filetypes=[("XML", "*.xml"), ("All", "*.*")],
    )
    if paths:
        xml_paths = [Path(p) for p in paths]
        _gui._last_xml_paths = xml_paths
        _gui._run_validation(xml_paths)


def on_validate_dir():
    """Запускает валидацию всех XML-файлов в выбранной папке."""
    if not _gui._check_schema():
        return
    d = filedialog.askdirectory(title="Select folder with XML")
    if not d:
        return
    try:
        files = collect_xml_files(Path(d))
    except Exception as e:
        messagebox.showerror("Error", str(e))
        return
    if not files:
        messagebox.showinfo("Empty", "No XML files found.")
        return
    _gui._last_xml_paths = files
    _gui._run_validation(files)


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


