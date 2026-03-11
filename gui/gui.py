"""Графический интерфейс с валидацией, исправлением, заменой LPU_1, PLAT, MOP."""
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
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
from .NprNum_dialog import NPRNumDialog
from .gui_handlers import (
set_gui,
on_clear as on_clear_handler,
)


class ValidatorApp:
    """Основное приложение для валидации и исправления XML."""
    VERSION = "2.3.0"

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"XML Validator v{self.VERSION}")
        self.root.geometry("1100x950")
        self.root.minsize(900, 750)
        self.root.configure(bg="#f5f5f5")
        self._schema = None
        self._xsd_path = None
        self._results = []
        self._is_running = False
        self._schema_elements = []
        self._last_xml_paths = []
        self._build_header()
        self._build_controls()
        self._build_tools()
        self._build_results()

        set_gui(self)

    # ══════════════════════════════════════════════
    #  ЗАГОЛОВОК
    # ══════════════════════════════════════════════
    def _build_header(self):
        """Создаёт верхнюю панель с заголовком и версией."""
        hdr = tk.Frame(self.root, bg="#2c3e50", height=50)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(
            hdr, text="XML Validator + Fixer (разработчик не уверен в том что у вас всё получится, но вдруг :))",
            font=("Segoe UI", 14, "bold"), bg="#2c3e50", fg="#ecf0f1",
        ).pack(side=tk.LEFT, padx=15, pady=10)
        tk.Label(
            hdr, text=f"v{self.VERSION}",
            font=("Segoe UI", 10), bg="#2c3e50", fg="#95a5a6",
        ).pack(side=tk.RIGHT, padx=15)

    # ══════════════════════════════════════════════
    #  ПАНЕЛЬ УПРАВЛЕНИЯ
    # ══════════════════════════════════════════════
    def _build_controls(self):
        """Создаёт панель управления: выбор XSD, опции валидации, кнопки."""
        frame = tk.LabelFrame(
            self.root, text="  Schema & Validation  ",
            font=("Segoe UI", 10, "bold"), bg="#f5f5f5", padx=10, pady=8,
        )
        frame.pack(fill=tk.X, padx=10, pady=(10, 3))
        # Строка выбора XSD
        xsd_row = tk.Frame(frame, bg="#f5f5f5")
        xsd_row.pack(fill=tk.X, pady=(0, 5))
        tk.Label(
            xsd_row, text="XSD:", font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5", width=6, anchor="w",
        ).pack(side=tk.LEFT)
        self._xsd_var = tk.StringVar(value="Not selected")
        tk.Label(
            xsd_row, textvariable=self._xsd_var,
            font=("Segoe UI", 10), bg="#f5f5f5", fg="#3498db", anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 10))
        self._btn_xsd = tk.Button(
            xsd_row, text="Select XSD", font=("Segoe UI", 10),
            command=self._on_select_xsd, padx=10,
        )
        self._btn_xsd.pack(side=tk.RIGHT)
        # Информация о схеме
        self._schema_info_var = tk.StringVar(value="")
        tk.Label(
            frame, textvariable=self._schema_info_var,
            font=("Segoe UI", 9), bg="#f5f5f5", fg="#7f8c8d", anchor="w",
        ).pack(fill=tk.X, pady=(0, 3))

        # dopinfo
        dopinfo_row = tk.Frame(frame, bg="#f5f5f5")
        dopinfo_row.pack(fill=tk.X, pady=(0, 5))
        tk.Label(
            dopinfo_row, text="LPU:", font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5", width=6, anchor="w",
        ).pack(side=tk.LEFT)
        self._lpu_kod = tk.StringVar(value="some kod")

        # Опции
        opt_row = tk.Frame(frame, bg="#f5f5f5")
        opt_row.pack(fill=tk.X, pady=(0, 5))
        self._validate_children_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opt_row,
            text="Validate children if root not in schema",
            variable=self._validate_children_var,
            font=("Segoe UI", 9), bg="#f5f5f5",
        ).pack(side=tk.LEFT)
        tk.Label(
            opt_row, text="  Tag:", font=("Segoe UI", 9), bg="#f5f5f5",
        ).pack(side=tk.LEFT, padx=(15, 3))
        self._child_tag_var = tk.StringVar(value="ZAP")
        self._child_tag_combo = ttk.Combobox(
            opt_row, textvariable=self._child_tag_var,
            width=15, font=("Segoe UI", 9),
        )
        self._child_tag_combo.pack(side=tk.LEFT)
        # Кнопки
        btn_row = tk.Frame(frame, bg="#f5f5f5")
        btn_row.pack(fill=tk.X, pady=(3, 5))
        self._btn_files = tk.Button(
            btn_row, text="Validate File(s)", font=("Segoe UI", 10, "bold"),
            command=self._on_validate_files,
            bg="#3498db", fg="white", padx=15, pady=4,
        )
        self._btn_files.pack(side=tk.LEFT, padx=(0, 5))
        self._btn_dir = tk.Button(
            btn_row, text="Validate Folder", font=("Segoe UI", 10, "bold"),
            command=self._on_validate_dir,
            bg="#16a085", fg="white", padx=15, pady=4,
        )
        self._btn_dir.pack(side=tk.LEFT, padx=(0, 5))
        self._btn_clear = tk.Button(
            btn_row, text="Clear", font=("Segoe UI", 10),
            command=on_clear_handler(), padx=10,
        )
        self._btn_clear.pack(side=tk.RIGHT)
        # Прогресс
        self._progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(
            frame, variable=self._progress_var, maximum=100,
        ).pack(fill=tk.X, pady=(0, 3))
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(
            frame, textvariable=self._status_var,
            font=("Segoe UI", 10), bg="#f5f5f5", anchor="w",
        ).pack(fill=tk.X)

    # ══════════════════════════════════════════════
    #  ИНСТРУМЕНТЫ
    # ══════════════════════════════════════════════
    def _build_tools(self):
        """Создаёт панель инструментов для замены элементов и исправлений."""
        frame = tk.LabelFrame(
            self.root, text="  Tools  ",
            font=("Segoe UI", 10, "bold"), bg="#f5f5f5", padx=10, pady=8,
        )
        frame.pack(fill=tk.X, padx=10, pady=(3, 3))
        # Строка 1: Исправление отсутствующих элементов
        fix_row = tk.Frame(frame, bg="#f5f5f5")
        fix_row.pack(fill=tk.X, pady=(0, 8))
        self._btn_fix = tk.Button(
            fix_row,
            text="Fix Missing Elements",
            font=("Segoe UI", 10, "bold"),
            command=self._on_fix_missing,
            bg="#e67e22", fg="white", padx=15, pady=4,
        )
        self._btn_fix.pack(side=tk.LEFT, padx=(0, 10))
        tk.Label(
            fix_row,
            text="Adds missing required elements, reorders by XSD. "
            "Saves as *_fixed.xml",
            font=("Segoe UI", 8, "italic"), bg="#f5f5f5", fg="#95a5a6",
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._btn_npr_num = tk.Button(
            fix_row,
            text="Validate NPR_NUM",
            font=("Segoe UI", 10, "bold"),
            command=self._on_validate_npr_num,
            bg="#1abc9c", fg="white", padx=15, pady=4,
        )
        self._btn_npr_num.pack(side=tk.LEFT, padx=(5, 0))
        # Строка 2: LPU_1
        self._build_tool_row(
            frame,
            label="LPU_1:",
            var_attr="_lpu1_var",
            entry_attr="_lpu1_entry",
            btn_attr="_btn_replace_lpu1",
            btn_text="Replace",
            btn_color="#8e44ad",
            command=self._on_replace_lpu1,
            hint="Replaces ALL <LPU_1> (in SL, USL, etc). Overwrites files.",
        )
        # Строка 3: PLAT
        self._build_tool_row(
            frame,
            label="PLAT:",
            var_attr="_plat_var",
            entry_attr="_plat_entry",
            btn_attr="_btn_replace_plat",
            btn_text="Replace",
            btn_color="#2980b9",
            command=self._on_replace_plat,
            hint="Replaces or CREATES <PLAT> in <SCHET>. Overwrites files.",
        )
        # Строка 4: MOP
        self._build_tool_row(
            frame,
            label="MOP:",
            var_attr="_mop_var",
            entry_attr="_mop_entry",
            btn_attr="_btn_replace_mop",
            btn_text="Replace",
            btn_color="#16a085",
            command=self._on_replace_mop,
            hint="Replaces or CREATES <MOP> in every <SL>. Overwrites files.",
        )
        # Строка 5: MO_PR
        self._build_tool_row(
            frame,
            label="MO_PR:",
            var_attr="_mo_pr_var",
            entry_attr="_mo_pr_entry",
            btn_attr="_btn_replace_mo_pr",
            btn_text="Replace",
            btn_color="#c0392b",
            command=self._on_replace_mo_pr,
            hint="Replaces or CREATES <MO_PR> in every <PACIENT>. Overwrites files.",
        )
        # Строка 6: VZ
        self._build_tool_row(
            frame,
            label="VZ:",
            var_attr="_vz_var",
            entry_attr="_vz_entry",
            btn_attr="_btn_replace_vz",
            btn_text="Replace",
            btn_color="#d35400",
            command=self._on_replace_vz,
            hint="Replaces or CREATES <VZ> in every <PACIENT>. Overwrites files.",
        )
        # Строка 7: KOEF_PR
        self._build_tool_row(
            frame,
            label="KOEF_PR:",
            var_attr="_koef_pr_var",
            entry_attr="_koef_pr_entry",
            btn_attr="_btn_replace_koef_pr",
            btn_text="Replace",
            btn_color="#34495e",  # Темно-синий/серый
            command=self._on_replace_koef_pr,
            hint="Replaces or CREATES <KOEF_PR> inside <KSG_KPG>.",
        )
        # Строка 8: LPU_1 (Specific USL)
        self._build_tool_row(
            frame,
            label="LPU_1 (Spec):",
            var_attr="_lpu1_spec_var",
            entry_attr="_lpu1_spec_entry",
            btn_attr="_btn_replace_lpu1_spec",
            btn_text="Replace",
            btn_color="#9b59b6",  # Светло-фиолетовый
            command=self._on_replace_lpu1_spec,
            hint="Replaces <LPU_1> in <USL> ONLY for codes: A05.10.006, A05.10.004, A04.28.001.",
        )

    def _build_tool_row(
        self, parent, label, var_attr, entry_attr, btn_attr,
        btn_text, btn_color, command, hint,
    ):
        """Создаёт строку инструмента: метка, поле ввода, кнопка, подсказка."""
        row = tk.Frame(parent, bg="#f5f5f5")
        row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            row, text=label,
            font=("Segoe UI", 10, "bold"), bg="#f5f5f5", width=7, anchor="w",
        ).pack(side=tk.LEFT)
        var = tk.StringVar(value="")
        setattr(self, var_attr, var)
        entry = tk.Entry(
            row, textvariable=var,
            font=("Segoe UI", 10), width=20,
        )
        entry.pack(side=tk.LEFT, padx=(5, 5))
        setattr(self, entry_attr, entry)
        btn = tk.Button(
            row, text=btn_text,
            font=("Segoe UI", 10, "bold"),
            command=command,
            bg=btn_color, fg="white", padx=15, pady=4,
        )
        btn.pack(side=tk.LEFT, padx=(0, 10))
        setattr(self, btn_attr, btn)
        tk.Label(
            row, text=hint,
            font=("Segoe UI", 8, "italic"), bg="#f5f5f5", fg="#95a5a6",
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    # ══════════════════════════════════════════════
    #  РЕЗУЛЬТАТЫ
    # ══════════════════════════════════════════════
    def _build_results(self):
        """Создаёт область отображения результатов валидации."""
        paned = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=(3, 10))
        # Таблица
        table_frame = tk.LabelFrame(
            paned, text="  Results  ",
            font=("Segoe UI", 10, "bold"), bg="#f5f5f5",
        )
        paned.add(table_frame, weight=3)
        cols = ("file", "status", "root", "checked", "errors")
        self._tree = ttk.Treeview(
            table_frame, columns=cols, show="headings", selectmode="browse",
        )
        self._tree.heading("file", text="File", anchor="w")
        self._tree.heading("status", text="Status", anchor="center")
        self._tree.heading("root", text="Root", anchor="center")
        self._tree.heading("checked", text="Checked", anchor="center")
        self._tree.heading("errors", text="Errors", anchor="center")
        self._tree.column("file", width=320, minwidth=200)
        self._tree.column("status", width=180, minwidth=120, anchor="center")
        self._tree.column("root", width=100, minwidth=80, anchor="center")
        self._tree.column("checked", width=100, minwidth=80, anchor="center")
        self._tree.column("errors", width=80, minwidth=60, anchor="center")
        self._tree.tag_configure("valid", background="#eafaf1")
        self._tree.tag_configure("invalid", background="#fdedec")
        self._tree.tag_configure("malformed", background="#f4ecf7")
        self._tree.tag_configure("partial", background="#fef9e7")
        self._tree.tag_configure("fixed", background="#ebf5fb")
        sb = ttk.Scrollbar(
            table_frame, orient=tk.VERTICAL, command=self._tree.yview,
        )
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.bind("<<TreeviewSelect>>", self._on_row_select)
        # Детали
        detail_frame = tk.LabelFrame(
            paned, text="  Details (click a row)  ",
            font=("Segoe UI", 10, "bold"), bg="#f5f5f5",
        )
        paned.add(detail_frame, weight=2)
        self._detail = scrolledtext.ScrolledText(
            detail_frame, font=("Consolas", 10), wrap=tk.WORD,
            bg="white", state=tk.DISABLED,
        )
        self._detail.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self._detail.tag_configure("error", foreground="#e74c3c")
        self._detail.tag_configure("warning", foreground="#e67e22")
        self._detail.tag_configure("fatal", foreground="#8e44ad")
        self._detail.tag_configure("info", foreground="#3498db")
        self._detail.tag_configure("ok", foreground="#27ae60")
        self._detail.tag_configure("fix", foreground="#e67e22",
                                   font=("Consolas", 10, "bold"))
        self._detail.tag_configure("header", foreground="#2c3e50",
                                   font=("Consolas", 10, "bold"))

    # ══════════════════════════════════════════════
    #  ОБРАБОТЧИКИ: СХЕМА
    # ══════════════════════════════════════════════
    def _on_select_xsd(self):
        """Обрабатывает выбор XSD-файла через диалог."""
        path = filedialog.askopenfilename(
            title="Select XSD schema",
            filetypes=[("XSD", "*.xsd"), ("All", "*.*")],
        )
        if not path:
            return
        xsd_path = Path(path)
        try:
            self._schema = load_xsd_schema(xsd_path)
            self._xsd_path = xsd_path
            self._xsd_var.set(xsd_path.name)
            elements = get_schema_root_elements(xsd_path)
            self._schema_elements = elements
            self._schema_info_var.set(
                f"Elements: {', '.join(elements) if elements else '(none)'}"
            )
            self._child_tag_combo["values"] = elements
            if elements:
                self._child_tag_var.set(elements[0])
            self._status_var.set(f"Schema loaded: {xsd_path.name}")
        except Exception as e:
            messagebox.showerror("XSD Error", str(e))
            self._schema = None

    # ══════════════════════════════════════════════
    #  ОБРАБОТЧИКИ: ВАЛИДАЦИЯ
    # ══════════════════════════════════════════════
    def _on_validate_files(self):
        """Запускает валидацию выбранных пользователем XML-файлов."""
        if not self._check_schema():
            return
        paths = filedialog.askopenfilenames(
            title="Select XML files",
            filetypes=[("XML", "*.xml"), ("All", "*.*")],
        )
        if paths:
            xml_paths = [Path(p) for p in paths]
            self._last_xml_paths = xml_paths
            self._run_validation(xml_paths)

    def _on_validate_dir(self):
        """Запускает валидацию всех XML-файлов в выбранной папке."""
        if not self._check_schema():
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
        self._last_xml_paths = files
        self._run_validation(files)

    def _on_clear(self):
        """Очищает таблицу результатов и панель деталей."""
        self._tree.delete(*self._tree.get_children())
        self._results.clear()
        self._detail.configure(state=tk.NORMAL)
        self._detail.delete("1.0", tk.END)
        self._detail.configure(state=tk.DISABLED)
        self._progress_var.set(0)
        self._status_var.set("Cleared")

    def _on_row_select(self, _event):
        """Обрабатывает выбор строки в таблице — показывает детали."""
        sel = self._tree.selection()
        if not sel:
            return
        try:
            idx = int(sel[0])
        except (ValueError, TypeError):
            return
        if 0 <= idx < len(self._results):
            self._show_details(self._results[idx])

    # ══════════════════════════════════════════════
    #  ОБРАБОТЧИКИ: ИСПРАВЛЕНИЕ ОТСУТСТВУЮЩИХ ЭЛЕМЕНТОВ
    # ══════════════════════════════════════════════
    def _on_fix_missing(self):
        """Запускает процесс исправления отсутствующих элементов в XML."""
        if not self._check_schema():
            return
        if not self._check_files_loaded():
            return
        self._is_running = True
        self._set_buttons(False)
        self._status_var.set("Fixing...")

        def worker():
            try:
                all_results = []
                total = len(self._last_xml_paths)
                for i, xml_path in enumerate(self._last_xml_paths, 1):
                    result, fixes = fix_and_save_xml(
                        xml_path, self._xsd_path, self._schema,
                    )
                    all_results.append(result)
                    pct = (i / total) * 100
                    self.root.after(0, self._progress_var.set, pct)
                    self.root.after(
                        0, self._status_var.set, f"Fixing {i}/{total}...",
                    )
                self.root.after(0, self._on_fix_done, all_results)
            except Exception as e:
                self.root.after(
                    0, messagebox.showerror, "Fix Error", str(e),
                )
                self.root.after(0, self._set_buttons, True)
                self._is_running = False

        threading.Thread(target=worker, daemon=True).start()

    def _on_fix_done(self, results):
        """Обрабатывает завершение процесса исправления — обновляет UI."""
        self._is_running = False
        self._set_buttons(True)
        for r in results:
            idx = len(self._results)
            self._results.append(r)
            fixes_count = len(r.fixes_applied)
            if r.is_valid:
                tag = "fixed"
                status = f"Fixed OK ({fixes_count} fixes)"
            else:
                tag = "invalid"
                status = f"Fixed, {r.error_count} errors remain"
            self._tree.insert(
                "", tk.END, iid=str(idx),
                values=(
                    r.file_path.name, status,
                    r.root_element or "-", "", r.error_count,
                ),
                tags=(tag,),
            )
        total_fixes = sum(len(r.fixes_applied) for r in results)
        self._status_var.set(
            f"Fix done! {len(results)} file(s), "
            f"{total_fixes} total fixes applied.",
        )

    # ══════════════════════════════════════════════
    #  ОБРАБОТЧИКИ: ЗАМЕНА LPU_1
    # ══════════════════════════════════════════════
    def _on_replace_lpu1(self):
        """Запускает замену всех элементов LPU_1 на указанное значение."""
        new_value = self._lpu1_var.get().strip()
        if not new_value:
            messagebox.showwarning("Empty", "Enter a value for LPU_1.")
            return
        if not self._check_files_loaded():
            return
        file_list = self._format_file_list(self._last_xml_paths)
        if not messagebox.askyesno(
            "Confirm LPU_1",
            f"Replace ALL <LPU_1> with:\n{new_value}\n"
            f"In files:\n{file_list}\nOverwrite?",
        ):
            return
        self._run_replace_thread(
            label="LPU_1",
            worker_func=self._worker_replace_lpu1,
            new_value=new_value,
        )

    def _worker_replace_lpu1(self, new_value):
        """Функция-воркер для замены LPU_1 в фоне."""
        total_count = 0
        total_files = 0
        for xml_path in self._last_xml_paths:
            count, _ = replace_element_value(xml_path, "LPU_1", new_value)
            total_count += count
            if count > 0:
                total_files += 1
        return total_count, total_files

    # ══════════════════════════════════════════════
    #  ОБРАБОТЧИКИ: ЗАМЕНА / ВСТАВКА PLAT
    # ══════════════════════════════════════════════
    def _on_replace_plat(self):
        """Запускает замену или вставку элементов PLAT в SCHET."""
        new_value = self._plat_var.get().strip()
        if not new_value:
            messagebox.showwarning("Empty", "Enter a value for PLAT.")
            return
        if not self._check_files_loaded():
            return
        if not self._check_xsd_for_upsert("PLAT"):
            return
        file_list = self._format_file_list(self._last_xml_paths)
        if not messagebox.askyesno(
            "Confirm PLAT",
            f"Replace or INSERT <PLAT> in <SCHET> with:\n{new_value}\n"
            f"In files:\n{file_list}\n"
            f"Missing <PLAT> will be created.\nOverwrite?",
        ):
            return
        self._run_replace_thread(
            label="PLAT",
            worker_func=self._worker_replace_plat,
            new_value=new_value,
        )

    def _worker_replace_plat(self, new_value):
        """Функция-воркер для замены/вставки PLAT в фоне."""
        total_count = 0
        total_files = 0
        for xml_path in self._last_xml_paths:
            replaced, created, _ = upsert_element_value(
                xml_path, "SCHET", "PLAT", new_value,
                xsd_path=self._xsd_path,
            )
            total_count += replaced + created
            if replaced > 0 or created > 0:
                total_files += 1
        return total_count, total_files

    # ══════════════════════════════════════════════
    #  ОБРАБОТЧИКИ: ЗАМЕНА / ВСТАВКА MOP
    # ══════════════════════════════════════════════
    def _on_replace_mop(self):
        """Запускает замену или вставку элементов MOP в SL."""
        new_value = self._mop_var.get().strip()
        if not new_value:
            messagebox.showwarning("Empty", "Enter a value for MOP.")
            return
        if not self._check_files_loaded():
            return
        if not self._check_xsd_for_upsert("MOP"):
            return
        file_list = self._format_file_list(self._last_xml_paths)
        if not messagebox.askyesno(
            "Confirm MOP",
            f"Replace or INSERT <MOP> in every <SL> with:\n{new_value}\n"
            f"In files:\n{file_list}\n"
            f"Missing <MOP> will be created.\nOverwrite?",
        ):
            return
        self._run_replace_thread(
            label="MOP",
            worker_func=self._worker_replace_mop,
            new_value=new_value,
        )

    def _worker_replace_mop(self, new_value):
        """Функция-воркер для замены/вставки MOP в фоне."""
        total_count = 0
        total_files = 0
        for xml_path in self._last_xml_paths:
            replaced, created, _ = upsert_element_value(
                xml_path, "SL", "MOP", new_value,
                xsd_path=self._xsd_path,
            )
            total_count += replaced + created
            if replaced > 0 or created > 0:
                total_files += 1
        return total_count, total_files

    # ══════════════════════════════════════════════
    #  ОБРАБОТЧИКИ: ЗАМЕНА / ВСТАВКА MO_PR
    # ══════════════════════════════════════════════
    def _on_replace_mo_pr(self):
        """Запускает замену или вставку элементов MO_PR в PACIENT."""
        new_value = self._mo_pr_var.get().strip()
        if not new_value:
            messagebox.showwarning("Empty", "Enter a value for MO_PR.")
            return
        if not self._check_files_loaded():
            return
        if not self._check_xsd_for_upsert("MO_PR"):
            return
        file_list = self._format_file_list(self._last_xml_paths)
        if not messagebox.askyesno(
            "Confirm MO_PR",
            f"Replace or INSERT <MO_PR> in every <PACIENT> with:\n"
            f"  {new_value}\n"
            f"In files:\n{file_list}\n"
            f"Missing <MO_PR> will be created.\nOverwrite?",
        ):
            return
        self._run_replace_thread(
            label="MO_PR",
            worker_func=self._worker_replace_mo_pr,
            new_value=new_value,
        )

    def _worker_replace_mo_pr(self, new_value):
        """Функция-воркер для замены/вставки MO_PR в фоне."""
        total_count = 0
        total_files = 0
        for xml_path in self._last_xml_paths:
            replaced, created, _ = upsert_element_value(
                xml_path, "PACIENT", "MO_PR", new_value,
                xsd_path=self._xsd_path,
            )
            total_count += replaced + created
            if replaced > 0 or created > 0:
                total_files += 1
        return total_count, total_files

    # ══════════════════════════════════════════════
    #  ОБРАБОТЧИКИ: ЗАМЕНА / ВСТАВКА VZ
    # ══════════════════════════════════════════════
    def _on_replace_vz(self):
        """Запускает замену или вставку элементов VZ в PACIENT."""
        new_value = self._vz_var.get().strip()
        if not new_value:
            messagebox.showwarning("Empty", "Enter a value for VZ.")
            return
        if not self._check_files_loaded():
            return
        if not self._check_xsd_for_upsert("VZ"):
            return
        file_list = self._format_file_list(self._last_xml_paths)
        if not messagebox.askyesno(
            "Confirm VZ",
            f"Replace or INSERT <VZ> in every <PACIENT> with:\n"
            f"  {new_value}\n"
            f"In files:\n{file_list}\n"
            f"Missing <VZ> will be created.\nOverwrite?",
        ):
            return
        self._run_replace_thread(
            label="VZ",
            worker_func=self._worker_replace_vz,
            new_value=new_value,
        )

    def _worker_replace_vz(self, new_value):
        """Функция-воркер для замены/вставки VZ в фоне."""
        total_count = 0
        total_files = 0
        for xml_path in self._last_xml_paths:
            replaced, created, _ = upsert_element_value(
                xml_path, "PACIENT", "VZ", new_value,
                xsd_path=self._xsd_path,
            )
            total_count += replaced + created
            if replaced > 0 or created > 0:
                total_files += 1
        return total_count, total_files

    # ══════════════════════════════════════════════
    #  ОБРАБОТЧИКИ: ЗАМЕНА / ВСТАВКА KOEF_PR
    # ══════════════════════════════════════════════
    def _on_replace_koef_pr(self):
        """Запускает замену или вставку элементов KOEF_PR в KSG_KPG."""
        new_value = self._koef_pr_var.get().strip()
        if not new_value:
            messagebox.showwarning("Empty", "Enter a value for KOEF_PR.")
            return
        if not self._check_files_loaded():
            return
        if not self._check_xsd_for_upsert("KOEF_PR"):
            return
        file_list = self._format_file_list(self._last_xml_paths)
        if not messagebox.askyesno(
            "Confirm KOEF_PR",
            f"Replace or INSERT <KOEF_PR> in every <KSG_KPG> with:\n"
            f"  {new_value}\n"
            f"In files:\n{file_list}\n"
            f"Note: Works only if <KSG_KPG> block exists.\nOverwrite?",
        ):
            return
        self._run_replace_thread(
            label="KOEF_PR",
            worker_func=self._worker_replace_koef_pr,
            new_value=new_value,
        )

    def _worker_replace_koef_pr(self, new_value):
        """Функция-воркер для замены/вставки KOEF_PR в фоне."""
        total_count = 0
        total_files = 0
        for xml_path in self._last_xml_paths:
            # Родительский тег здесь KSG_KPG
            replaced, created, _ = upsert_element_value(
                xml_path, "KSG_KPG", "KOEF_PR", new_value,
                xsd_path=self._xsd_path,
            )
            total_count += replaced + created
            if replaced > 0 or created > 0:
                total_files += 1
        return total_count, total_files

    # ══════════════════════════════════════════════
    #  ОБРАБОТЧИКИ: ЗАМЕНА LPU_1 (КОНКРЕТНЫЕ USL)
    # ══════════════════════════════════════════════
    def _on_replace_lpu1_spec(self):
        """Запускает замену LPU_1 только в USL с определёнными кодами."""
        new_value = self._lpu1_spec_var.get().strip()
        if not new_value:
            messagebox.showwarning("Empty", "Enter a value for specific LPU_1.")
            return
        if not self._check_files_loaded():
            return
        target_codes = ["A05.10.006", "A05.10.004", "A04.28.001"]
        codes_str = ", ".join(target_codes)
        file_list = self._format_file_list(self._last_xml_paths)
        if not messagebox.askyesno(
            "Confirm Specific LPU_1",
            f"Replace <LPU_1> with:\n{new_value}\n"
            f"ONLY inside <USL> blocks where <CODE_USL> is one of:\n{codes_str}\n"
            f"In files:\n{file_list}\nOverwrite?",
        ):
            return
        self._run_replace_thread(
            label="LPU_1 (Specific)",
            worker_func=lambda val: self._worker_replace_lpu1_spec(val, target_codes),
            new_value=new_value,
        )

    def _worker_replace_lpu1_spec(self, new_value, target_codes):
        """Функция-воркер для замены LPU_1 в конкретных USL."""
        total_count = 0
        total_files = 0
        for xml_path in self._last_xml_paths:
            count, _ = replace_lpu1_for_specific_usl(
                xml_path, target_codes, new_value
            )
            total_count += count
            if count > 0:
                total_files += 1
        return total_count, total_files

    # ══════════════════════════════════════════════  <-- СЮДА
    #  ОБРАБОТЧИКИ: ДИАЛОГ NPR_NUM
    # ══════════════════════════════════════════════
    def _on_validate_npr_num(self):
        """Открывает диалоговое окно для редактирования NPR_NUM."""
        if not self._check_files_loaded():
            return
        dialog = NPRNumDialog(self.root, self._last_xml_paths)
        dialog.grab_set()
        dialog.focus_set()

    # ══════════════════════════════════════════════
    #  УНИВЕРСАЛЬНЫЙ ПОТОК ЗАМЕНЫ
    # ══════════════════════════════════════════════
    def _run_replace_thread(self, label, worker_func, new_value):
        """Запускает фоновый поток для выполнения операции замены."""
        self._is_running = True
        self._set_buttons(False)
        self._status_var.set(f"Replacing {label}...")

        def thread_target():
            try:
                total_count, total_files = worker_func(new_value)
                self.root.after(
                    0, self._on_replace_done,
                    label, total_count, total_files,
                )
            except Exception as e:
                self.root.after(
                    0, messagebox.showerror, f"{label} Error", str(e),
                )
                self.root.after(0, self._set_buttons, True)
                self._is_running = False

        threading.Thread(target=thread_target, daemon=True).start()

    def _on_replace_done(self, label, total_count, total_files):
        """Обрабатывает завершение операции замены — обновляет UI."""
        self._is_running = False
        self._set_buttons(True)
        self._progress_var.set(100)
        msg = (
            f"{label}: {total_count} element(s) updated "
            f"in {total_files} file(s)."
        )
        self._status_var.set(msg)
        messagebox.showinfo(f"{label} Done", msg)
        # Повторная валидация
        if self._schema and self._last_xml_paths:
            self._status_var.set("Re-validating after replacement...")
            #self._on_clear()
            on_clear_handler()
            self._run_validation(self._last_xml_paths)

    # ══════════════════════════════════════════════
    #  ДВИЖОК ВАЛИДАЦИИ
    # ══════════════════════════════════════════════
    def _run_validation(self, xml_paths):
        """Запускает процесс валидации XML-файлов в фоновом потоке."""
        if self._is_running:
            return
        #self._on_clear()
        on_clear_handler()
        self._is_running = True
        self._set_buttons(False)
        self._last_xml_paths = xml_paths
        validate_children = self._validate_children_var.get()
        child_tag = self._child_tag_var.get().strip() or None
        total = len(xml_paths)
        self._status_var.set(f"Validating {total} file(s)...")

        def on_progress(current, total):
            pct = (current / total) * 100 if total else 0
            self.root.after(0, self._progress_var.set, pct)
            self.root.after(
                0, self._status_var.set, f"Validating {current}/{total}...",
            )

        def worker():
            try:
                results = validate_batch(
                    xml_paths, self._schema,
                    validate_children=validate_children,
                    child_tag=child_tag,
                    on_progress=on_progress,
                )
                self.root.after(0, self._on_validation_done, results)
            except Exception as e:
                self.root.after(
                    0, messagebox.showerror, "Error", str(e),
                )
                self.root.after(0, self._set_buttons, True)
                self._is_running = False

        threading.Thread(target=worker, daemon=True).start()

    def _on_validation_done(self, results):
        """Обрабатывает завершение валидации — отображает результаты."""
        self._is_running = False
        self._results = results
        self._set_buttons(True)
        for i, r in enumerate(results):
            if r.is_valid:
                tag = "valid"
                status = "Valid"
            elif not r.is_wellformed:
                tag = "malformed"
                status = "Bad XML"
            elif r.elements_checked > 0:
                if r.elements_valid > 0:
                    tag = "partial"
                else:
                    tag = "invalid"
                status = f"{r.elements_valid}/{r.elements_checked} ok"
            else:
                tag = "invalid"
                status = f"Errors: {r.error_count}"
            checked_text = ""
            if r.elements_checked > 0:
                checked_text = f"{r.elements_valid}/{r.elements_checked}"
            self._tree.insert(
                "", tk.END, iid=str(i),
                values=(
                    r.file_path.name, status,
                    r.root_element or "-", checked_text, r.error_count,
                ),
                tags=(tag,),
            )
        ok = sum(1 for r in results if r.is_valid)
        fail = len(results) - ok
        self._status_var.set(
            f"Done! Total: {len(results)} | Valid: {ok} | Errors: {fail}"
        )

    # ══════════════════════════════════════════════
    #  ПАНЕЛЬ ДЕТАЛЕЙ
    # ══════════════════════════════════════════════
    def _show_details(self, result):
        """Отображает детальную информацию о результате валидации."""
        t = self._detail
        t.configure(state=tk.NORMAL)
        t.delete("1.0", tk.END)
        t.insert(tk.END, f"File: {result.file_path}\n", "info")
        t.insert(tk.END, f"Root: {result.root_element or '-'}\n", "info")
        if result.elements_checked > 0:
            t.insert(
                tk.END,
                f"Elements checked: {result.elements_checked}, "
                f"valid: {result.elements_valid}, "
                f"errors: "
                f"{result.elements_checked - result.elements_valid}\n",
                "info",
            )
        if result.fixes_applied:
            t.insert(
                tk.END,
                f"\nFixes applied: {len(result.fixes_applied)}\n",
                "fix",
            )
            for j, fix in enumerate(result.fixes_applied, 1):
                t.insert(
                    tk.END,
                    f"  {j}. [{fix.action}] {fix.element_path}\n"
                    f"     {fix.details}\n",
                    "fix",
                )
            t.insert(tk.END, "\n")
        t.insert(tk.END, "-" * 80 + "\n")
        if result.is_valid:
            t.insert(tk.END, "File is valid!\n", "ok")
        elif not result.errors:
            t.insert(tk.END, "No error details available.\n", "warning")
        else:
            error_num = 0
            for err in result.errors:
                if err.level == "INFO" and err.message.startswith("---"):
                    t.insert(tk.END, f"\n{err.message}\n", "header")
                elif err.level == "INFO":
                    t.insert(tk.END, f"{err.message}\n", "info")
                else:
                    error_num += 1
                    tag = {
                        "WARNING": "warning",
                        "ERROR": "error",
                        "FATAL": "fatal",
                    }.get(err.level, "error")
                    t.insert(tk.END, f"  {error_num}. {err}\n", tag)
        t.configure(state=tk.DISABLED)

    # ══════════════════════════════════════════════
    #  ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ══════════════════════════════════════════════
    def _check_schema(self):
        """Проверяет, загружена ли XSD-схема."""
        if self._schema is None:
            messagebox.showwarning("No schema", "Select XSD first!")
            return False
        return True

    def _check_files_loaded(self):
        """Проверяет, загружены ли XML-файлы для обработки."""
        if not self._last_xml_paths:
            messagebox.showwarning(
                "No files", "First validate file(s), then use tools.",
            )
            return False
        return True

    def _check_xsd_for_upsert(self, element_name):
        """Проверяет, доступна ли XSD для корректной вставки элементов."""
        if not self._xsd_path:
            messagebox.showwarning(
                "No schema",
                f"XSD needed to insert <{element_name}> at correct position.",
            )
            return False
        return True

    def _set_buttons(self, enabled):
        """Включает или отключает кнопки и поля ввода в интерфейсе."""
        state = tk.NORMAL if enabled else tk.DISABLED
        for btn in (
            self._btn_xsd,
            self._btn_files,
            self._btn_dir,
            self._btn_clear,
            self._btn_fix,
            self._btn_npr_num,
            self._btn_replace_lpu1,
            self._btn_replace_plat,
            self._btn_replace_mop,
            self._btn_replace_mo_pr,
            self._btn_replace_vz,
            self._btn_replace_koef_pr,
            self._btn_replace_lpu1_spec,
        ):
            btn.configure(state=state)
        entry_state = "normal" if enabled else "disabled"
        self._lpu1_entry.configure(state=entry_state)
        self._plat_entry.configure(state=entry_state)
        self._mop_entry.configure(state=entry_state)
        self._mo_pr_entry.configure(state=entry_state)
        self._vz_entry.configure(state=entry_state)
        self._koef_pr_entry.configure(state=entry_state)
        self._lpu1_spec_entry.configure(state=entry_state)

    @staticmethod
    def _format_file_list(paths, max_show=10):
        """Форматирует список путей к файлам для отображения в диалогах."""
        names = "\n".join(f"  {p.name}" for p in paths[:max_show])
        if len(paths) > max_show:
            names += f"\n... and {len(paths) - max_show} more"
        return names

    def run(self):
        """Запускает главный цикл приложения."""
        self.root.mainloop()