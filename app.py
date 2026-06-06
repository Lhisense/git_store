import json
import os
import sqlite3
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk


APP_TITLE = "大连动车车间电子股道表查询系统"
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "train_data.db")
TRAIN_TABLE = "车次"
SIGNAL_TABLE = "表示器显示"
RELATION_TABLE = "对应关系"
DEFAULT_SEARCH_FIELD = "_key"
VERSION_ROW_KEY = "version"
LATEST_VERSION_FIELD = "最新版本号"
CONTENT_FIELD = "\u5185\u5bb9"
EMPTY_DISPLAY = "-"
SECTION_FIELD = "\u533a\u6bb5"
QUEUE_FIELDS = ("\u961f\u52171", "\u961f\u52172", "\u961f\u52173")
IMPORT_PASSWORD = "Dccj2019.."


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def normalize_rows(value):
    if isinstance(value, list):
        rows = []
        for item in value:
            rows.append(item if isinstance(item, dict) else {"value": item})
        return rows
    if isinstance(value, dict):
        if value and all(isinstance(v, dict) for v in value.values()):
            rows = []
            for key, item in value.items():
                row = {DEFAULT_SEARCH_FIELD: key}
                row.update(item)
                rows.append(row)
            return rows
        return [value]
    return [{"value": value}]


def unwrap_nested_container(value):
    current = value
    while isinstance(current, dict) and len(current) == 1:
        nested_value = next(iter(current.values()))
        if isinstance(nested_value, (dict, list)):
            current = nested_value
            continue
        break
    return current


