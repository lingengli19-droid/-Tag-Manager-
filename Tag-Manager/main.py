import tkinter as tk
from tkinter import messagebox, ttk, filedialog, simpledialog
import json
import os
import re
import time
import threading
from PIL import Image, ImageTk
from deep_translator import GoogleTranslator

try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class UltimatePaletteApp:
    def __init__(self, root):
        self.root = root
        self.root.title("标签工具 v1.0")

        self.root.geometry("1150x850")
        self.root.minsize(950, 650)

        self.config_dir = os.path.join(os.path.expanduser("~"), ".ultimate_palette")
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_file = os.path.join(self.config_dir, "path_config.json")

        self.workspace_dir = self.load_saved_workspace_path()

        self.prompt_bank = {"默认提示词库": []}
        self.current_sub_bank = "默认提示词库"

        self.image_keepalive = {}
        self.click_tracker = {}
        self.edit_ctx = {}

        self._tagger_model_key = None
        self._tagger_loading = False
        self._tagger_cancelled = False

        self._tag_db = None
        self._translations = None

        self._editor_dataset = {}
        self._editor_image_keepalive = {}

        self.setup_hd_styles()
        self.setup_ui()
        self.load_all_data_from_workspace()
        self._init_tag_database_async()

    def _init_tag_database_async(self):
        def load():
            from editor.tag_database import TagDatabase
            from editor.translation import load_translations
            db = TagDatabase()
            data_dir = os.path.join(BASE_DIR, 'data')
            db.load_all(data_dir)
            trans_path = os.path.join(data_dir, 'translations', 'zh-CN.txt')
            trans = load_translations(trans_path)
            self.root.after(0, lambda: self._on_tag_db_loaded(db, trans))
        threading.Thread(target=load, daemon=True).start()

    def _on_tag_db_loaded(self, db, translations):
        self._tag_db = db
        self._translations = translations

    def setup_hd_styles(self):
        self.style = ttk.Style()
        self.style.theme_use("vista" if "vista" in self.style.theme_names() else "default")
        font_config = ("Microsoft YaHei", 10)
        self.style.configure(".", font=font_config)
        self.style.configure("TLabelFrame", font=("Microsoft YaHei", 10, "bold"))
        self.style.configure("TNotebook.Tab", font=("Microsoft YaHei", 10, "bold"), padding=[12, 4])
        self.root.option_add("*Font", font_config)

    def load_saved_workspace_path(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    path = cfg.get("workspace_dir", os.getcwd())
                    if os.path.exists(path):
                        return path
            except:
                pass
        return os.getcwd()

    def save_workspace_path_to_config(self, path):
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump({"workspace_dir": path}, f, indent=4)
        except Exception as e:
            print(f"路径配置写入失败: {e}")

    def setup_ui(self):
        path_frame = ttk.LabelFrame(self.root, text=" 📂 工作文件绝对保存路径", padding=8)
        path_frame.pack(fill=tk.X, padx=12, pady=6)

        self.path_var = tk.StringVar(value=self.workspace_dir)
        self.path_entry = ttk.Entry(path_frame, textvariable=self.path_var, state="readonly",
                                     font=("Microsoft YaHei", 9))
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        change_path_btn = ttk.Button(path_frame, text="更改并迁移地址", command=self.change_workspace)
        change_path_btn.pack(side=tk.RIGHT, padx=5)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        self.tab_prompt = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_prompt, text="  📸 提示词库  ")
        self.setup_prompt_tab()

        self.tab_tagger = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_tagger, text="  🏷️ 数据集标注  ")
        self.setup_tagger_tab()

        self.tab_editor = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_editor, text="  ✏️ 标签编辑器  ")
        self.setup_editor_tab()

        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN,
                               anchor=tk.W, padding=6, font=("Microsoft YaHei", 9))
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def change_workspace(self):
        new_dir = filedialog.askdirectory(title="重定向所有生成文件的存放目录")
        if new_dir:
            new_dir = os.path.normpath(new_dir)
            self.workspace_dir = new_dir
            self.path_var.set(new_dir)
            self.save_workspace_path_to_config(new_dir)
            self.clear_prompt_widgets()
            self.image_keepalive.clear()
            self.load_all_data_from_workspace()

    def bind_right_click_paste(self, widget):
        def do_paste(event):
            try:
                clipboard_text = self.root.clipboard_get()
                if clipboard_text:
                    if isinstance(widget, tk.Text):
                        try:
                            widget.delete("sel.first", "sel.last")
                        except:
                            pass
                        widget.insert("insert", clipboard_text)
                    else:
                        try:
                            if widget.select_present():
                                widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
                        except:
                            pass
                        current_idx = widget.index(tk.INSERT)
                        widget.insert(current_idx, clipboard_text)
            except:
                pass
            return "break"
        widget.bind("<Button-3>", do_paste)
        widget.bind("<Button-2>", do_paste)

    # ================== TAB 1: 提示词库 ==================
    def setup_prompt_tab(self):
        main_paned = ttk.PanedWindow(self.tab_prompt, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.LabelFrame(main_paned, text=" 📂 分类小提示词库 ", padding=5)
        main_paned.add(left_frame, weight=1)

        btn_box = ttk.Frame(left_frame)
        btn_box.pack(fill=tk.X, pady=2)
        ttk.Button(btn_box, text="➕ 新建", command=self.add_sub_bank).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)
        ttk.Button(btn_box, text="✏️ 改名", command=self.rename_sub_bank).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)
        ttk.Button(btn_box, text="❌ 删除", command=self.delete_sub_bank).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)

        self.bank_listbox = tk.Listbox(left_frame, font=("Microsoft YaHei", 10), selectmode=tk.SINGLE,
                                       bd=1, relief=tk.SOLID)
        self.bank_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self.bank_listbox.bind("<<ListboxSelect>>", self.on_sub_bank_change)

        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=5)

        in_frame = ttk.Frame(right_frame)
        in_frame.pack(fill=tk.X, pady=2, padx=5)
        self.cur_bank_lbl = ttk.Label(in_frame, text="当前小库: 默认提示词库 | 输入:",
                                       font=("Microsoft YaHei", 9, "bold"))
        self.cur_bank_lbl.pack(side=tk.LEFT, padx=2)

        self.prompt_entry = ttk.Entry(in_frame)
        self.prompt_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.prompt_entry.bind("<Return>", lambda e: self.add_prompt())
        self.bind_right_click_paste(self.prompt_entry)

        ttk.Button(in_frame, text="添加并上传参考图", command=self.add_prompt).pack(side=tk.RIGHT, padx=2)
        ttk.Button(in_frame, text="🌐 一键全量翻译并保存",
                   command=self.start_global_translation).pack(side=tk.RIGHT, padx=2)

        list_frame = ttk.Frame(right_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5, padx=5)

        self.outer_canvas = tk.Canvas(list_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.outer_canvas.yview)

        self.scroll_prompt_frame = ttk.Frame(self.outer_canvas)
        self.scroll_prompt_frame.bind("<Configure>", self.on_grid_frame_configure)

        self.outer_canvas.create_window((0, 0), window=self.scroll_prompt_frame, anchor="nw")
        self.outer_canvas.configure(yscrollcommand=scrollbar.set)
        self.outer_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Mouse wheel binding
        _canvas_ref = self.outer_canvas

        def _on_mousewheel(event):
            _canvas_ref.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mw(e):
            _canvas_ref.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mw(e):
            _canvas_ref.unbind_all("<MouseWheel>")

        self.outer_canvas.bind("<Enter>", _bind_mw)
        self.outer_canvas.bind("<Leave>", _unbind_mw)

    def on_grid_frame_configure(self, event):
        self.outer_canvas.configure(scrollregion=self.outer_canvas.bbox("all"))

    def add_sub_bank(self):
        new_name = simpledialog.askstring("新建提示词库", "请输入新小库的名称:", parent=self.root)
        if new_name:
            new_name = new_name.strip()
            if not new_name:
                return
            if new_name in self.prompt_bank:
                messagebox.showwarning("警告", "该分类小库已存在！")
                return
            self.prompt_bank[new_name] = []
            self.refresh_bank_listbox()
            self.switch_to_sub_bank(new_name)
            self.save_prompt_data_to_workspace()

    def rename_sub_bank(self):
        old_name = self.current_sub_bank
        new_name = simpledialog.askstring("重命名提示词库", f"请输入【{old_name}】的新名称:",
                                          initialvalue=old_name, parent=self.root)
        if new_name:
            new_name = new_name.strip()
            if not new_name or new_name == old_name:
                return
            if new_name in self.prompt_bank:
                messagebox.showwarning("错误", "该小库名称已存在！", parent=self.root)
                return
            self.prompt_bank[new_name] = self.prompt_bank.pop(old_name)
            self.current_sub_bank = new_name
            self.switch_to_sub_bank(new_name)
            self.save_prompt_data_to_workspace()

    def delete_sub_bank(self):
        if self.current_sub_bank == "默认提示词库":
            messagebox.showwarning("警告", "核心『默认提示词库』不允许删除！")
            return
        if messagebox.askyesno("确认删除", f"确定要删除小库【{self.current_sub_bank}】吗？"):
            for item in self.prompt_bank[self.current_sub_bank]:
                full_path = os.path.normpath(os.path.join(self.workspace_dir, item["img_path"]))
                if os.path.exists(full_path):
                    try:
                        os.remove(full_path)
                    except:
                        pass
            del self.prompt_bank[self.current_sub_bank]
            self.switch_to_sub_bank("默认提示词库")
            self.refresh_bank_listbox()
            self.save_prompt_data_to_workspace()

    def refresh_bank_listbox(self):
        self.bank_listbox.delete(0, tk.END)
        for idx, bank_name in enumerate(self.prompt_bank.keys()):
            self.bank_listbox.insert(tk.END, bank_name)
            if bank_name == self.current_sub_bank:
                self.bank_listbox.select_set(idx)

    def on_sub_bank_change(self, event):
        selection = self.bank_listbox.curselection()
        if selection:
            bank_name = self.bank_listbox.get(selection[0])
            self.switch_to_sub_bank(bank_name)

    def switch_to_sub_bank(self, bank_name):
        self.current_sub_bank = bank_name
        self.cur_bank_lbl.config(text=f"当前小库: {bank_name} | 输入:")
        self.refresh_bank_listbox()
        self.refresh_prompt_display_view()

    def refresh_prompt_display_view(self):
        self.clear_prompt_widgets()
        current_items = self.prompt_bank.get(self.current_sub_bank, [])
        if not current_items:
            return
        canvas_width = self.outer_canvas.winfo_width()
        if canvas_width < 10:
            canvas_width = 700
        card_width = 180
        columns = max(1, canvas_width // card_width)
        for idx, item in enumerate(current_items):
            r = idx // columns
            c = idx % columns
            self.create_prompt_grid_card(item, r, c)

    def clear_prompt_widgets(self):
        for child in self.scroll_prompt_frame.winfo_children():
            child.destroy()

    def add_prompt(self):
        prompt_text = self.prompt_entry.get().strip()
        if not prompt_text:
            messagebox.showwarning("警告", "提示词不能为空！")
            return

        file_path = filedialog.askopenfilename(
            title="选择参考图",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png *.webp *.bmp")]
        )
        if not file_path:
            return

        img_dir = os.path.join(self.workspace_dir, "reference_images")
        os.makedirs(img_dir, exist_ok=True)

        safe_filename = f"img_{int(time.time())}{os.path.splitext(file_path)[1].lower()}"
        dest_path = os.path.join(img_dir, safe_filename)

        if self.compress_and_save_image(file_path, dest_path):
            relative_img_path = os.path.join("reference_images", safe_filename)
            prompt_item = {
                "text": prompt_text,
                "translation": "",
                "img_path": relative_img_path,
                "notes": []
            }
            self.prompt_bank[self.current_sub_bank].append(prompt_item)
            self.refresh_prompt_display_view()
            self.save_prompt_data_to_workspace()
            self.prompt_entry.delete(0, tk.END)
        else:
            messagebox.showerror("错误", "图片压缩失败。")

    def compress_and_save_image(self, source_path, target_path, max_size_mb=1.9):
        max_bytes = max_size_mb * 1024 * 1024
        try:
            img = Image.open(source_path)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            if os.path.getsize(source_path) <= max_bytes and source_path.lower().endswith(
                    ('.jpg', '.jpeg', '.png')):
                img.save(target_path)
                return True
            quality = 85
            width, height = img.size
            while True:
                img.save(target_path, "JPEG", quality=quality)
                current_size = os.path.getsize(target_path)
                if current_size <= max_bytes:
                    break
                if quality > 40:
                    quality -= 10
                else:
                    width = int(width * 0.85)
                    height = int(height * 0.85)
                    img = img.resize((width, height), Image.Resampling.LANCZOS)
                if width < 50 or height < 50:
                    break
            return True
        except Exception as e:
            print(f"压缩故障: {e}")
            return False

    def create_prompt_grid_card(self, item, row, col):
        card = tk.Frame(self.scroll_prompt_frame, bg="#ffffff", bd=1, relief=tk.RIDGE, padx=4, pady=4)
        card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")

        full_img_path = os.path.normpath(os.path.join(self.workspace_dir, item["img_path"]))

        img_canvas = tk.Canvas(card, width=150, height=150, bg="#f5f5f5",
                               highlightthickness=0, cursor="hand2")
        img_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        if os.path.exists(full_img_path):
            try:
                pil_img = Image.open(full_img_path)
                if pil_img.mode != "RGB":
                    pil_img = pil_img.convert("RGB")
                pil_img.thumbnail((150, 150), Image.Resampling.LANCZOS)
                tk_img = ImageTk.PhotoImage(pil_img)
                w, h = pil_img.size
                img_canvas.config(width=w, height=h, bg="#ffffff")
                img_canvas.create_image(w // 2, h // 2, image=tk_img)
                self.image_keepalive[item["img_path"]] = tk_img
            except Exception as e:
                img_canvas.create_text(75, 75, text="[载入失败]", fill="#ff4d4d")
        else:
            img_canvas.create_text(75, 75, text="[无图]", fill="#888888")

        self.click_tracker[item["img_path"]] = None

        def on_click(event):
            if self.click_tracker[item["img_path"]] is not None:
                self.root.after_cancel(self.click_tracker[item["img_path"]])
            self.click_tracker[item["img_path"]] = self.root.after(
                250, lambda: self.show_large_preview(item, full_img_path))

        def on_double_click(event):
            if self.click_tracker[item["img_path"]] is not None:
                self.root.after_cancel(self.click_tracker[item["img_path"]])
                self.click_tracker[item["img_path"]] = None
            self.edit_prompt_dialog(item)

        img_canvas.bind("<Button-1>", on_click)
        img_canvas.bind("<Double-Button-1>", on_double_click)

        for w in (card, img_canvas):
            w.bind("<Button-3>", lambda e, txt=item["text"]: self.copy_to_clip(txt, "提示词"))
            w.bind("<Button-2>", lambda e, txt=item["text"]: self.copy_to_clip(txt, "提示词"))

    def show_large_preview(self, item, full_img_path):
        self.status_var.set(f"📜 提示词: {item['text']}")

        preview_win = tk.Toplevel(self.root)
        preview_win.title("🔍 查看大图与完整备注")
        preview_win.geometry("650x750")

        if os.path.exists(full_img_path):
            try:
                p_img = Image.open(full_img_path)
                p_img.thumbnail((600, 400), Image.Resampling.LANCZOS)
                tk_p_img = ImageTk.PhotoImage(p_img)
                img_lbl = tk.Label(preview_win, image=tk_p_img, bg="#fbfbfb")
                img_lbl.image = tk_p_img
                img_lbl.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
            except:
                tk.Label(preview_win, text="[大图加载失败]", fg="red").pack(pady=10)
        else:
            tk.Label(preview_win, text="[本地原图已丢失]", fg="gray").pack(pady=10)

        info_container = ttk.Frame(preview_win)
        info_container.pack(fill=tk.X, side=tk.BOTTOM, padx=15, pady=10)

        btn_box = tk.Frame(info_container)
        btn_box.pack(fill=tk.X, side=tk.BOTTOM, pady=5)
        ttk.Button(btn_box, text="📋 复制原始提示词",
                   command=lambda: self.copy_to_clip(item["text"], "提示词")).pack(side=tk.RIGHT)
        ttk.Button(btn_box, text="关闭预览", command=preview_win.destroy).pack(side=tk.LEFT)

        text_panel = tk.Text(info_container, height=10, font=("Microsoft YaHei", 9),
                             wrap=tk.WORD, bd=1, relief=tk.SOLID)
        text_panel.pack(fill=tk.X, expand=True)

        text_panel.insert(tk.END, "【原始提示词 (Prompt)】\n", "header")
        text_panel.insert(tk.END, f"{item['text']}\n\n")

        translation = item.get("translation", "").strip()
        if translation:
            text_panel.insert(tk.END, "【提示词中文翻译】\n", "header")
            text_panel.insert(tk.END, f"{translation}\n\n")

        notes = item.get("notes", [])
        if notes:
            text_panel.insert(tk.END, "【绑定的说明备注库】\n", "header")
            for i, note in enumerate(notes, 1):
                n_txt = note.get("text", "").strip()
                n_trans = note.get("translation", "").strip()
                if n_txt or n_trans:
                    text_panel.insert(tk.END, f" 📍 备注 {i} : {n_txt}\n")
                    if n_trans:
                        text_panel.insert(tk.END, f"     └─ 翻译 : {n_trans}\n")

        text_panel.tag_config("header", font=("Microsoft YaHei", 10, "bold"), foreground="#1976d2")
        text_panel.config(state=tk.DISABLED)

    def edit_prompt_dialog(self, item):
        self.edit_ctx = {"note_rows": [], "text_box": None, "trans_box": None}

        edit_win = tk.Toplevel(self.root)
        edit_win.title("📝 增强型词条编辑器")
        edit_win.geometry("680x650")
        edit_win.minsize(580, 450)

        edit_win.transient(self.root)
        edit_win.grab_set()

        btn_box = tk.Frame(edit_win, pady=12)
        btn_box.pack(fill=tk.X, side=tk.BOTTOM, padx=15)

        def save_edit():
            new_text = self.edit_ctx["text_box"].get("1.0", tk.END).strip()
            new_trans = self.edit_ctx["trans_box"].get("1.0", tk.END).strip()
            if not new_text:
                messagebox.showwarning("警告", "原始提示词不能为空！", parent=edit_win)
                return
            saved_notes = []
            for row in self.edit_ctx["note_rows"]:
                if row["frame"].winfo_exists():
                    nt = row["entry_note"].get().strip()
                    nt_tr = row["entry_trans"].get().strip()
                    if nt or nt_tr:
                        saved_notes.append({"text": nt, "translation": nt_tr})
            item["text"] = new_text
            item["translation"] = new_trans
            item["notes"] = saved_notes
            self.save_prompt_data_to_workspace()
            self.status_var.set("💾 数据全量保存成功！")
            edit_win.destroy()
            self.refresh_prompt_display_view()

        def translate_current_popup_fields():
            current_prompt = self.edit_ctx["text_box"].get("1.0", tk.END).strip()
            if not current_prompt:
                messagebox.showwarning("提示", "请输入原始英文提示词后再执行翻译", parent=edit_win)
                return
            try:
                edit_win.config(cursor="watch")
                edit_win.update_idletasks()
                popup_translator = GoogleTranslator(source='auto', target='zh-CN')
                translated_prompt = popup_translator.translate(current_prompt)
                self.edit_ctx["trans_box"].delete("1.0", tk.END)
                self.edit_ctx["trans_box"].insert(tk.END, translated_prompt)
                for row in self.edit_ctx["note_rows"]:
                    if row["frame"].winfo_exists():
                        nt = row["entry_note"].get().strip()
                        nt_tr = row["entry_trans"].get().strip()
                        if nt and not nt_tr:
                            row["entry_trans"].delete(0, tk.END)
                            row["entry_trans"].insert(0, popup_translator.translate(nt))
                self.status_var.set("⚡ 当前窗口词条快捷翻译成功！")
            except Exception as e:
                messagebox.showerror("翻译失败", f"局部翻译失败，请检查网络联通性: {e}", parent=edit_win)
            finally:
                edit_win.config(cursor="")

        btn_translate_curr = tk.Button(btn_box, text="🤖 翻译当前词条",
                                        font=("Microsoft YaHei", 10),
                                        bg="#00bcd4", fg="#ffffff",
                                        relief=tk.RAISED, padx=10,
                                        command=translate_current_popup_fields)
        btn_translate_curr.pack(side=tk.RIGHT, padx=5)

        btn_save = tk.Button(btn_box, text="💾 确认全量保存",
                             font=("Microsoft YaHei", 10, "bold"),
                             bg="#4caf50", fg="#ffffff",
                             relief=tk.RAISED, padx=15, command=save_edit)
        btn_save.pack(side=tk.RIGHT, padx=5)

        btn_cancel = ttk.Button(btn_box, text="放弃取消", command=edit_win.destroy)
        btn_cancel.pack(side=tk.RIGHT, padx=5)

        full_img_path = os.path.normpath(os.path.join(self.workspace_dir, item["img_path"]))
        btn_view = ttk.Button(btn_box, text="🔍 查看原图",
                              command=lambda: os.startfile(full_img_path) if os.path.exists(
                                  full_img_path) else messagebox.showerror("错误", "图片丢失", parent=edit_win))
        btn_view.pack(side=tk.LEFT, padx=2)

        btn_del = ttk.Button(btn_box, text="🗑️ 删除整张卡片",
                             command=lambda: [self.delete_prompt(item), edit_win.destroy()])
        btn_del.pack(side=tk.LEFT, padx=2)

        center_container = ttk.Frame(edit_win)
        center_container.pack(fill=tk.BOTH, expand=True, side=tk.TOP, padx=15, pady=5)

        canvas = tk.Canvas(center_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(center_container, orient="vertical", command=canvas.yview)
        scroll_inner_frame = ttk.Frame(canvas)

        scroll_inner_frame.bind("<Configure>",
                                lambda e: canvas.configure(scrollregion=(0, 0, e.width, e.height)))
        canvas_frame_id = canvas.create_window((0, 0), window=scroll_inner_frame, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_frame_id, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_inner_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        center_container.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_inner_mousewheel))
        center_container.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        lbl_p = ttk.Label(scroll_inner_frame, text="⚙️ 原始英文提示词 (Prompt):",
                          font=("Microsoft YaHei", 10, "bold"))
        lbl_p.pack(anchor=tk.W, pady=(5, 2))

        self.edit_ctx["text_box"] = tk.Text(scroll_inner_frame, font=("Consolas", 11),
                                            height=4, wrap=tk.WORD, bd=1, relief=tk.SOLID)
        self.edit_ctx["text_box"].pack(fill=tk.X, expand=True, pady=3)
        self.edit_ctx["text_box"].insert(tk.END, item.get("text", ""))
        self.bind_right_click_paste(self.edit_ctx["text_box"])

        lbl_t = ttk.Label(scroll_inner_frame, text="🇨🇳 提示词中文核心翻译:",
                          font=("Microsoft YaHei", 10, "bold"))
        lbl_t.pack(anchor=tk.W, pady=(8, 2))

        self.edit_ctx["trans_box"] = tk.Text(scroll_inner_frame, font=("Microsoft YaHei", 10),
                                             height=3, wrap=tk.WORD, bd=1, relief=tk.SOLID)
        self.edit_ctx["trans_box"].pack(fill=tk.X, expand=True, pady=3)
        self.edit_ctx["trans_box"].insert(tk.END, item.get("translation", ""))
        self.bind_right_click_paste(self.edit_ctx["trans_box"])

        notes_header_frame = ttk.Frame(scroll_inner_frame, padding=5)
        notes_header_frame.pack(fill=tk.X, pady=(5, 0))

        lbl_n = ttk.Label(notes_header_frame, text="📌 深度备注及衍生词翻译库",
                          font=("Microsoft YaHei", 10, "bold"), foreground="#e65100")
        lbl_n.pack(side=tk.LEFT)

        dynamic_notes_box = ttk.Frame(scroll_inner_frame)
        dynamic_notes_box.pack(fill=tk.X, pady=2)

        def add_single_note_row(initial_text="", initial_trans=""):
            row_f = ttk.Frame(dynamic_notes_box, padding=2)
            row_f.pack(fill=tk.X, pady=2)
            row_f.columnconfigure(1, weight=5)
            row_f.columnconfigure(3, weight=5)

            lbl1 = ttk.Label(row_f, text="备注:")
            lbl1.grid(row=0, column=0, padx=4, sticky="w")

            e1 = ttk.Entry(row_f, font=("Microsoft YaHei", 10))
            e1.insert(0, initial_text)
            e1.grid(row=0, column=1, padx=4, sticky="ew")
            self.bind_right_click_paste(e1)

            lbl2 = ttk.Label(row_f, text="翻译:")
            lbl2.grid(row=0, column=2, padx=4, sticky="w")

            e2 = ttk.Entry(row_f, font=("Microsoft YaHei", 10))
            e2.insert(0, initial_trans)
            e2.grid(row=0, column=3, padx=4, sticky="ew")
            self.bind_right_click_paste(e2)

            row_info = {"frame": row_f, "entry_note": e1, "entry_trans": e2}

            def remove_this_row():
                row_f.destroy()
                if row_info in self.edit_ctx["note_rows"]:
                    self.edit_ctx["note_rows"].remove(row_info)

            btn_del_row = ttk.Button(row_f, text="➖", width=3, command=remove_this_row)
            btn_del_row.grid(row=0, column=4, padx=4)
            self.edit_ctx["note_rows"].append(row_info)

        btn_add_note = ttk.Button(notes_header_frame, text=" ➕ 添加一条新备注 ",
                                  command=lambda: add_single_note_row("", ""))
        btn_add_note.pack(side=tk.RIGHT, padx=5)

        existing_notes = item.get("notes", [])
        if existing_notes:
            for note in existing_notes:
                add_single_note_row(note.get("text", ""), note.get("translation", ""))
        else:
            add_single_note_row("", "")

        edit_win.update_idletasks()
        self.edit_ctx["text_box"].focus_set()

    def start_global_translation(self):
        threading.Thread(target=self.translate_all_prompts_and_notes, daemon=True).start()

    def translate_all_prompts_and_notes(self):
        self.root.after(0, lambda: [
            self.status_var.set("⏳ 正在智能翻译所有小库中的提示词与备注，请稍候..."),
            self.root.config(cursor="watch")
        ])
        try:
            translator = GoogleTranslator(source='auto', target='zh-CN')
            translated_count = 0
            for bank_name, items in self.prompt_bank.items():
                for item in items:
                    if item.get("text"):
                        try:
                            item["translation"] = translator.translate(item["text"])
                            translated_count += 1
                        except Exception as e:
                            print(f"核心词条翻译异常: {e}")
                    if "notes" in item and isinstance(item["notes"], list):
                        for note in item["notes"]:
                            if note.get("text"):
                                try:
                                    note["translation"] = translator.translate(note["text"])
                                    translated_count += 1
                                except Exception as e:
                                    print(f"历史备注翻译异常: {e}")
            self.save_prompt_data_to_workspace()
            self.root.after(0, lambda: self.update_ui_after_translation(translated_count))
        except Exception as e:
            self.root.after(0, lambda: [
                self.root.config(cursor=""),
                self.status_var.set("❌ 全量翻译失败，请检查网络连接。"),
                messagebox.showerror("翻译出错", f"全局翻译遭遇异常: {e}",
                                     parent=self.root)
            ])

    def update_ui_after_translation(self, count):
        self.root.config(cursor="")
        self.refresh_prompt_display_view()
        self.status_var.set(f"💾 智能翻译完毕！共自动化处理并覆盖保存了 {count} 条文本数据。")
        messagebox.showinfo("成功",
                            f"一键全量翻译完成！\n已自动更新并全量同步保存了 {count} 条提示词/备注信息。",
                            parent=self.root)

    def delete_prompt(self, item):
        if item in self.prompt_bank[self.current_sub_bank]:
            self.prompt_bank[self.current_sub_bank].remove(item)
            if item["img_path"] in self.image_keepalive:
                del self.image_keepalive[item["img_path"]]
            full_img_path = os.path.normpath(os.path.join(self.workspace_dir, item["img_path"]))
            if os.path.exists(full_img_path):
                try:
                    os.remove(full_img_path)
                except:
                    pass
            self.save_prompt_data_to_workspace()
            self.refresh_prompt_display_view()

    def copy_to_clip(self, text, type_str):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set(f" 📋 已成功复制")

    def save_prompt_data_to_workspace(self):
        file = os.path.join(self.workspace_dir, "saved_prompts.json")
        with open(file, "w", encoding="utf-8") as f:
            json.dump(self.prompt_bank, f, indent=4)

    def load_all_data_from_workspace(self):
        prompt_file = os.path.join(self.workspace_dir, "saved_prompts.json")
        if os.path.exists(prompt_file):
            try:
                with open(prompt_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.prompt_bank = data
                        if "默认提示词库" not in self.prompt_bank:
                            self.prompt_bank["默认提示词库"] = []
                    else:
                        self.prompt_bank = {"默认提示词库": data}
            except:
                self.prompt_bank = {"默认提示词库": []}
        else:
            self.prompt_bank = {"默认提示词库": []}

        first_key = list(self.prompt_bank.keys())[0]
        self.switch_to_sub_bank(first_key)

    # ================== TAB 2: 数据集标注 ==================
    def setup_tagger_tab(self):
        config_frame = ttk.LabelFrame(self.tab_tagger, text=" ⚙️ 标注配置 ", padding=8)
        config_frame.pack(fill=tk.X, pady=5)

        row1 = ttk.Frame(config_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="标注模型:").pack(side=tk.LEFT, padx=2)
        self.tagger_model_var = tk.StringVar(value="wd-vit-v3")
        self.tagger_model_combo = ttk.Combobox(row1, textvariable=self.tagger_model_var,
                                                state="readonly", width=25,
                                                values=[
                                                    "wd-vit-v3", "wd-convnext-v3", "wd-swinv2-v3",
                                                    "wd-eva02-large-tagger-v3", "wd-vit-large-tagger-v3",
                                                    "wd14-vit-v2", "wd14-convnextv2-v2",
                                                    "wd14-swinv2-v2", "wd14-moat-v2",
                                                    "cl_tagger_1_01"
                                                ])
        self.tagger_model_combo.pack(side=tk.LEFT, padx=5)

        ttk.Label(row1, text="通用阈值:").pack(side=tk.LEFT, padx=(15, 2))
        self.tagger_threshold_var = tk.DoubleVar(value=0.35)
        ttk.Scale(row1, from_=0.1, to=0.9, variable=self.tagger_threshold_var,
                  orient=tk.HORIZONTAL, length=120).pack(side=tk.LEFT, padx=2)
        self.tagger_threshold_lbl = ttk.Label(row1, text="0.35", width=4)
        self.tagger_threshold_lbl.pack(side=tk.LEFT)
        self.tagger_threshold_var.trace_add('write',
                                            lambda *a: self.tagger_threshold_lbl.config(
                                                text=f"{self.tagger_threshold_var.get():.2f}"))

        ttk.Label(row1, text="角色阈值:").pack(side=tk.LEFT, padx=(10, 2))
        self.tagger_char_threshold_var = tk.DoubleVar(value=0.6)
        ttk.Scale(row1, from_=0.1, to=0.9, variable=self.tagger_char_threshold_var,
                  orient=tk.HORIZONTAL, length=120).pack(side=tk.LEFT, padx=2)
        self.tagger_char_threshold_lbl = ttk.Label(row1, text="0.60", width=4)
        self.tagger_char_threshold_lbl.pack(side=tk.LEFT)
        self.tagger_char_threshold_var.trace_add('write',
                                                 lambda *a: self.tagger_char_threshold_lbl.config(
                                                     text=f"{self.tagger_char_threshold_var.get():.2f}"))

        row2 = ttk.Frame(config_frame)
        row2.pack(fill=tk.X, pady=2)
        self.tagger_replace_underscore_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="下划线转空格",
                        variable=self.tagger_replace_underscore_var).pack(side=tk.LEFT, padx=5)
        self.tagger_sort_alpha_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="字母排序",
                        variable=self.tagger_sort_alpha_var).pack(side=tk.LEFT, padx=5)
        self.tagger_add_rating_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="添加分级标签",
                        variable=self.tagger_add_rating_var).pack(side=tk.LEFT, padx=5)

        row3 = ttk.Frame(config_frame)
        row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="附加标签:").pack(side=tk.LEFT, padx=2)
        self.tagger_additional_entry = ttk.Entry(row3, width=25)
        self.tagger_additional_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(row3, text="排除标签:").pack(side=tk.LEFT, padx=(15, 2))
        self.tagger_exclude_entry = ttk.Entry(row3, width=25)
        self.tagger_exclude_entry.pack(side=tk.LEFT, padx=5)

        action_frame = ttk.LabelFrame(self.tab_tagger, text=" 🖼️ 输入路径与操作 ", padding=8)
        action_frame.pack(fill=tk.X, pady=5)

        row4 = ttk.Frame(action_frame)
        row4.pack(fill=tk.X, pady=2)
        ttk.Label(row4, text="图片文件夹:").pack(side=tk.LEFT, padx=2)
        self.tagger_dir_var = tk.StringVar()
        self.tagger_dir_entry = ttk.Entry(row4, textvariable=self.tagger_dir_var, width=40)
        self.tagger_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(row4, text="浏览...", command=self._select_tagger_dir).pack(side=tk.LEFT, padx=2)

        row5 = ttk.Frame(action_frame)
        row5.pack(fill=tk.X, pady=2)
        self.tagger_recursive_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row5, text="递归搜索子文件夹",
                        variable=self.tagger_recursive_var).pack(side=tk.LEFT, padx=5)

        self.tagger_start_btn = ttk.Button(row5, text="▶ 开始标注",
                                           command=self._start_tagging)
        self.tagger_start_btn.pack(side=tk.RIGHT, padx=10)

        self.tagger_stop_btn = ttk.Button(row5, text="⏹ 取消",
                                          command=self._cancel_tagging, state=tk.DISABLED)
        self.tagger_stop_btn.pack(side=tk.RIGHT, padx=5)

        progress_frame = ttk.Frame(self.tab_tagger)
        progress_frame.pack(fill=tk.X, pady=5)
        self.tagger_progress_var = tk.DoubleVar()
        self.tagger_progress_bar = ttk.Progressbar(progress_frame, variable=self.tagger_progress_var,
                                                   maximum=100, mode='determinate')
        self.tagger_progress_bar.pack(fill=tk.X, padx=5)

        log_frame = ttk.LabelFrame(self.tab_tagger, text=" 📋 运行日志 ", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.tagger_log_text = tk.Text(log_frame, font=("Consolas", 9), height=10,
                                       wrap=tk.WORD, bg="#1e1e1e", fg="#d4d4d4",
                                       bd=0, state=tk.DISABLED)
        self.tagger_log_text.pack(fill=tk.BOTH, expand=True)

    def _select_tagger_dir(self):
        d = filedialog.askdirectory(title="选择包含图片的文件夹")
        if d:
            self.tagger_dir_var.set(os.path.normpath(d))

    def _tagger_log(self, msg):
        self.root.after(0, lambda: self._tagger_log_impl(msg))

    def _tagger_log_impl(self, msg):
        self.tagger_log_text.config(state=tk.NORMAL)
        self.tagger_log_text.insert(tk.END, msg + "\n")
        self.tagger_log_text.see(tk.END)
        self.tagger_log_text.config(state=tk.DISABLED)

    def _cancel_tagging(self):
        self._tagger_cancelled = True
        self._tagger_log("⚠ 正在取消...")

    def _start_tagging(self):
        image_dir = self.tagger_dir_var.get().strip()
        if not image_dir:
            messagebox.showwarning("警告", "请先选择图片文件夹！")
            return
        if not os.path.isdir(image_dir):
            messagebox.showerror("错误", "图片文件夹路径无效！")
            return

        from tagger.interrogator import check_dependencies
        missing = check_dependencies()
        if missing:
            messagebox.showerror(
                "缺少依赖",
                "数据集标注功能需要以下 Python 包，请先安装：\n\n"
                f"pip install {' '.join(missing)}\n\n"
                f"缺失: {', '.join(missing)}"
            )
            return

        self.tagger_start_btn.config(state=tk.DISABLED)
        self.tagger_stop_btn.config(state=tk.NORMAL)
        self.tagger_progress_var.set(0)
        self.tagger_log_text.config(state=tk.NORMAL)
        self.tagger_log_text.delete("1.0", tk.END)
        self.tagger_log_text.config(state=tk.DISABLED)
        self._tagger_cancelled = False

        model_key = self.tagger_model_var.get()
        threshold = self.tagger_threshold_var.get()
        char_threshold = self.tagger_char_threshold_var.get()
        replace_underscore = self.tagger_replace_underscore_var.get()
        sort_alpha = self.tagger_sort_alpha_var.get()
        add_rating = self.tagger_add_rating_var.get()
        additional_tags = self.tagger_additional_entry.get()
        exclude_tags = self.tagger_exclude_entry.get()
        recursive = self.tagger_recursive_var.get()

        models_dir = os.path.join(BASE_DIR, "models")

        threading.Thread(target=self._run_tagging,
                         args=(image_dir, model_key, threshold, char_threshold,
                               replace_underscore, sort_alpha, add_rating,
                               additional_tags, exclude_tags, recursive, models_dir),
                         daemon=True).start()

    def _run_tagging(self, image_dir, model_key, threshold, char_threshold,
                     replace_underscore, sort_alpha, add_rating,
                     additional_tags, exclude_tags, recursive, models_dir):
        from tagger.interrogator import create_interrogators, run_interrogate

        self._tagger_log("正在初始化标注器...")

        try:
            interrogators = create_interrogators(cache_dir=models_dir)
            if model_key not in interrogators:
                self._tagger_log(f"未知模型: {model_key}")
                self._reset_tagger_ui()
                return
            interrogator = interrogators[model_key]
            self._tagger_log(f"加载模型 {model_key}，优先使用 GPU...")
            interrogator.load()
            provider = interrogator.model.get_providers()[0]
            self._tagger_log(f"推理引擎: {provider}")

            def log_cb(msg):
                self._tagger_log(msg)

            def progress_cb(current, total):
                pct = int(current / total * 100) if total > 0 else 0
                self.root.after(0, lambda: self.tagger_progress_var.set(pct))
                self.root.after(0, lambda: self.status_var.set(
                    f"🏷️ 标注进度: {current}/{total}"))

            def cancel_cb():
                return self._tagger_cancelled

            run_interrogate(
                image_dir=image_dir,
                recursive=recursive,
                interrogator=interrogator,
                threshold=threshold,
                character_threshold=char_threshold,
                add_rating_tag=add_rating,
                add_model_tag=False,
                additional_tags=additional_tags,
                exclude_tags=exclude_tags,
                sort_by_alphabetical_order=sort_alpha,
                add_confident_as_weight=False,
                replace_underscore=replace_underscore,
                escape_tag=False,
                progress_callback=progress_cb,
                log_callback=log_cb,
                cancel_check=cancel_cb,
            )

        except ImportError as e:
            self._tagger_log(f"缺少依赖库，请先安装: pip install numpy pandas onnxruntime huggingface_hub")
            self._tagger_log(f"错误: {e}")
        except Exception as e:
            self._tagger_log(f"标注异常: {e}")
            import traceback
            self._tagger_log(traceback.format_exc())
        finally:
            self._reset_tagger_ui()

    def _reset_tagger_ui(self):
        self.root.after(0, lambda: [
            self.tagger_start_btn.config(state=tk.NORMAL),
            self.tagger_stop_btn.config(state=tk.DISABLED),
            self.status_var.set("就绪")
        ])

    # ================== TAB 3: 标签编辑器 ==================
    def setup_editor_tab(self):
        toolbar = ttk.LabelFrame(self.tab_editor, text=" 🔧 数据集操作 ", padding=5)
        toolbar.pack(fill=tk.X, pady=5)

        row1 = ttk.Frame(toolbar)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="数据文件夹:").pack(side=tk.LEFT, padx=2)
        self.editor_dir_var = tk.StringVar()
        self.editor_dir_entry = ttk.Entry(row1, textvariable=self.editor_dir_var, width=35)
        self.editor_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(row1, text="打开文件夹", command=self._open_editor_dataset).pack(side=tk.LEFT, padx=2)

        ttk.Label(row1, text="分隔符:").pack(side=tk.LEFT, padx=(10, 2))
        self.editor_sep_var = tk.StringVar(value=", ")
        self.editor_sep_entry = ttk.Entry(row1, textvariable=self.editor_sep_var, width=6)
        self.editor_sep_entry.pack(side=tk.LEFT, padx=2)

        self.editor_save_btn = tk.Button(row1, text="💾 保存所有修改", font=("Microsoft YaHei", 9, "bold"),
                                          bg="#4caf50", fg="#ffffff", relief=tk.RAISED, padx=8,
                                          command=self._editor_save_all)
        self.editor_save_btn.pack(side=tk.RIGHT, padx=5)

        self.editor_modified_lbl = ttk.Label(row1, text="", foreground="#e65100")
        self.editor_modified_lbl.pack(side=tk.RIGHT, padx=2)

        row2 = ttk.Frame(toolbar)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="搜索过滤:").pack(side=tk.LEFT, padx=2)
        self.editor_search_var = tk.StringVar()
        self.editor_search_entry = ttk.Entry(row2, textvariable=self.editor_search_var, width=20)
        self.editor_search_entry.pack(side=tk.LEFT, padx=5)
        self.editor_search_entry.bind("<KeyRelease>", lambda e: self.root.after_idle(self._editor_on_search))

        ttk.Label(row2, text="替换:").pack(side=tk.LEFT, padx=(10, 2))
        self.editor_replace_from_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.editor_replace_from_var, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Label(row2, text="→").pack(side=tk.LEFT)
        self.editor_replace_to_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.editor_replace_to_var, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(row2, text="全部替换", command=self._editor_replace_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(row2, text="去重", command=self._editor_deduplicate).pack(side=tk.LEFT, padx=5)

        self.editor_main_paned = ttk.PanedWindow(self.tab_editor, orient=tk.HORIZONTAL)
        self.editor_main_paned.pack(fill=tk.BOTH, expand=True, pady=5)

        # COLUMN 1: image grid
        left_frame = ttk.LabelFrame(self.editor_main_paned, text=" 🖼️ 图片列表 ", padding=3)
        self.editor_main_paned.add(left_frame, weight=2)

        self.editor_canvas = tk.Canvas(left_frame, highlightthickness=0)
        img_scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=self.editor_canvas.yview)
        self.editor_image_grid_frame = ttk.Frame(self.editor_canvas)
        self.editor_image_grid_frame.bind("<Configure>",
                                           lambda e: self.editor_canvas.configure(scrollregion=self.editor_canvas.bbox("all")))
        self.editor_canvas.create_window((0, 0), window=self.editor_image_grid_frame, anchor="nw")
        self.editor_canvas.configure(yscrollcommand=img_scrollbar.set)
        self.editor_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        img_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        _ec = self.editor_canvas
        self._editor_grid_refresh_id = None

        def _emw(event):
            _ec.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.editor_canvas.bind("<Enter>", lambda e: _ec.bind_all("<MouseWheel>", _emw))
        self.editor_canvas.bind("<Leave>", lambda e: _ec.unbind_all("<MouseWheel>"))
        self.editor_canvas.bind("<Configure>", lambda e: self._debounced_refresh_grid())

        # COLUMN 2: current image tags
        mid_frame = ttk.LabelFrame(self.editor_main_paned, text=" 📝 当前图片标签 ", padding=3)
        self.editor_main_paned.add(mid_frame, weight=3)

        mid_top = ttk.Frame(mid_frame)
        mid_top.pack(fill=tk.X, pady=2)
        self.editor_mid_add_entry = ttk.Entry(mid_top, width=16)
        self.editor_mid_add_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.editor_mid_add_entry.bind("<Return>", lambda e: self._add_tag_to_current())
        ttk.Button(mid_top, text="插入", command=self._add_tag_to_current).pack(side=tk.LEFT, padx=2)
        ttk.Button(mid_top, text="🗑 删除选中", command=self._delete_tag_from_current).pack(side=tk.LEFT, padx=2)

        self.editor_mid_tree = ttk.Treeview(mid_frame, columns=('tag', 'count', 'trans'),
                                            show='headings', selectmode='browse')
        self.editor_mid_tree.heading('tag', text='标签名')
        self.editor_mid_tree.heading('count', text='次数')
        self.editor_mid_tree.heading('trans', text='中文翻译')
        self.editor_mid_tree.column('tag', width=120, minwidth=80)
        self.editor_mid_tree.column('count', width=60, anchor='center')
        self.editor_mid_tree.column('trans', width=200, minwidth=100)
        mid_tree_scroll = ttk.Scrollbar(mid_frame, orient='vertical', command=self.editor_mid_tree.yview)
        self.editor_mid_tree.configure(yscrollcommand=mid_tree_scroll.set)
        self.editor_mid_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        mid_tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.editor_mid_tree.bind('<<TreeviewSelect>>', lambda e: self._on_mid_tag_selected())

        # COLUMN 3: all tag counts
        right_frame = ttk.LabelFrame(self.editor_main_paned, text=" 📊 全部标签计数 ", padding=3)
        self.editor_main_paned.add(right_frame, weight=3)

        right_top = ttk.Frame(right_frame)
        right_top.pack(fill=tk.X, pady=2)
        self.editor_right_add_entry = ttk.Entry(right_top, width=16)
        self.editor_right_add_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.editor_right_add_entry.bind("<Return>", lambda e: self._add_tag_to_all())
        ttk.Button(right_top, text="插入全部", command=self._add_tag_to_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(right_top, text="🗑 全部删除", command=self._delete_tag_from_all).pack(side=tk.LEFT, padx=2)

        self.editor_right_tree = ttk.Treeview(right_frame, columns=('tag', 'count', 'trans'),
                                              show='headings', selectmode='browse')
        self.editor_right_tree.heading('tag', text='标签名')
        self.editor_right_tree.heading('count', text='次数')
        self.editor_right_tree.heading('trans', text='中文翻译')
        self.editor_right_tree.column('tag', width=120, minwidth=80)
        self.editor_right_tree.column('count', width=60, anchor='center')
        self.editor_right_tree.column('trans', width=200, minwidth=100)
        right_tree_scroll = ttk.Scrollbar(right_frame, orient='vertical', command=self.editor_right_tree.yview)
        self.editor_right_tree.configure(yscrollcommand=right_tree_scroll.set)
        self.editor_right_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right_tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.editor_right_tree.bind('<<TreeviewSelect>>', lambda e: self._on_right_tag_selected())

        self._editor_selected_item = None
        self._editor_selected_mid_tag = None
        self._editor_selected_right_tag = None
        self._editor_modified = False
        self._editor_original = {}
        self._editor_counts_cache = None

    def _mark_modified(self, item, original_tags):
        key = item['img_path']
        if original_tags is not None:
            self._editor_original[key] = original_tags
        self._editor_modified = True
        n = len(self._editor_original)
        self.editor_modified_lbl.config(text=f"⚠ 未保存 {n} 项" if n else "")
        self.editor_save_btn.config(bg="#ff9800")

    def _editor_save_all(self):
        if not self._editor_modified:
            return
        saved = 0
        for img_path, original in list(self._editor_original.items()):
            item = self._editor_dataset.get(img_path)
            if item and item['tags'] != original:
                try:
                    with open(item['txt_path'], 'w', encoding='utf-8') as f:
                        f.write(item['tags'])
                    saved += 1
                except:
                    pass
        self._editor_original.clear()
        self._editor_modified = False
        self._editor_counts_cache = None
        self.editor_modified_lbl.config(text="")
        self.editor_save_btn.config(bg="#4caf50")
        self._refresh_editor_all()
        self.status_var.set(f"💾 已保存 {saved} 个文件")

    def _debounced_refresh_grid(self):
        if self._editor_grid_refresh_id:
            self.root.after_cancel(self._editor_grid_refresh_id)
        self._editor_grid_refresh_id = self.root.after(150, self._refresh_image_grid)

    def _parse_tags(self, tags_str):
        sep = self.editor_sep_var.get().strip()
        return [t.strip() for t in tags_str.split(sep) if t.strip()]

    def _get_all_tag_counts(self):
        if self._editor_counts_cache is not None:
            return self._editor_counts_cache
        counts = {}
        for item in self._editor_dataset.values():
            for tag in self._parse_tags(item['tags']):
                tl = tag.lower()
                if tl not in counts:
                    counts[tl] = {'tag': tag, 'count': 0}
                counts[tl]['count'] += 1
        self._editor_counts_cache = sorted(
            counts.values(), key=lambda x: (-x['count'], x['tag'].lower()))
        return self._editor_counts_cache

    def _open_editor_dataset(self):
        d = filedialog.askdirectory(title="选择数据集文件夹（含图片和.txt文件）")
        if not d:
            return
        self.editor_dir_var.set(os.path.normpath(d))
        self._load_editor_dataset(d)

    def _load_editor_dataset(self, dir_path):
        self._editor_dataset = {}
        self._editor_image_keepalive = {}
        self._editor_selected_item = None
        self._editor_selected_mid_tag = None
        self._editor_selected_right_tag = None
        self._editor_modified = False
        self._editor_original = {}
        self._editor_counts_cache = None
        self.editor_modified_lbl.config(text="")
        self.editor_save_btn.config(bg="#4caf50")
        supported_exts = set(Image.registered_extensions().keys())

        for fname in sorted(os.listdir(dir_path)):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in supported_exts:
                continue
            path = os.path.join(dir_path, fname)
            if not os.path.isfile(path):
                continue
            txt_path = os.path.splitext(path)[0] + '.txt'
            tags = ''
            if os.path.exists(txt_path):
                try:
                    with open(txt_path, 'r', encoding='utf-8') as f:
                        tags = f.read().strip()
                except:
                    pass
            item = {
                'img_path': path,
                'txt_path': txt_path,
                'tags': tags,
                'name': fname,
            }
            self._editor_dataset[path] = item

        self._refresh_editor_all()
        self.status_var.set(f"📂 加载完成：{len(self._editor_dataset)} 张图片")

    def _refresh_editor_all(self):
        self._refresh_image_grid()
        self._refresh_current_tags()
        self._refresh_all_tags()

    def _refresh_image_grid(self, event=None):
        for child in self.editor_image_grid_frame.winfo_children():
            child.destroy()
        self._editor_image_keepalive.clear()

        search_text = self.editor_search_entry.get().strip().lower()
        canvas_width = self.editor_canvas.winfo_width()
        if canvas_width < 10:
            canvas_width = 700
        card_width = 130
        columns = max(1, canvas_width // card_width)

        idx = 0
        for path, item in sorted(self._editor_dataset.items()):
            if search_text:
                name_lower = item['name'].lower()
                tags_lower = item['tags'].lower()
                if search_text not in name_lower and search_text not in tags_lower:
                    continue
            r = idx // columns
            c = idx % columns
            self._create_editor_image_card(item, r, c)
            idx += 1

    def _create_editor_image_card(self, item, row, col):
        is_selected = (self._editor_selected_item is not None and
                       self._editor_selected_item['img_path'] == item['img_path'])
        bg_color = "#d0e8ff" if is_selected else "#ffffff"
        bd_width = 2 if is_selected else 1

        card = tk.Frame(self.editor_image_grid_frame, bg=bg_color, bd=bd_width,
                        relief=tk.RIDGE, padx=2, pady=2)
        card.grid(row=row, column=col, padx=2, pady=2, sticky="nsew")

        name_lbl = tk.Label(card, text=item['name'][:18], bg=bg_color,
                            font=("Microsoft YaHei", 7), anchor=tk.W)
        name_lbl.pack(fill=tk.X, padx=1)

        img_path = item['img_path']
        try:
            pil_img = Image.open(img_path)
            if pil_img.mode not in ("RGB", "RGBA"):
                pil_img = pil_img.convert("RGB")
            pil_img.thumbnail((110, 110), Image.Resampling.LANCZOS)
            tk_img = ImageTk.PhotoImage(pil_img)
            w, h = pil_img.size
            img_canvas = tk.Canvas(card, width=w, height=h, bg="#f5f5f5",
                                   highlightthickness=0, cursor="hand2")
            img_canvas.create_image(w // 2, h // 2, image=tk_img)
            self._editor_image_keepalive[img_path] = tk_img
        except:
            img_canvas = tk.Canvas(card, width=100, height=80, bg="#f5f5f5",
                                   highlightthickness=0, cursor="hand2")
            img_canvas.create_text(50, 40, text="[加载失败]", fill="#ff4d4d", font=("Microsoft YaHei", 7))
        img_canvas.pack(fill=tk.BOTH, expand=True, pady=1)

        for w in (card, img_canvas, name_lbl):
            w.bind("<Button-1>", lambda e, it=item: self._on_image_select(it))

    def _on_image_select(self, item):
        self._editor_selected_item = item
        self._editor_selected_mid_tag = None
        self._refresh_image_grid()
        self._refresh_current_tags()
        self.status_var.set(f"📷 选中: {item['name']}")

    def _trans(self, tag):
        if self._translations:
            return self._translations.get(tag, '')
        return ''

    def _editor_on_search(self):
        self._refresh_image_grid()
        self._refresh_current_tags()
        self._refresh_all_tags()

    def _refresh_current_tags(self):
        tree = self.editor_mid_tree
        tree.delete(*tree.get_children())
        if not self._editor_selected_item:
            return
        search_text = self.editor_search_entry.get().strip().lower()
        tags = self._parse_tags(self._editor_selected_item['tags'])
        for tag in tags:
            if search_text and search_text not in tag.lower():
                continue
            trans = self._trans(tag) or '—'
            tree.insert('', 'end', values=(tag, '1次', trans))

    def _refresh_all_tags(self):
        tree = self.editor_right_tree
        tree.delete(*tree.get_children())
        search_text = self.editor_search_entry.get().strip().lower()
        counts = self._get_all_tag_counts()
        for c in counts:
            tag = c['tag']
            if search_text and search_text not in tag.lower():
                continue
            trans = self._trans(tag) or '—'
            tree.insert('', 'end', values=(tag, f"{c['count']}次", trans))

    def _on_mid_tag_selected(self):
        sel = self.editor_mid_tree.selection()
        if sel:
            self._editor_selected_mid_tag = self.editor_mid_tree.item(sel[0], 'values')[0]

    def _on_right_tag_selected(self):
        sel = self.editor_right_tree.selection()
        if sel:
            self._editor_selected_right_tag = self.editor_right_tree.item(sel[0], 'values')[0]

    def _delete_tag_from_current(self):
        tag = self._editor_selected_mid_tag
        if not tag or not self._editor_selected_item:
            messagebox.showwarning("提示", "请先在标签列表中选中一个标签")
            return
        item = self._editor_selected_item
        sep = self.editor_sep_var.get().strip()
        original = item['tags']
        tags = self._parse_tags(item['tags'])
        tag_lower = tag.lower()
        new_tags = []
        found = False
        for t in tags:
            if not found and t.lower() == tag_lower:
                found = True
                continue
            new_tags.append(t)
        if found:
            item['tags'] = sep.join(new_tags)
            self._mark_modified(item, original)
        self._editor_selected_mid_tag = None
        self._editor_counts_cache = None
        self._refresh_current_tags()
        self._refresh_all_tags()
        self.status_var.set(f"🗑️ 已标记删除 [当前图片]: {tag} (请点击保存)")

    def _delete_tag_from_all(self):
        tag = self._editor_selected_right_tag
        if not tag or not self._editor_dataset:
            messagebox.showwarning("提示", "请先在全部标签列表中选中一个标签")
            return
        tag_lower = tag.lower()
        count = 0
        sep = self.editor_sep_var.get().strip()
        for item in self._editor_dataset.values():
            original = item['tags']
            tags = self._parse_tags(item['tags'])
            new_tags = []
            found = False
            for t in tags:
                if not found and t.lower() == tag_lower:
                    found = True
                    continue
                new_tags.append(t)
            if found:
                item['tags'] = sep.join(new_tags)
                self._mark_modified(item, original)
                count += 1
        self._editor_selected_right_tag = None
        self._editor_counts_cache = None
        self._refresh_current_tags()
        self._refresh_all_tags()
        self.status_var.set(f"🗑️ 已标记删除 [全部 {count} 张]: {tag} (请点击保存)")

    def _ask_insert_position(self, parent, n_tags):
        win = tk.Toplevel(parent)
        win.title("选择插入位置")
        win.geometry("320x150")
        win.transient(parent)
        win.grab_set()
        win.resizable(False, False)

        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        win.geometry(f"+{px + pw//2 - 160}+{py + ph//2 - 75}")

        ttk.Label(win, text=f"当前有 {n_tags} 个标签，1=最前, {n_tags+1}=末尾",
                  font=("Microsoft YaHei", 9)).pack(padx=15, pady=(15, 5))

        input_frame = ttk.Frame(win)
        input_frame.pack(pady=5)
        ttk.Label(input_frame, text="插入到第").pack(side=tk.LEFT)
        pos_var = tk.StringVar(value=str(n_tags + 1))
        pos_entry = ttk.Entry(input_frame, textvariable=pos_var, width=6, justify=tk.CENTER)
        pos_entry.pack(side=tk.LEFT, padx=6)
        ttk.Label(input_frame, text="个标签前面").pack(side=tk.LEFT)
        pos_entry.select_range(0, tk.END)
        pos_entry.focus_set()

        result = [None]

        def confirm():
            try:
                p = int(pos_var.get())
                if 1 <= p <= n_tags + 1:
                    result[0] = p
                    win.destroy()
            except ValueError:
                pass

        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="确定", command=confirm).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=win.destroy).pack(side=tk.LEFT, padx=5)
        pos_entry.bind("<Return>", lambda e: confirm())

        win.wait_window()
        return result[0]

    def _add_tag_to_current(self):
        if not self._editor_selected_item:
            messagebox.showwarning("提示", "请先在左侧选择一张图片")
            return
        new_tag = self.editor_mid_add_entry.get().strip()
        if not new_tag:
            return
        item = self._editor_selected_item
        original = item['tags']
        sep = self.editor_sep_var.get().strip()
        tags = self._parse_tags(item['tags'])
        pos = self._ask_insert_position(self.root, len(tags))
        if pos is None:
            return
        idx = max(0, min(pos - 1, len(tags)))
        tags.insert(idx, new_tag)
        item['tags'] = sep.join(tags)
        self._mark_modified(item, original)
        self.editor_mid_add_entry.delete(0, tk.END)
        self._editor_counts_cache = None
        self._refresh_current_tags()
        self._refresh_all_tags()
        self.status_var.set(f"➕ 已标记插入 [当前图片 第{pos}位]: {new_tag} (请点击保存)")

    def _add_tag_to_all(self):
        new_tag = self.editor_right_add_entry.get().strip()
        if not new_tag:
            return
        if not self._editor_dataset:
            messagebox.showwarning("提示", "请先打开数据集文件夹")
            return

        items_to_modify = []
        sep = self.editor_sep_var.get().strip()
        max_n = 0
        for item in self._editor_dataset.values():
            tags = self._parse_tags(item['tags'])
            if new_tag.lower() not in [t.lower() for t in tags]:
                items_to_modify.append(item)
                max_n = max(max_n, len(tags))

        if not items_to_modify:
            self.editor_right_add_entry.delete(0, tk.END)
            self.status_var.set("该标签已存在于所有图片中")
            return

        pos = self._ask_insert_position(self.root, max_n + 1)
        if pos is None:
            return
        idx = max(0, pos - 1)

        count = 0
        for item in items_to_modify:
            tags = self._parse_tags(item['tags'])
            original = item['tags']
            effective_idx = min(idx, len(tags))
            tags.insert(effective_idx, new_tag)
            item['tags'] = sep.join(tags)
            self._mark_modified(item, original)
            count += 1

        self.editor_right_add_entry.delete(0, tk.END)
        self._editor_counts_cache = None
        self._refresh_current_tags()
        self._refresh_all_tags()
        self.status_var.set(f"➕ 已标记插入 [全部 {count} 张 第{pos}位]: {new_tag} (请点击保存)")

    def _editor_replace_all(self):
        from_str = self.editor_replace_from_var.get().strip()
        to_str = self.editor_replace_to_var.get().strip()
        if not from_str:
            messagebox.showwarning("警告", "请输入要替换的内容")
            return
        if not messagebox.askyesno("确认",
                                    f"将所有标签文件中的 '{from_str}' 替换为 '{to_str}'？"):
            return
        count = 0
        for path, item in self._editor_dataset.items():
            if from_str in item['tags']:
                original = item['tags']
                item['tags'] = item['tags'].replace(from_str, to_str)
                self._mark_modified(item, original)
                count += 1
        self._editor_counts_cache = None
        self._refresh_editor_all()
        self.status_var.set(f"✅ 已标记替换 {count} 个文件 (请点击保存)")

    def _editor_deduplicate(self):
        if not messagebox.askyesno("确认", "去除所有标签文件中的重复标签？"):
            return
        sep = self.editor_sep_var.get().strip()
        count = 0
        for path, item in self._editor_dataset.items():
            tag_list = self._parse_tags(item['tags'])
            seen = set()
            unique = []
            changed = False
            for t in tag_list:
                if t.lower() not in seen:
                    seen.add(t.lower())
                    unique.append(t)
                else:
                    changed = True
            if changed:
                original = item['tags']
                item['tags'] = sep.join(unique)
                self._mark_modified(item, original)
                count += 1
        self._editor_counts_cache = None
        self._refresh_editor_all()
        self.status_var.set(f"✅ 已标记去重 {count} 个文件 (请点击保存)")


if __name__ == "__main__":
    root = tk.Tk()
    app = UltimatePaletteApp(root)
    root.mainloop()
