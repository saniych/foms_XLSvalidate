import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox

from core.core import get_records_with_for_pom, set_npr_num


class NPRNumDialog(tk.Toplevel):
    """
    Окно для редактирования NPR_NUM у записей с FOR_POM=3.
    """
    COL_FILE = 0
    COL_N_ZAP = 1
    COL_IDCASE = 2
    COL_ID_PAC = 3
    COL_NPR_MO = 4
    COL_NPR_DATE = 5
    COL_NPR_NUM = 6
    COL_STATUS = 7

    def __init__(self, parent, xml_paths: list):
        super().__init__(parent)
        self.title("Validate NPR_NUM — FOR_POM = 3")
        self.geometry("1300x700")
        self.minsize(1000, 500)
        self.configure(bg="#f5f5f5")
        self.resizable(True, True)
        self._xml_paths = xml_paths
        self._records = []      # список dict из core
        self._entries = {}      # idcase -> tk.StringVar
        self._build_ui()
        self._load_records()

    # ──────────────────────────────────────────────
    #  ПОЛЬЗОВАТЕЛЬСКИЙ ИНТЕРФЕЙС
    # ──────────────────────────────────────────────
    def _build_ui(self):
        # Заголовок
        hdr = tk.Frame(self, bg="#2c3e50", height=45)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(
            hdr,
            text="Записи с FOR_POM = 3 — ввод NPR_NUM",
            font=("Segoe UI", 12, "bold"),
            bg="#2c3e50", fg="#ecf0f1",
        ).pack(side=tk.LEFT, padx=15, pady=8)
        # Счётчик
        self._count_var = tk.StringVar(value="Загрузка...")
        tk.Label(
            hdr, textvariable=self._count_var,
            font=("Segoe UI", 10), bg="#2c3e50", fg="#95a5a6",
        ).pack(side=tk.RIGHT, padx=15)
        # Фильтр
        filter_row = tk.Frame(self, bg="#f5f5f5", pady=5)
        filter_row.pack(fill=tk.X, padx=10)
        tk.Label(
            filter_row, text="Фильтр по файлу/IDCASE/ID_PAC:",
            font=("Segoe UI", 9), bg="#f5f5f5",
        ).pack(side=tk.LEFT)
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", self._on_filter)
        filter_entry = tk.Entry(
            filter_row, textvariable=self._filter_var,
            font=("Segoe UI", 10), width=30,
        )
        filter_entry.pack(side=tk.LEFT, padx=(5, 0))
        tk.Button(
            filter_row, text="Сбросить",
            font=("Segoe UI", 9),
            command=lambda: self._filter_var.set(""),
            padx=8,
        ).pack(side=tk.LEFT, padx=5)
        # Прогресс-бар
        self._progress = ttk.Progressbar(self, maximum=100)
        self._progress.pack(fill=tk.X, padx=10, pady=(0, 3))
        # Canvas + Scrollbar для строк
        container = tk.Frame(self, bg="#f5f5f5")
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))
        # Шапка таблицы
        self._build_header_row(container)
        # Область с прокруткой
        self._canvas = tk.Canvas(container, bg="#f5f5f5", highlightthickness=0)
        vsb = ttk.Scrollbar(container, orient=tk.VERTICAL,
                            command=self._canvas.yview)
        hsb = ttk.Scrollbar(container, orient=tk.HORIZONTAL,
                            command=self._canvas.xview)
        self._canvas.configure(
            yscrollcommand=vsb.set, xscrollcommand=hsb.set,
        )
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._rows_frame = tk.Frame(self._canvas, bg="#f5f5f5")
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._rows_frame, anchor="nw",
        )
        self._rows_frame.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        # Кнопки внизу
        self._build_bottom_bar()

    def _build_header_row(self, parent):
        """Создаёт шапку таблицы с заголовками колонок."""
        hrow = tk.Frame(parent, bg="#bdc3c7")
        hrow.pack(fill=tk.X)
        headers = [
            ("Файл", 180),
            ("N_ZAP", 60),
            ("IDCASE", 220),
            ("ID_PAC", 160),
            ("N_HISTORY", 130),
            ("NPR_MO", 100),
            ("NPR_DATE", 100),
            ("NPR_NUM (ввод)", 200),
            ("Статус", 100),
        ]
        for text, width in headers:
            tk.Label(
                hrow, text=text,
                font=("Segoe UI", 9, "bold"),
                bg="#bdc3c7", fg="#2c3e50",
                width=width // 8, anchor="w",
                padx=4, pady=4,
            ).pack(side=tk.LEFT)

    def _build_bottom_bar(self):
        """Создаёт нижнюю панель с кнопками управления."""
        bar = tk.Frame(self, bg="#ecf0f1", pady=8)
        bar.pack(fill=tk.X, padx=10)
        self._btn_add_all = tk.Button(
            bar,
            text="Add NPR_NUM (все заполненные)",
            font=("Segoe UI", 10, "bold"),
            command=self._on_add_all,
            bg="#27ae60", fg="white", padx=20, pady=5,
        )
        self._btn_add_all.pack(side=tk.LEFT, padx=(0, 10))
        self._btn_reload = tk.Button(
            bar,
            text="Обновить список",
            font=("Segoe UI", 10),
            command=self._load_records,
            padx=15, pady=5,
        )
        self._btn_reload.pack(side=tk.LEFT)
        self._result_var = tk.StringVar(value="")
        tk.Label(
            bar, textvariable=self._result_var,
            font=("Segoe UI", 10, "bold"),
            bg="#ecf0f1", fg="#27ae60",
        ).pack(side=tk.LEFT, padx=15)
        tk.Button(
            bar,
            text="Закрыть",
            font=("Segoe UI", 10),
            command=self.destroy,
            padx=15, pady=5,
        ).pack(side=tk.RIGHT)

    # ──────────────────────────────────────────────
    #  ЗАГРУЗКА ЗАПИСЕЙ
    # ──────────────────────────────────────────────
    def _load_records(self):
        """Загружает записи с FOR_POM=3 из всех XML-файлов."""
        self._records.clear()
        self._entries.clear()
        self._progress["value"] = 0
        self._result_var.set("")
        total = len(self._xml_paths)
        for i, xml_path in enumerate(self._xml_paths, 1):
            try:
                recs = get_records_with_for_pom(xml_path, for_pom_value="3")
                self._records.extend(recs)
            except Exception as e:
                self._records.append({
                    "file_path": xml_path,
                    "n_zap": "ERR",
                    "idcase": str(e),
                    "id_pac": "",
                    "npr_mo": "",
                    "npr_date": "",
                    "npr_num": "",
                    "for_pom": "?",
                })
            self._progress["value"] = (i / total) * 100
        self._count_var.set(f"Найдено записей: {len(self._records)}")
        self._render_rows(self._records)

    # ──────────────────────────────────────────────
    #  ОТРИСОВКА СТРОК
    # ──────────────────────────────────────────────
    def _render_rows(self, records):
        """Отрисовывает список записей в таблице."""
        # Очищаем
        for widget in self._rows_frame.winfo_children():
            widget.destroy()
        if not records:
            tk.Label(
                self._rows_frame,
                text="Нет записей с FOR_POM = 3",
                font=("Segoe UI", 11, "italic"),
                bg="#f5f5f5", fg="#95a5a6",
                pady=20,
            ).pack()
            return
        for idx, rec in enumerate(records):
            self._render_one_row(idx, rec)

    def _render_one_row(self, idx: int, rec: dict):
        """Отрисовывает одну строку таблицы с данными записи."""
        bg = "#ffffff" if idx % 2 == 0 else "#f4f6f9"
        row = tk.Frame(self._rows_frame, bg=bg, pady=3)
        row.pack(fill=tk.X)
        # Файл
        self._cell(row, Path(rec["file_path"]).name, 180, bg)
        # N_ZAP
        self._cell(row, rec["n_zap"], 60, bg)
        # IDCASE
        self._cell(row, rec["idcase"], 220, bg)
        # ID_PAC
        self._cell(row, rec["id_pac"], 160, bg)
        # N_HISTORY  <-- новое
        self._cell(row, rec["nhistory"], 130, bg)
        # NPR_MO
        self._cell(row, rec["npr_mo"], 100, bg)
        # NPR_DATE
        self._cell(row, rec["npr_date"], 100, bg)
        # NPR_NUM — текстовое поле для ввода
        idcase = rec["idcase"]
        if idcase not in self._entries:
            var = tk.StringVar(value=rec["npr_num"] or "")
            self._entries[idcase] = {
                "var": var,
                "file_path": rec["file_path"],
                "status_var": None,
            }
        else:
            var = self._entries[idcase]["var"]
        entry_frame = tk.Frame(row, bg=bg)
        entry_frame.pack(side=tk.LEFT, padx=2)
        entry = tk.Entry(
            entry_frame, textvariable=var,
            font=("Consolas", 10), width=24,
        )
        entry.pack(side=tk.LEFT)
        # Кнопка "Add" для одной строки
        status_var = tk.StringVar(value="")
        if self._entries[idcase]["status_var"] is None:
            self._entries[idcase]["status_var"] = status_var
        tk.Button(
            row,
            text="Add",
            font=("Segoe UI", 9, "bold"),
            command=lambda ic=idcase, sv=status_var: self._on_add_one(ic, sv),
            bg="#2980b9", fg="white", padx=8,
        ).pack(side=tk.LEFT, padx=4)
        # Статус
        tk.Label(
            row, textvariable=status_var,
            font=("Segoe UI", 9, "bold"),
            bg=bg, fg="#27ae60", width=10, anchor="w",
        ).pack(side=tk.LEFT, padx=4)

    def _cell(self, parent, text: str, width: int, bg: str):
        """Создаёт ячейку таблицы с текстом."""
        tk.Label(
            parent, text=text or "—",
            font=("Segoe UI", 9),
            bg=bg, fg="#2c3e50",
            width=width // 8, anchor="w",
            padx=4,
        ).pack(side=tk.LEFT)

    # ──────────────────────────────────────────────
    #  ФИЛЬТР
    # ──────────────────────────────────────────────
    def _on_filter(self, *_):
        """Обрабатывает изменение текста в поле фильтра."""
        query = self._filter_var.get().lower().strip()
        if not query:
            self._render_rows(self._records)
            return
        filtered = [
            r for r in self._records
            if query in Path(r["file_path"]).name.lower()
            or query in (r["idcase"] or "").lower()
            or query in (r["id_pac"] or "").lower()
            or query in (r["n_zap"] or "").lower()
        ]
        self._render_rows(filtered)

    # ──────────────────────────────────────────────
    #  ФОРМАТИРОВАНИЕ NPR_NUM
    # ──────────────────────────────────────────────
    @staticmethod
    def _format_npr_num(raw_value: str) -> str:
        """
        Форматирует NPR_NUM до 15 символов.
        Префикс 495, затем нули, затем введённое значение.
        Примеры:
        2051  → 49500000002051  (495 + 8 нулей + 2051)
        22511 → 495000000022511 (495 + 7 нулей + 22511)
        """
        digits = raw_value.strip()
        # Если уже 15 символов — не трогаем
        if len(digits) >= 15:
            return digits
        prefix = "495"
        zeros_count = 15 - len(prefix) - len(digits)
        if zeros_count < 0:
            # Введено слишком много цифр — вернуть как есть
            return digits
        return prefix + "0" * zeros_count + digits

    # ──────────────────────────────────────────────
    #  СОХРАНЕНИЕ
    # ──────────────────────────────────────────────
    def _on_add_one(self, idcase: str, status_var: tk.StringVar):
        """Обрабатывает сохранение NPR_NUM для одной записи."""
        entry_info = self._entries.get(idcase)
        if not entry_info:
            return
        raw_value = entry_info["var"].get().strip()
        if not raw_value:
            messagebox.showwarning(
                "Пусто", f"Введите NPR_NUM для IDCASE: {idcase}",
                parent=self,
            )
            return
        # Валидация — только цифры
        if not raw_value.isdigit():
            messagebox.showwarning(
                "Ошибка", "NPR_NUM должен содержать только цифры.",
                parent=self,
            )
            return
        formatted = self._format_npr_num(raw_value)
        # Показываем что будет сохранено
        entry_info["var"].set(formatted)
        try:
            ok = set_npr_num(
                Path(entry_info["file_path"]),
                idcase, formatted,
            )
            if ok:
                status_var.set("✓ Сохранено")
            else:
                status_var.set("✗ Не найден")
        except Exception as e:
            status_var.set("✗ Ошибка")
            messagebox.showerror("Ошибка", str(e), parent=self)

    def _on_add_all(self):
        """Обрабатывает массовое сохранение всех заполненных NPR_NUM."""
        saved = 0
        skipped = 0
        errors = 0
        for idcase, info in self._entries.items():
            raw_value = info["var"].get().strip()
            if not raw_value:
                skipped += 1
                continue
            # Пропускаем уже отформатированные (15 символов)
            if len(raw_value) == 15 and raw_value.isdigit():
                formatted = raw_value
            elif not raw_value.isdigit():
                errors += 1
                continue
            else:
                formatted = self._format_npr_num(raw_value)
            # Обновляем поле ввода
            info["var"].set(formatted)
            try:
                ok = set_npr_num(
                    Path(info["file_path"]),
                    idcase, formatted,
                )
                if ok:
                    saved += 1
                    if info["status_var"]:
                        info["status_var"].set("✓ Сохранено")
                else:
                    errors += 1
            except Exception:
                errors += 1
        msg = (
            f"Сохранено: {saved}\n"
            f"Пропущено (пустые): {skipped}\n"
            f"Ошибок: {errors}"
        )
        self._result_var.set(
            f"✓ Сохранено: {saved}, пропущено: {skipped}"
        )
        messagebox.showinfo("Готово", msg, parent=self)

    # ──────────────────────────────────────────────
    #  ПРОКРУТКА CANVAS
    # ──────────────────────────────────────────────
    def _on_frame_configure(self, _event):
        """Обновляет область прокрутки при изменении размера фрейма."""
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        """Подстраивает ширину контента под размер canvas."""
        self._canvas.itemconfig(self._canvas_window, width=event.width)