def to_text(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def parse_json_object(value):
    if not value:
        return None
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def format_display_value(value):
    if value is None:
        return EMPTY_DISPLAY
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else EMPTY_DISPLAY
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
        return text if text else EMPTY_DISPLAY
    text = str(value)
    return text if text else EMPTY_DISPLAY


def is_empty_display_item(key, value):
    return format_display_value(value) == EMPTY_DISPLAY


def trim_edge_empty_items(items, boundary_skip_keys=None):
    skip_keys = {str(key).strip() for key in (boundary_skip_keys or ())}
    content_indexes = [
        index
        for index, (key, value) in enumerate(items)
        if format_display_value(value) != EMPTY_DISPLAY and str(key).strip() not in skip_keys
    ]
    if not content_indexes:
        return [item for item in items if format_display_value(item[1]) != EMPTY_DISPLAY]

    start = content_indexes[0]
    end = content_indexes[-1]
    filtered_items = []
    for index, item in enumerate(items):
        if format_display_value(item[1]) != EMPTY_DISPLAY or start <= index <= end:
            filtered_items.append(item)
    return filtered_items


def resolve_signal_lookup_key(row, content_object):
    if isinstance(content_object, dict):
        section_value = content_object.get(SECTION_FIELD)
        if isinstance(section_value, str) and section_value.strip():
            return section_value.strip()
    if DEFAULT_SEARCH_FIELD in row.keys():
        fallback_value = row[DEFAULT_SEARCH_FIELD]
        if isinstance(fallback_value, str):
            return fallback_value.strip()
        return fallback_value
    return ""


class DatabaseService:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        self.conn.close()

    def initialize(self):
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.commit()

    def table_exists(self, table_name):
        row = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        return row is not None

    def get_columns(self, table_name):
        if not self.table_exists(table_name):
            return []
        rows = self.conn.execute(f"PRAGMA table_info({qident(table_name)})").fetchall()
        return [row["name"] for row in rows if row["name"] != "_id"]

    def list_user_tables(self):
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return [row["name"] for row in rows]

    def clear_user_tables(self):
        for name in self.list_user_tables():
            self.conn.execute(f"DROP TABLE IF EXISTS {qident(name)}")

    def build_rows_for_table(self, table_name, raw_value):
        if raw_value is None:
            raise ValueError(f"{table_name} 的值为空，无法导入。")

        normalized_value = unwrap_nested_container(raw_value)
        rows = normalize_rows(normalized_value)
        if not rows:
            raise ValueError(f"{table_name} 没有可导入的数据。")
        return rows

    def validate_required_tables(self):
        for table_name in (TRAIN_TABLE, SIGNAL_TABLE):
            if not self.table_exists(table_name):
                raise ValueError(f"缺少必需表：{table_name}")

            columns = self.get_columns(table_name)
            if DEFAULT_SEARCH_FIELD not in columns:
                raise ValueError(
                    f"{table_name} 导入后缺少 {DEFAULT_SEARCH_FIELD} 列。"
                    f"请确认 JSON 结构是“_key -> 对象”映射或对象列表。"
                )

    def import_json(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("JSON 顶层必须是对象。")
        try:
            self.conn.execute("BEGIN")
            self.clear_user_tables()

            for table_name, raw_value in payload.items():
                rows = self.build_rows_for_table(table_name, raw_value)

                columns = []
                seen = set()
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    for key in row.keys():
                        if key not in seen:
                            seen.add(key)
                            columns.append(key)
                if not columns:
                    columns = ["value"]

                self.conn.execute(
                    f"CREATE TABLE {qident(table_name)} (_id INTEGER PRIMARY KEY AUTOINCREMENT)"
                )
                for column in columns:
                    self.conn.execute(
                        f"ALTER TABLE {qident(table_name)} ADD COLUMN {qident(column)} TEXT"
                    )

                for row in rows:
                    values = {column: to_text(row.get(column)) for column in columns}
                    column_sql = ", ".join(qident(name) for name in values.keys())
                    placeholders = ", ".join("?" for _ in values)
                    self.conn.execute(
                        f"INSERT INTO {qident(table_name)} ({column_sql}) VALUES ({placeholders})",
                        tuple(values.values()),
                    )

            self.validate_required_tables()
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def fetch_latest_version(self):
        if not self.table_exists(TRAIN_TABLE):
            return ""
        columns = self.get_columns(TRAIN_TABLE)
        if DEFAULT_SEARCH_FIELD not in columns:
            return ""
        row = self.conn.execute(
            f"""
            SELECT *
            FROM {qident(TRAIN_TABLE)}
            WHERE COALESCE({qident(DEFAULT_SEARCH_FIELD)}, '') = ?
            LIMIT 1
            """,
            (VERSION_ROW_KEY,),
        ).fetchone()
        if not row:
            return ""
        if LATEST_VERSION_FIELD in row.keys():
            return row[LATEST_VERSION_FIELD] or ""
        if CONTENT_FIELD in row.keys():
            content = parse_json_object(row[CONTENT_FIELD])
            if isinstance(content, dict):
                version = content.get(LATEST_VERSION_FIELD)
                if version:
                    return str(version)
        return ""

    def search_train(self, keyword):
        if not self.table_exists(TRAIN_TABLE):
            return []
        columns = self.get_columns(TRAIN_TABLE)
        if DEFAULT_SEARCH_FIELD not in columns:
            return []

        if keyword:
            sql = f"""
                SELECT * FROM {qident(TRAIN_TABLE)}
                WHERE COALESCE({qident(DEFAULT_SEARCH_FIELD)}, '') LIKE ?
                ORDER BY COALESCE({qident(DEFAULT_SEARCH_FIELD)}, '') COLLATE NOCASE ASC, _id ASC
            """
            return self.conn.execute(sql, (f"%{keyword}%",)).fetchall()

        sql = (
            f"SELECT * FROM {qident(TRAIN_TABLE)} "
            f"ORDER BY COALESCE({qident(DEFAULT_SEARCH_FIELD)}, '') COLLATE NOCASE ASC, _id ASC "
            "LIMIT 200"
        )
        return self.conn.execute(sql).fetchall()

    def fetch_signal_rows_by_key(self, key_value):
        if not self.table_exists(SIGNAL_TABLE):
            return []
        columns = self.get_columns(SIGNAL_TABLE)
        if DEFAULT_SEARCH_FIELD not in columns:
            return []
        sql = f"""
            SELECT * FROM {qident(SIGNAL_TABLE)}
            WHERE COALESCE({qident(DEFAULT_SEARCH_FIELD)}, '') = ?
            ORDER BY _id DESC
        """
        return self.conn.execute(sql, (key_value,)).fetchall()

    def fetch_train_row_by_key(self, key_value):
        if not self.table_exists(TRAIN_TABLE):
            return None
        columns = self.get_columns(TRAIN_TABLE)
        if DEFAULT_SEARCH_FIELD not in columns:
            return None
        sql = f"""
            SELECT * FROM {qident(TRAIN_TABLE)}
            WHERE COALESCE({qident(DEFAULT_SEARCH_FIELD)}, '') = ?
            ORDER BY _id ASC
            LIMIT 1
        """
        return self.conn.execute(sql, (key_value,)).fetchone()

    def fetch_relation_row_by_key(self, key_value):
        if not self.table_exists(RELATION_TABLE):
            return None
        columns = self.get_columns(RELATION_TABLE)
        if DEFAULT_SEARCH_FIELD not in columns:
            return None
        sql = f"""
            SELECT * FROM {qident(RELATION_TABLE)}
            WHERE COALESCE({qident(DEFAULT_SEARCH_FIELD)}, '') = ?
            ORDER BY _id ASC
            LIMIT 1
        """
        return self.conn.execute(sql, (key_value,)).fetchone()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1840x980")
        self.minsize(1560, 860)
        self.configure(bg="#eef2f6")

        self.db = DatabaseService(DB_FILE)
        self.db.initialize()

        self.search_keyword = tk.StringVar()
        self.version_var = tk.StringVar(value="最新版本号：-")
        self.status_var = tk.StringVar(value="就绪")
        self.current_rows = []
        self.detail_panels = []
        self.search_after_id = None

        self.build_ui()
        self.refresh_after_import()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_ui(self):
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(
            "Detail.Treeview",
            font=("Microsoft YaHei", 11),
            rowheight=20,
            borderwidth=1,
            relief="solid",
            fieldbackground="white",
            background="white",
        )
        style.configure(
            "Detail.Treeview.Heading",
            font=("Microsoft YaHei", 11, "bold"),
            borderwidth=1,
            relief="solid",
        )

        header = tk.Frame(self, bg="#16324f", height=52)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header,
            text=APP_TITLE,
            bg="#16324f",
            fg="white",
            font=("Microsoft YaHei", 17, "bold"),
        ).pack(side="left", padx=14, pady=9)

        tk.Label(
            header,
            textvariable=self.version_var,
            bg="#16324f",
            fg="#d9f0ff",
            font=("Microsoft YaHei", 13),
        ).pack(side="right", padx=14)

        main = tk.PanedWindow(self, orient="horizontal", sashrelief="raised", bg="#eef2f6")
        main.pack(fill="both", expand=True, padx=8, pady=(4, 4))

        left_frame = tk.LabelFrame(main, text="车次显示", padx=6, pady=6, font=("Microsoft YaHei", 11, "bold"))
        center_frame = tk.LabelFrame(main, text="担当交路", padx=6, pady=6, font=("Microsoft YaHei", 11, "bold"))
        left_frame.configure(width=255)
        main.add(left_frame, minsize=220)
        main.add(center_frame, stretch="always")

        toolbar = tk.Frame(left_frame, bg="#eef2f6")
        toolbar.pack(fill="x", pady=(0, 6))

        tk.Button(
            toolbar,
            text="导入股道数据",
            command=self.import_json_file,
            bg="#2d6cdf",
            fg="white",
            relief="flat",
            padx=10,
            pady=4,
            font=("Microsoft YaHei", 11, "bold"),
        ).pack(side="left")

        tk.Label(
            toolbar,
            text="车次查询",
            bg="#eef2f6",
            font=("Microsoft YaHei", 11),
        ).pack(side="left", padx=(10, 6))

        entry = tk.Entry(
            toolbar,
            textvariable=self.search_keyword,
            width=14,
            font=("Microsoft YaHei", 11),
        )
        entry.pack(side="left", fill="x", expand=False)
        entry.bind("<KeyRelease>", self.on_search_change)

        self.result_list = tk.Listbox(left_frame, activestyle="dotbox", font=("Microsoft YaHei", 11))
        self.result_list.pack(fill="both", expand=True)
        self.result_list.bind("<<ListboxSelect>>", self.on_result_select)

        detail_modules_frame = tk.Frame(center_frame, bg="#eef2f6")
        detail_modules_frame.pack(fill="both", expand=True)

        detail_modules_frame.rowconfigure(0, weight=1)
        for column in range(4):
            detail_modules_frame.columnconfigure(column, weight=1, uniform="detail")
        for index in range(4):
            panel = self.create_detail_panel(detail_modules_frame, 0, index)
            self.detail_panels.append(panel)

        tk.Label(
            self,
            textvariable=self.status_var,
            anchor="w",
            bg="#dde5ee",
            fg="#334155",
            font=("Microsoft YaHei", 10),
        ).pack(fill="x", side="bottom")

    def create_detail_panel(self, parent, row_index, column_index):
        panel_frame = tk.Frame(parent, bg="#eef2f6", padx=2)
        panel_frame.grid(row=row_index, column=column_index, sticky="nsew", padx=2, pady=2)

        summary_var = tk.StringVar(value="")

        detail_meta_frame = tk.Frame(panel_frame, bg="#eef2f6", height=32)
        detail_meta_frame.pack(fill="x", expand=False, pady=(0, 2))
        detail_meta_frame.pack_propagate(False)

        detail_entry = tk.Entry(
            detail_meta_frame,
            textvariable=summary_var,
            font=("Microsoft YaHei", 11),
            relief="solid",
            bd=1,
            state="readonly",
            readonlybackground="white",
        )
        detail_entry.pack(fill="x", expand=False, ipady=1)

        content_frame = tk.LabelFrame(panel_frame, text="详情：", padx=3, pady=3, font=("Microsoft YaHei", 11, "bold"))
        content_frame.pack(fill="both", expand=True, pady=(1, 0))

        detail_header = tk.Frame(content_frame, bg="#e7edf5", height=28)
        detail_header.pack(fill="x")
        detail_header.pack_propagate(False)
        detail_header.columnconfigure(0, minsize=96)
        detail_header.columnconfigure(1, weight=1)
        tk.Label(
            detail_header,
            text="车站",
            bg="#e7edf5",
            fg="#0f172a",
            font=("Microsoft YaHei", 14, "bold"),
            anchor="w",
            justify="left",
            padx=8,
        ).grid(row=0, column=0, sticky="nsew")
        tk.Label(
            detail_header,
            text="停车股道",
            bg="#e7edf5",
            fg="#0f172a",
            font=("Microsoft YaHei", 14, "bold"),
            anchor="w",
            justify="left",
            padx=8,
        ).grid(row=0, column=1, sticky="nsew")

        header_separator = tk.Frame(content_frame, bg="#cfd8e3", height=1)
        header_separator.pack(fill="x")

        detail_body = tk.Frame(content_frame, bg="white")
        detail_body.pack(fill="both", expand=True)

        detail_canvas = tk.Canvas(
            detail_body,
            bg="white",
            highlightthickness=0,
            bd=0,
        )
        detail_scrollbar = ttk.Scrollbar(detail_body, orient="vertical", command=detail_canvas.yview)
        detail_canvas.configure(yscrollcommand=detail_scrollbar.set)
        detail_canvas.pack(side="left", fill="both", expand=True)
        detail_scrollbar.pack(side="right", fill="y")
        detail_content = tk.Frame(detail_canvas, bg="white")
        detail_content._detail_row_widgets = []
        detail_window = detail_canvas.create_window((0, 0), window=detail_content, anchor="nw")
        detail_content.bind(
            "<Configure>",
            lambda event, canvas=detail_canvas: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        detail_canvas.bind(
            "<Configure>",
            lambda event, canvas=detail_canvas, window_id=detail_window, content=detail_content: self.on_detail_canvas_resize(
                event,
                canvas,
                window_id,
                content,
            ),
        )

        signal_frame = tk.LabelFrame(panel_frame, text="进路表示器", padx=4, pady=4, font=("Microsoft YaHei", 11, "bold"), height=230)
        signal_frame.pack(fill="both", expand=False, pady=(1, 0))
        signal_frame.pack_propagate(False)

        signal_text = tk.Text(signal_frame, wrap="word", height=10, font=("Microsoft YaHei", 13))
        signal_text.pack(fill="both", expand=True)

        return {
            "summary_var": summary_var,
            "detail_canvas": detail_canvas,
            "detail_content": detail_content,
            "detail_row_widgets": detail_content._detail_row_widgets,
            "signal_text": signal_text,
        }

    def import_json_file(self):
        password = simpledialog.askstring("密码验证", "请输入导入密码：", show="*")
        if password is None:
            return
        if password != IMPORT_PASSWORD:
            messagebox.showerror("密码错误", "密码不正确，无法导入。")
            return

        path = filedialog.askopenfilename(
            title="选择 JSON 文件",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
            self.db.import_json(payload)
            self.status_var.set(f"已导入：{os.path.basename(path)}")
            self.refresh_after_import()
            messagebox.showinfo("导入成功", "JSON 已导入并覆盖本地数据库。")
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc))

    def refresh_version(self):
        version = self.db.fetch_latest_version()
        self.version_var.set(f"最新版本号：{version or '-'}")

    def refresh_after_import(self):
        self.refresh_version()
        self.search_keyword.set("")
        self.current_rows = []
        self.result_list.delete(0, tk.END)
        self.clear_detail_panels()

        columns = self.db.get_columns(TRAIN_TABLE)
        if not columns:
            self.status_var.set("未找到车次表")
            return
        if DEFAULT_SEARCH_FIELD not in columns:
            self.status_var.set("车次表缺少 _key 列，无法按要求搜索")
            return
        self.run_search()

    def on_search_change(self, _event=None):
        if self.search_after_id is not None:
            self.after_cancel(self.search_after_id)
        self.search_after_id = self.after(120, self.run_search)

    def on_detail_canvas_resize(self, event, canvas, window_id, content):
        canvas.itemconfigure(window_id, width=event.width)
        self.update_detail_row_wraplengths(content, event.width)

    def update_detail_row_wraplengths(self, content, total_width):
        field_width = max(92, min(120, int(total_width * 0.20)))
        value_wraplength = max(160, total_width - field_width - 20)
        for field_label, value_label in getattr(content, "_detail_row_widgets", []):
            field_label.configure(wraplength=field_width - 6)
            value_label.configure(wraplength=value_wraplength)

    def run_search(self):
        self.search_after_id = None
        keyword = self.search_keyword.get().strip()
        rows = self.db.search_train(keyword)
        self.current_rows = rows

        self.result_list.delete(0, tk.END)
        self.clear_detail_panels()

        for index, row in enumerate(rows, 1):
            summary = row[DEFAULT_SEARCH_FIELD] if DEFAULT_SEARCH_FIELD in row.keys() else ""
            self.result_list.insert(tk.END, f"{index}. {summary}")

        self.status_var.set(f"命中 {len(rows)} 条")
        if rows:
            self.result_list.selection_set(0)
            self.result_list.event_generate("<<ListboxSelect>>")

    def on_result_select(self, _event):
        selection = self.result_list.curselection()
        if not selection:
            return
        index = selection[0]
        if index >= len(self.current_rows):
            return
        self.show_row_details(index)

    def clear_detail_panels(self):
        for panel in self.detail_panels:
            panel["summary_var"].set("")
            for child in panel["detail_content"].winfo_children():
                child.destroy()
            panel["detail_row_widgets"].clear()
            panel["detail_content"]._detail_row_widgets = panel["detail_row_widgets"]
            panel["detail_canvas"].yview_moveto(0)
            panel["signal_text"].delete("1.0", tk.END)

    def insert_detail_table_rows(self, panel, rows):
        content = panel["detail_content"]
        content._detail_row_widgets = panel["detail_row_widgets"]
        for field_text, value_text in rows:
            row_frame = tk.Frame(content, bg="white", padx=3, pady=0)
            row_frame.pack(fill="x")
            row_frame.columnconfigure(0, minsize=92)
            row_frame.columnconfigure(1, weight=1)

            is_section = field_text == SECTION_FIELD
            row_font = ("Microsoft YaHei", 14, "bold") if is_section else ("Microsoft YaHei", 14)
            field_label = tk.Label(
                row_frame,
                text=field_text,
                bg="white",
                fg="#1f2937",
                font=row_font,
                anchor="w",
                justify="left",
                pady=0,
                wraplength=86,
            )
            value_label = tk.Label(
                row_frame,
                text=value_text,
                bg="white",
                fg="#111827",
                font=row_font,
                anchor="w",
                justify="left",
                pady=0,
                wraplength=260,
            )
            field_label.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=0)
            value_label.grid(row=0, column=1, sticky="ew", pady=0)

            separator = tk.Frame(content, bg="#d6dde6", height=1)
            separator.pack(fill="x")
            panel["detail_row_widgets"].append((field_label, value_label))

        self.update_detail_row_wraplengths(content, max(panel["detail_canvas"].winfo_width(), 320))

    def show_row_details(self, start_index):
        self.clear_detail_panels()
        if start_index >= len(self.current_rows):
            return

        base_row = self.current_rows[start_index]
        self.render_detail_panel(self.detail_panels[0], base_row)

        base_key = base_row[DEFAULT_SEARCH_FIELD] if DEFAULT_SEARCH_FIELD in base_row.keys() else ""
        relation_row = self.db.fetch_relation_row_by_key(base_key) if base_key else None
        if not relation_row:
            return

        for panel_index, queue_field in enumerate(QUEUE_FIELDS, start=1):
            if panel_index >= len(self.detail_panels):
                break
            if queue_field not in relation_row.keys():
                continue
            queue_key = format_display_value(relation_row[queue_field])
            if queue_key == EMPTY_DISPLAY:
                continue
            queue_row = self.db.fetch_train_row_by_key(queue_key)
            if queue_row:
                self.render_detail_panel(self.detail_panels[panel_index], queue_row)

    def render_detail_panel(self, panel, row):
        panel["summary_var"].set(format_display_value(row[DEFAULT_SEARCH_FIELD]) if DEFAULT_SEARCH_FIELD in row.keys() else EMPTY_DISPLAY)
        for child in panel["detail_content"].winfo_children():
            child.destroy()
        panel["detail_row_widgets"].clear()
        panel["detail_content"]._detail_row_widgets = panel["detail_row_widgets"]
        content_value = None

        for key in row.keys():
            if key == "_id":
                continue
            if key == CONTENT_FIELD:
                content_value = row[key]
                continue

        content_object = parse_json_object(content_value)
        key_value = resolve_signal_lookup_key(row, content_object)
        if content_object:
            table_rows = []
            display_items = trim_edge_empty_items(list(content_object.items()), boundary_skip_keys={SECTION_FIELD})
            for key, value in display_items:
                display_value = format_display_value(value)
                if display_value == EMPTY_DISPLAY:
                    continue
                display_key = key if str(key).strip() else "(空字段)"
                table_rows.append((display_key, display_value))
            self.insert_detail_table_rows(panel, table_rows)
        else:
            display_value = format_display_value(content_value)
            if display_value != EMPTY_DISPLAY:
                self.insert_detail_table_rows(panel, [(CONTENT_FIELD, display_value)])

        panel["signal_text"].delete("1.0", tk.END)
        if not key_value:
            panel["signal_text"].insert(tk.END, "当前记录缺少可用于查询表示器显示的区段或 _key")
            return

        matches = self.db.fetch_signal_rows_by_key(key_value)
        if not matches:
            panel["signal_text"].insert(tk.END, "表示器显示表中未找到对应 _key")
            return

        lines = []
        for index, item in enumerate(matches, 1):
            signal_content = item[CONTENT_FIELD] if CONTENT_FIELD in item.keys() else None
            signal_content_object = parse_json_object(signal_content)
            if len(matches) > 1:
                lines.append(f"{index}.")
            if signal_content_object:
                display_items = trim_edge_empty_items(list(signal_content_object.items()))
                for signal_key, signal_value in display_items:
                    if is_empty_display_item(signal_key, signal_value) and not str(signal_key).strip():
                        lines.append(EMPTY_DISPLAY)
                        continue
                    display_key = signal_key if str(signal_key).strip() else "(空字段)"
                    lines.append(f"{display_key}：{format_display_value(signal_value)}")
            else:
                lines.append(format_display_value(signal_content))
            if len(matches) > 1 and index < len(matches):
                lines.append("")
        panel["signal_text"].insert(tk.END, "\n".join(lines).rstrip())

    def on_close(self):
        self.db.close()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
