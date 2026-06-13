import tkinter as tk
from tkinter import ttk


class AutoCompleteEntry(ttk.Entry):
    def __init__(self, parent, tag_database=None, translations=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.tag_db = tag_database
        self.translations = translations or {}
        self.popup = None
        self.listbox = None
        self.bind('<KeyRelease>', self._on_keyrelease)
        self.bind('<FocusOut>', self._on_focusout)

    def set_tag_db(self, tag_db):
        self.tag_db = tag_db

    def set_translations(self, translations):
        self.translations = translations

    def _on_keyrelease(self, event):
        if event.keysym in ('Up', 'Down', 'Return', 'Escape', 'Tab', 'BackSpace', 'Delete'):
            if event.keysym == 'Down':
                self._focus_listbox()
            elif event.keysym == 'Escape':
                self._hide_popup()
            return
        self._show_suggestions()

    def _show_suggestions(self):
        text = self.get()
        cursor_pos = self.index(tk.INSERT)
        tag_start = text.rfind(',', 0, cursor_pos)
        if tag_start == -1:
            tag_start = 0
        else:
            tag_start += 1
        prefix = text[tag_start:cursor_pos].strip()

        if not prefix or not self.tag_db:
            self._hide_popup()
            return

        matches = self.tag_db.search_with_priority(prefix, 15)
        if not matches:
            self._hide_popup()
            return

        self._hide_popup()
        x = self.winfo_rootx() + self.winfo_width() // 2
        y = self.winfo_rooty() + self.winfo_height()

        self.popup = tk.Toplevel(self, bg='white', bd=0)
        self.popup.wm_overrideredirect(True)
        self.popup.wm_geometry(f'+{x}+{y}')

        frame = tk.Frame(self.popup, bg='white', bd=1, relief=tk.SOLID)
        frame.pack(fill=tk.BOTH, expand=True)

        self.listbox = tk.Listbox(frame, bg='white', fg='#333333',
                                  font=('Microsoft YaHei', 9),
                                  selectbackground='#0078d4',
                                  selectforeground='white',
                                  activestyle='none',
                                  bd=0, highlightthickness=0,
                                  width=40, height=min(len(matches), 12))
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(frame, orient='vertical')
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.listbox.yview)

        self._matches = matches
        self._prefix_start = tag_start
        self._prefix_end = cursor_pos
        self._prefix = prefix

        for tag in matches:
            display = self.tag_db.get_translation_text(tag, self.translations)
            self.listbox.insert(tk.END, display)

        self.listbox.bind('<ButtonRelease-1>', self._on_select)
        self.listbox.bind('<Return>', self._on_select)
        self.listbox.bind('<Escape>', lambda e: self._hide_popup())
        self.listbox.bind('<FocusOut>', lambda e: self._hide_popup())

    def _focus_listbox(self):
        if self.listbox and self.listbox.winfo_exists():
            self.listbox.focus_set()
            if self.listbox.size() > 0:
                self.listbox.selection_set(0)
                self.listbox.activate(0)

    def _on_select(self, event):
        if not self.listbox or not self.listbox.winfo_exists():
            return
        sel = self.listbox.curselection()
        if sel:
            idx = sel[0]
            tag = self._matches[idx]
            text = self.get()
            new_text = text[:self._prefix_start] + tag + ', ' + text[self._prefix_end:]
            self.delete(0, tk.END)
            self.insert(0, new_text)
            self.icursor(self._prefix_start + len(tag) + 2)
        self._hide_popup()

    def _hide_popup(self, event=None):
        if self.popup:
            self.popup.destroy()
            self.popup = None
            self.listbox = None

    def _on_focusout(self, event):
        self.after(200, self._delayed_hide)

    def _delayed_hide(self):
        if self.popup and self.listbox:
            focused = self.focus_get()
            if focused != self.listbox and focused != self:
                self._hide_popup()
