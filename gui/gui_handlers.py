import threading
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


# ══════════════════════════════════════════════
#  ОБРАБОТЧИКИ: ИСПРАВЛЕНИЕ ОТСУТСТВУЮЩИХ ЭЛЕМЕНТОВ
# ══════════════════════════════════════════════
def on_fix_missing():
    """Запускает процесс исправления отсутствующих элементов в XML."""
    if not _gui._check_schema():
        return
    if not _gui._check_files_loaded():
        return
    _gui._is_running = True
    _gui._set_buttons(False)
    _gui._status_var.set("Fixing...")

    def worker():
        try:
            all_results = []
            total = len(_gui._last_xml_paths)
            for i, xml_path in enumerate(_gui._last_xml_paths, 1):
                result, fixes = fix_and_save_xml(
                    xml_path, _gui._xsd_path, _gui._schema,
                )
                all_results.append(result)
                pct = (i / total) * 100
                _gui.root.after(0, _gui._progress_var.set, pct)
                _gui.root.after(
                    0, _gui._status_var.set, f"Fixing {i}/{total}...",
                )
            _gui.root.after(0, __on_fix_done, all_results)
        except Exception as e:
            _gui.root.after(
                0, messagebox.showerror, "Fix Error", str(e),
            )
            _gui.root.after(0, _gui._set_buttons, True)
            _gui._is_running = False

    threading.Thread(target=worker, daemon=True).start()

def __on_fix_done(results):
    """Обрабатывает завершение процесса исправления — обновляет UI."""
    _gui._is_running = False
    _gui._set_buttons(True)
    for r in results:
        idx = len(_gui._results)
        _gui._results.append(r)
        fixes_count = len(r.fixes_applied)
        if r.is_valid:
            tag = "fixed"
            status = f"Fixed OK ({fixes_count} fixes)"
        else:
            tag = "invalid"
            status = f"Fixed, {r.error_count} errors remain"
        _gui._tree.insert(
            "", tk.END, iid=str(idx),
            values=(
                r.file_path.name, status,
                r.root_element or "-", "", r.error_count,
            ),
            tags=(tag,),
        )
    total_fixes = sum(len(r.fixes_applied) for r in results)
    _gui._status_var.set(
        f"Fix done! {len(results)} file(s), "
        f"{total_fixes} total fixes applied.",
    )


# ══════════════════════════════════════════════
#  ОБРАБОТЧИКИ: ЗАМЕНА LPU_1
# ══════════════════════════════════════════════

def on_replace_lpu1():
    """Запускает замену всех элементов LPU_1 на указанное значение."""
    new_value = _gui._lpu1_var.get().strip()
    if not new_value:
        messagebox.showwarning("Empty", "Enter a value for LPU_1.")
        return
    if not _gui._check_files_loaded():
        return
    file_list = _gui._format_file_list(_gui._last_xml_paths)
    if not messagebox.askyesno(
        "Confirm LPU_1",
        f"Replace ALL <LPU_1> with:\n{new_value}\n"
        f"In files:\n{file_list}\nOverwrite?",
    ):
        return
    _gui._run_replace_thread(
        label="LPU_1",
        worker_func=_worker_replace_lpu1,
        new_value=new_value,
    )


def _worker_replace_lpu1(new_value):
    """Функция-воркер для замены LPU_1 в фоне."""
    total_count = 0
    total_files = 0
    for xml_path in _gui._last_xml_paths:
        count, _ = replace_element_value(xml_path, "LPU_1", new_value)
        total_count += count
        if count > 0:
            total_files += 1
    return total_count, total_files
