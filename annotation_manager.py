"""
annotation_manager.py
标注系统控制器：tag配置、交互绑定、底部备注栏、标注面板
新增：浮动工具条、悬停 Tooltip、面板搜索、撤销栈、右键改色
"""

import tkinter as tk
from tkinter import ttk, font as tkfont
import platform
from annotation_store import AnnotationStore
from theme import C, ANNOT_THEMES

IS_MAC  = platform.system() == 'Darwin'
MOD     = 'Command' if IS_MAC else 'Control'
MOD_KEY = 'Cmd'     if IS_MAC else 'Ctrl'

# ── 当前主题的标注样式（随主题切换更新） ─────────────────────────
ANNOT_STYLES: dict = dict(ANNOT_THEMES['dark'])

HOTKEYS = {
    f'<{MOD}-1>': 'hl_yellow',
    f'<{MOD}-2>': 'hl_green',
    f'<{MOD}-3>': 'hl_pink',
    f'<{MOD}-4>': 'hl_purple',
    f'<{MOD}-b>': 'bold',
    f'<{MOD}-u>': 'underline',
}

# 浮动工具条各类型顺序（高亮色 + 加粗 + 下划线）
TOOLBAR_TYPES = ['hl_yellow', 'hl_green', 'hl_pink', 'hl_purple', 'bold', 'underline']


class AnnotationManager:
    def __init__(self, app, text_widget, tag_store, note_bar_frame):
        self.app       = app
        self.text      = text_widget
        self.store     = AnnotationStore(tag_store)
        self._note_bar = note_bar_frame
        self._current_file  = None
        self._active_annot  = None

        # 底部备注栏
        self._note_bar_built = False

        # 右侧常驻面板
        self._panel_built      = False
        self._panel_canvas     = None
        self._panel_inner      = None
        self._filter_type      = 'all'
        self._filter_btns      = {}
        self._panel_search_var = None   # 面板搜索框

        # 浮动工具条
        self._toolbar_win   = None
        self._toolbar_after = None

        # 悬停 Tooltip
        self._tip_win   = None
        self._tip_after = None

        # 撤销栈（每项 {'action': 'add'|'remove', 'annot': dict, 'file': str}）
        self._undo_stack = []

    # ── 初始化 ─────────────────────────────────────────────────

    def setup(self):
        self._configure_tags()
        self._bind_events()
        self._build_note_bar()
        self._build_panel()

    def _configure_tags(self):
        for tag_name, style in ANNOT_STYLES.items():
            # 始终显式设置 background/foreground，空字符串会重置为默认值
            # 避免主题切换后旧颜色残留在 tag 上
            self.text.tag_configure(tag_name,
                                    background=style.get('bg', ''),
                                    foreground=style.get('fg', ''))
            if tag_name == 'bold':
                f = tkfont.Font(font=self.text['font'])
                f.config(weight='bold')
                self.text.tag_configure(tag_name, font=f)
            if tag_name == 'underline':
                self.text.tag_configure(tag_name, underline=True)
        try:
            self.text.tag_raise('search_match')
            self.text.tag_raise('search_current')
        except tk.TclError:
            pass

    def _bind_events(self):
        for key, annot_type in HOTKEYS.items():
            self.text.bind(key, lambda e, t=annot_type: self._annotate_selection(t))
        self.text.bind(f'<{MOD}-Delete>', self._remove_at_cursor)
        self.text.bind(f'<{MOD}-z>',     lambda e: self._undo_annotation() or 'break')

        # 鼠标释放：检测选区 → 弹出浮动工具条 或 检测点击批注
        self.text.bind('<ButtonRelease-1>', self._on_mouse_release)
        # 拖动时隐藏工具条
        self.text.bind('<B1-Motion>',      lambda e: self._hide_toolbar())
        # 悬停检测
        self.text.bind('<Motion>',         self._on_motion)
        self.text.bind('<Leave>',          lambda e: self._hide_tip())

    # ══════════════════════════════════════════════════════════
    # 浮动工具条
    # ══════════════════════════════════════════════════════════

    def _on_mouse_release(self, event):
        """鼠标释放：有选区→显示工具条；无选区→检测点击批注"""
        self.app.after(10, self._check_selection_or_click, event)

    def _check_selection_or_click(self, event):
        try:
            sel_first = self.text.index('sel.first')
            sel_last  = self.text.index('sel.last')
            if sel_first != sel_last:
                self._show_toolbar(sel_first, sel_last)
                return
        except tk.TclError:
            pass
        self._hide_toolbar()
        # 无选区时检测是否点击了批注
        if not self._current_file:
            return
        try:
            idx    = self.text.index(f'@{event.x},{event.y}')
            offset = self._get_char_offset(idx)
        except Exception:
            return
        annot = self._find_annotation_at(offset)
        if annot:
            self._show_note_bar(annot)

    def _show_toolbar(self, sel_first, sel_last):
        """在选区上方弹出浮动标注工具条"""
        self._hide_toolbar()
        if not self._current_file:
            return
        try:
            bbox = self.text.bbox(sel_last)
            if not bbox:
                bbox = self.text.bbox(sel_first)
            if not bbox:
                return
            bx, by, bw, bh = bbox
            rx = self.text.winfo_rootx() + bx
            ry = self.text.winfo_rooty() + by
        except Exception:
            return

        win = tk.Toplevel(self.app)
        win.overrideredirect(True)
        win.attributes('-topmost', True)
        win.configure(bg=C['bg_input'])

        frame = tk.Frame(win, bg=C['bg_input'], padx=6, pady=6,
                         relief=tk.FLAT, bd=0)
        frame.pack()

        # 添加圆角外框阴影感（用 bd + relief 模拟）
        win.configure(highlightbackground=C['border'], highlightthickness=1)

        def apply_type(t):
            self._annotate_selection(t)
            self._hide_toolbar()

        for atype in TOOLBAR_TYPES:
            style = ANNOT_STYLES.get(atype, {})
            dot   = style.get('dot', C['fg'])
            label = style.get('label', '')

            btn_frame = tk.Frame(frame, bg=C['bg_input'], cursor='hand2')
            btn_frame.pack(side=tk.LEFT, padx=4)

            if atype in ('bold', 'underline'):
                # 加粗/下划线用文字按钮
                txt  = 'B' if atype == 'bold' else 'U'
                font = ('PingFang SC', 13, 'bold') if atype == 'bold' else ('PingFang SC', 13)
                lbl  = tk.Label(btn_frame, text=txt, bg=C['bg_input'], fg=dot,
                                font=font, width=2, cursor='hand2')
                if atype == 'underline':
                    lbl.config(underline=0)
                lbl.pack()
            else:
                # 颜色用圆点 Canvas
                cv = tk.Canvas(btn_frame, width=20, height=20,
                               bg=C['bg_input'], highlightthickness=0, cursor='hand2')
                cv.create_oval(2, 2, 18, 18, fill=dot, outline='')
                cv.pack()
                lbl = cv

            # Hover 效果 + 点击
            def _enter(e, w=btn_frame):
                w.configure(bg=C['bg_sel_tag'])
                for ch in w.winfo_children():
                    try: ch.configure(bg=C['bg_sel_tag'])
                    except Exception: pass

            def _leave(e, w=btn_frame):
                w.configure(bg=C['bg_input'])
                for ch in w.winfo_children():
                    try: ch.configure(bg=C['bg_input'])
                    except Exception: pass

            btn_frame.bind('<Enter>', _enter)
            btn_frame.bind('<Leave>', _leave)
            btn_frame.bind('<Button-1>', lambda e, t=atype: apply_type(t))
            for ch in btn_frame.winfo_children():
                ch.bind('<Enter>', _enter)
                ch.bind('<Leave>', _leave)
                ch.bind('<Button-1>', lambda e, t=atype: apply_type(t))

        # 分隔线
        tk.Frame(frame, bg=C['border'], width=1).pack(side=tk.LEFT, fill=tk.Y, padx=4)

        # 删除按钮
        del_btn = tk.Frame(frame, bg=C['bg_input'], cursor='hand2')
        del_btn.pack(side=tk.LEFT, padx=4)
        del_lbl = tk.Label(del_btn, text="✕", bg=C['bg_input'], fg=C['btn_close'],
                           font=('PingFang SC', 11), cursor='hand2')
        del_lbl.pack()
        del_btn.bind('<Button-1>', lambda e: (self._remove_at_cursor(), self._hide_toolbar()))
        del_lbl.bind('<Button-1>', lambda e: (self._remove_at_cursor(), self._hide_toolbar()))

        # 定位：优先显示在选区上方，不够空间则显示在下方
        win.update_idletasks()
        tw = win.winfo_reqwidth()
        th = win.winfo_reqheight()
        tx = rx - tw // 2
        ty = ry - th - 8
        # 防止超出屏幕
        sw = win.winfo_screenwidth()
        tx = max(4, min(tx, sw - tw - 4))
        if ty < 4:
            ty = ry + bh + 8
        win.geometry(f'+{tx}+{ty}')

        self._toolbar_win = win

        # 点击 Toplevel 外部时关闭
        win.bind('<FocusOut>', lambda e: self._hide_toolbar())
        win.bind('<Escape>',   lambda e: self._hide_toolbar())

    def _hide_toolbar(self):
        if self._toolbar_win:
            try:
                self._toolbar_win.destroy()
            except Exception:
                pass
            self._toolbar_win = None

    # ══════════════════════════════════════════════════════════
    # 悬停 Tooltip（高亮文字上悬停显示备注预览）
    # ══════════════════════════════════════════════════════════

    def _on_motion(self, event):
        """鼠标在文本区移动时，检测是否悬停在批注上"""
        if self._tip_after:
            self.text.after_cancel(self._tip_after)
            self._tip_after = None
        try:
            idx    = self.text.index(f'@{event.x},{event.y}')
            offset = self._get_char_offset(idx)
        except Exception:
            self._hide_tip()
            return
        annot = self._find_annotation_at(offset)
        if annot and annot.get('note', '').strip():
            rx = event.x_root
            ry = event.y_root
            self._tip_after = self.text.after(
                500, lambda: self._show_tip(annot, rx, ry))
        else:
            self._hide_tip()

    def _show_tip(self, annot, rx, ry):
        """弹出备注预览气泡"""
        self._hide_tip()
        note = annot.get('note', '').strip()
        if not note:
            return
        style = ANNOT_STYLES.get(annot['type'], {})
        dot   = style.get('dot', C['accent'])

        win = tk.Toplevel(self.app)
        win.overrideredirect(True)
        win.attributes('-topmost', True)
        win.configure(bg=C['bg_input'],
                      highlightbackground=C['border'], highlightthickness=1)

        inner = tk.Frame(win, bg=C['bg_input'], padx=10, pady=8)
        inner.pack()

        # 颜色点 + 类型标签
        hdr = tk.Frame(inner, bg=C['bg_input'])
        hdr.pack(fill=tk.X, pady=(0, 4))
        cv = tk.Canvas(hdr, width=10, height=10, bg=C['bg_input'],
                       highlightthickness=0)
        cv.create_oval(1, 1, 9, 9, fill=dot, outline='')
        cv.pack(side=tk.LEFT)
        tk.Label(hdr, text=style.get('label', ''), bg=C['bg_input'],
                 fg=C['fg_dim2'], font=('PingFang SC', 10)).pack(side=tk.LEFT, padx=(4, 0))

        # 原文摘要
        preview = annot['text'][:40].replace('\n', ' ')
        if len(annot['text']) > 40:
            preview += '…'
        tk.Label(inner, text=f'"{preview}"', bg=C['bg_input'], fg=C['fg_file'],
                 font=('PingFang SC', 11), wraplength=220,
                 justify=tk.LEFT, anchor='w').pack(fill=tk.X)

        # 备注内容
        short = note[:80] + ('…' if len(note) > 80 else '')
        tk.Label(inner, text=short, bg=C['bg_input'], fg=C['fg'],
                 font=('PingFang SC', 12), wraplength=220,
                 justify=tk.LEFT, anchor='w').pack(fill=tk.X, pady=(4, 0))

        win.update_idletasks()
        tw = win.winfo_reqwidth()
        th = win.winfo_reqheight()
        tx = rx + 12
        ty = ry + 12
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        if tx + tw > sw - 4:
            tx = rx - tw - 12
        if ty + th > sh - 4:
            ty = ry - th - 12
        win.geometry(f'+{tx}+{ty}')
        self._tip_win = win

    def _hide_tip(self):
        if self._tip_after:
            try: self.text.after_cancel(self._tip_after)
            except Exception: pass
            self._tip_after = None
        if self._tip_win:
            try: self._tip_win.destroy()
            except Exception: pass
            self._tip_win = None

    # ══════════════════════════════════════════════════════════
    # 底部备注栏
    # ══════════════════════════════════════════════════════════

    def _build_note_bar(self):
        bar = self._note_bar
        bar.configure(bg=C['note_bar'])
        bar.pack_propagate(False)

        top = tk.Frame(bar, bg=C['note_bar'])
        top.pack(fill=tk.X, padx=12, pady=(8, 0))

        self._note_type_lbl = tk.Label(top, text="", bg=C['note_bar'], fg=C['accent'],
                                        font=('PingFang SC', 12))
        self._note_type_lbl.pack(side=tk.LEFT)

        _close_note = tk.Label(top, text="✕", bg=C['note_bar'], fg=C['btn_close'],
                               font=('PingFang SC', 12), cursor='hand2')
        _close_note.pack(side=tk.RIGHT)
        _close_note.bind('<Button-1>', lambda e: self._hide_note_bar())
        _close_note.bind('<Enter>', lambda e: _close_note.config(fg=C['fg_dim2']))
        _close_note.bind('<Leave>', lambda e: _close_note.config(fg=C['btn_close']))

        self._note_preview_lbl = tk.Label(top, text="", bg=C['note_bar'], fg=C['note_fg'],
                                           font=('PingFang SC', 12), anchor='w')
        self._note_preview_lbl.pack(side=tk.LEFT, padx=(8, 0))

        mid = tk.Frame(bar, bg=C['note_bar'])
        mid.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        self._note_entry = tk.Text(mid, bg=C['note_entry'], fg=C['fg'],
                                    insertbackground=C['fg'],
                                    font=('LXGW WenKai', 16),
                                    relief=tk.FLAT, bd=0,
                                    padx=8, pady=6,
                                    wrap=tk.WORD, height=3)
        self._note_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._note_entry.bind(f'<{MOD}-Return>', lambda e: self._save_note(hide_after=True))

        self._save_lbl = tk.Label(mid, text="✓",
                                   bg=C['save_btn_bg'], fg=C['save_btn_fg'],
                                   font=('PingFang SC', 12, 'bold'),
                                   padx=14, pady=6, cursor='hand2')
        self._save_lbl.pack(side=tk.RIGHT, padx=(8, 0))
        self._save_lbl.bind('<Button-1>', lambda e: self._save_note(hide_after=True))
        self._save_lbl.bind('<Enter>', lambda e: self._save_lbl.config(bg=C['save_btn_hov']))
        self._save_lbl.bind('<Leave>', lambda e: self._save_lbl.config(bg=C['save_btn_bg']))

        self._note_bar_built = True
        self._note_bar.pack_forget()

    def _show_note_bar(self, annot):
        self._active_annot = annot
        style   = ANNOT_STYLES.get(annot['type'], {})
        self._note_type_lbl.config(
            text=f"● {style.get('label','标注')}",
            fg=style.get('dot', C['accent']))
        preview = annot['text'][:50].replace('\n', ' ')
        if len(annot['text']) > 50:
            preview += '…'
        self._note_preview_lbl.config(text=f'"{preview}"')
        self._note_entry.delete('1.0', tk.END)
        self._note_entry.insert('1.0', annot.get('note', ''))
        # 清除主文本框选区，避免 focus 转移后出现暗色"非活跃选区"
        self.text.tag_remove('sel', '1.0', tk.END)
        if not self._note_bar.winfo_ismapped():
            self._note_bar.pack(side=tk.BOTTOM, fill=tk.X,
                                before=self.app._vsb_text)
        self._note_entry.focus_set()

    def _hide_note_bar(self):
        self._save_note(hide_after=True)

    def _save_note(self, hide_after=False):
        if self._active_annot and self._current_file:
            note = self._note_entry.get('1.0', tk.END).strip()
            self.store.update_note(self._current_file, self._active_annot['id'], note)
            self._active_annot['note'] = note
            self._refresh_panel()
            if hasattr(self, '_save_lbl'):
                self._save_lbl.config(text='✓✓', bg='#3a7a3a')
                self.app.after(800, lambda: self._save_lbl.config(text='✓', bg=C['save_btn_bg'])
                               if hasattr(self, '_save_lbl') else None)
        if hide_after or not self._active_annot:
            self._note_bar.pack_forget()
            self._active_annot = None
            self.text.focus_set()

    # ══════════════════════════════════════════════════════════
    # 添加 / 删除标注 + 撤销栈
    # ══════════════════════════════════════════════════════════

    def _annotate_selection(self, annot_type):
        try:
            start_idx = self.text.index('sel.first')
            end_idx   = self.text.index('sel.last')
        except tk.TclError:
            return
        if not self._current_file:
            return

        # 去掉末尾换行符，避免把下一行空白也染色
        while end_idx != start_idx and self.text.get(f'{end_idx}-1c', end_idx) in ('\n', '\r'):
            end_idx = self.text.index(f'{end_idx}-1c')

        start_off    = self._get_char_offset(start_idx)
        end_off      = self._get_char_offset(end_idx)
        text_content = self.text.get(start_idx, end_idx)

        self.text.tag_add(annot_type, start_idx, end_idx)

        author = self.app._get_author() if hasattr(self.app, '_get_author') else ''
        annot  = self.store.add(self._current_file, annot_type,
                                start_off, end_off, text_content, author=author)

        # 压入撤销栈
        self._undo_stack.append({'action': 'add', 'annot': annot, 'file': self._current_file})

        self._refresh_panel()
        self.app.after(50, lambda: self._show_note_bar(annot))
        return annot

    def _remove_at_cursor(self, event=None):
        if not self._current_file:
            return
        try:
            cursor = self.text.index('sel.first')
        except tk.TclError:
            cursor = self.text.index('insert')
        offset    = self._get_char_offset(cursor)
        to_remove = [a for a in self.store.get_for_file(self._current_file)
                     if a['start'] <= offset < a['end']]
        for annot in to_remove:
            self._do_remove(annot, push_undo=True)
        if to_remove:
            self._hide_note_bar()
            self._refresh_panel()

    def remove_annotation(self, annot):
        self._do_remove(annot, push_undo=True)
        if self._active_annot and self._active_annot['id'] == annot['id']:
            self._hide_note_bar()
        self._refresh_panel()

    def _do_remove(self, annot, push_undo=False):
        start = self._offset_to_index(annot['start'])
        end   = self._offset_to_index(annot['end'])
        self.text.tag_remove(annot['type'], start, end)
        self.store.remove(self._current_file, annot['id'])
        if push_undo:
            self._undo_stack.append(
                {'action': 'remove', 'annot': dict(annot), 'file': self._current_file})

    def _undo_annotation(self):
        if not self._undo_stack:
            # 批注撤销栈为空，回退到文本编辑器原生撤销
            try:
                self.text.edit_undo()
            except Exception:
                pass
            return
        item = self._undo_stack.pop()
        action = item['action']
        annot  = item['annot']
        fp     = item['file']

        if action == 'add':
            # 撤销添加 → 删除
            start = self._offset_to_index(annot['start'])
            end   = self._offset_to_index(annot['end'])
            self.text.tag_remove(annot['type'], start, end)
            self.store.remove(fp, annot['id'])
            if self._active_annot and self._active_annot['id'] == annot['id']:
                self._hide_note_bar()
        elif action == 'remove':
            # 撤销删除 → 重新添加
            self.store._restore(fp, annot)
            start = self._offset_to_index(annot['start'])
            end   = self._offset_to_index(annot['end'])
            self.text.tag_add(annot['type'], start, end)

        self._refresh_panel()

    def _change_annot_color(self, annot, new_type):
        """修改已有标注的颜色类型"""
        old_start = self._offset_to_index(annot['start'])
        old_end   = self._offset_to_index(annot['end'])
        self.text.tag_remove(annot['type'], old_start, old_end)
        self.text.tag_add(new_type, old_start, old_end)
        self.store.change_type(self._current_file, annot['id'], new_type)
        annot['type'] = new_type
        self._refresh_panel()

    # ══════════════════════════════════════════════════════════
    # 右键菜单（阅读区）
    # ══════════════════════════════════════════════════════════

    def populate_context_menu(self, menu):
        menu.add_separator()
        annot_sub = tk.Menu(menu, tearoff=0)
        menu.add_cascade(label="标注", menu=annot_sub)
        for annot_type, style in ANNOT_STYLES.items():
            hk = next((k.replace(f'<{MOD}-', f'{MOD_KEY}+').rstrip('>')
                       for k, t in HOTKEYS.items() if t == annot_type), '')
            label = f"{style['label']}  {hk}" if hk else style['label']
            annot_sub.add_command(label=label,
                command=lambda t=annot_type: self._annotate_selection(t))
        annot_sub.add_separator()
        annot_sub.add_command(label="取消光标处标注", command=self._remove_at_cursor)
        annot_sub.add_command(label=f"撤销  {MOD_KEY}+Z", command=self._undo_annotation)

    # ══════════════════════════════════════════════════════════
    # 点击检测（备注栏）
    # ══════════════════════════════════════════════════════════

    def _find_annotation_at(self, offset):
        if not self._current_file:
            return None
        candidates = [a for a in self.store.get_for_file(self._current_file)
                      if a['start'] <= offset < a['end']]
        return min(candidates, key=lambda a: a['end'] - a['start']) if candidates else None

    # ══════════════════════════════════════════════════════════
    # 文件加载 / 还原
    # ══════════════════════════════════════════════════════════

    def on_file_loaded(self, filepath):
        self._current_file = filepath
        self._hide_note_bar()
        self._restore_annotations(filepath)
        self._refresh_panel()

    def _restore_annotations(self, filepath):
        self._configure_tags()   # 确保 tag 颜色与当前主题一致
        for tag_name in ANNOT_STYLES:
            self.text.tag_remove(tag_name, '1.0', tk.END)
        annots = self.store.get_for_file(filepath)
        total     = int(self.text.count('1.0', tk.END, 'chars')[0])
        full_text = self.text.get('1.0', tk.END)

        # 新批注优先：按创建时间倒序排，确保较新的批注先占位
        annots_sorted = sorted(annots,
                               key=lambda a: a.get('created_at', ''),
                               reverse=True)
        applied = []   # 已占用的 [(start, end), ...]

        for annot in annots_sorted:
            if annot['type'] not in ANNOT_STYLES:
                continue
            s, e     = annot['start'], annot['end']
            expected = annot.get('text', '')
            length   = e - s
            if length <= 0:
                continue

            final_s = final_e = None

            # 精确匹配：直接用存储偏移量
            if 0 <= s and s + length <= total:
                if not expected or full_text[s:s + length] == expected:
                    final_s, final_e = s, s + length

            # 模糊匹配：找最靠近原始偏移量的出现位置
            if final_s is None and expected:
                best_idx, best_dist = -1, float('inf')
                pos = 0
                while True:
                    idx = full_text.find(expected, pos)
                    if idx == -1:
                        break
                    d = abs(idx - s)
                    if d < best_dist:
                        best_dist, best_idx = d, idx
                    pos = idx + 1
                if best_idx != -1:
                    final_s, final_e = best_idx, best_idx + len(expected)

            if final_s is None:
                continue

            # 与已占位范围有重叠则跳过（防止颜色混乱）
            if any(final_s < ae and final_e > as_ for as_, ae in applied):
                continue

            applied.append((final_s, final_e))
            self.text.tag_add(annot['type'],
                              f'1.0+{final_s}c',
                              f'1.0+{final_e}c')
        try:
            self.text.tag_raise('search_match')
            self.text.tag_raise('search_current')
        except tk.TclError:
            pass

    # ══════════════════════════════════════════════════════════
    # 右侧常驻标注面板
    # ══════════════════════════════════════════════════════════

    def _build_panel(self):
        container = self.app._annot_panel_frame
        container.configure(bg=C['bg_sidebar'])

        # 标题行
        hdr = tk.Frame(container, bg=C['bg_sidebar'], height=44)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(hdr, text="标记", bg=C['bg_sidebar'], fg=C['fg'],
                 font=('PingFang SC', 12)).pack(side=tk.LEFT, padx=14)
        _close_panel = tk.Label(hdr, text="✕", bg=C['bg_sidebar'], fg=C['btn_close'],
                                font=('PingFang SC', 12), cursor='hand2')
        _close_panel.pack(side=tk.RIGHT, padx=12)
        _close_panel.bind('<Button-1>', lambda e: self.toggle_panel())
        _close_panel.bind('<Enter>', lambda e: _close_panel.config(fg=C['fg_dim2']))
        _close_panel.bind('<Leave>', lambda e: _close_panel.config(fg=C['btn_close']))

        # 彩色圆点筛选行
        filter_frame = tk.Frame(container, bg=C['bg_sidebar'])
        filter_frame.pack(fill=tk.X, padx=12, pady=(0, 4))
        self._filter_type = 'all'
        self._filter_btns = {}
        for key in ('all', 'hl_yellow', 'hl_green', 'hl_pink', 'hl_purple'):
            color = C['fg'] if key == 'all' else ANNOT_STYLES[key]['dot']
            cv = tk.Canvas(filter_frame, width=22, height=22,
                           bg=C['bg_sidebar'], highlightthickness=0, cursor='hand2')
            cv.pack(side=tk.LEFT, padx=3)
            cv.create_oval(4, 4, 18, 18, fill=color, outline='')
            cv.bind('<Button-1>', lambda e, v=key: self._set_filter(v))
            self._filter_btns[key] = cv
        self._update_filter_btn_styles()

        # 搜索框
        self._panel_search_var = tk.StringVar()
        self._panel_search_var.trace_add('write', lambda *a: self._refresh_panel())
        search_frame = tk.Frame(container, bg=C['bg_sidebar'], padx=8, pady=4)
        search_frame.pack(fill=tk.X)
        search_entry = tk.Entry(search_frame,
                                textvariable=self._panel_search_var,
                                bg=C['bg_input'], fg=C['fg'],
                                insertbackground=C['fg'],
                                relief=tk.FLAT, bd=4,
                                font=('PingFang SC', 11))
        search_entry.pack(fill=tk.X)
        # 占位符
        def _on_focus_in(e):
            if search_entry.get() == '搜索批注…':
                search_entry.delete(0, tk.END)
                search_entry.config(fg=C['fg'])
        def _on_focus_out(e):
            if not search_entry.get():
                search_entry.insert(0, '搜索批注…')
                search_entry.config(fg=C['fg_hint'])
        search_entry.insert(0, '搜索批注…')
        search_entry.config(fg=C['fg_hint'])
        search_entry.bind('<FocusIn>',  _on_focus_in)
        search_entry.bind('<FocusOut>', _on_focus_out)

        # 分割线
        tk.Frame(container, bg=C['border'], height=1).pack(fill=tk.X)

        # 可滚动列表区
        outer = tk.Frame(container, bg=C['bg_sidebar'])
        outer.pack(fill=tk.BOTH, expand=True)
        self._panel_canvas = tk.Canvas(outer, bg=C['bg_sidebar'], highlightthickness=0)
        self._panel_canvas.pack(fill=tk.BOTH, expand=True)
        self._panel_inner = tk.Frame(self._panel_canvas, bg=C['bg_sidebar'])
        self._panel_inner_id = self._panel_canvas.create_window(
            (0, 6), window=self._panel_inner, anchor='nw')
        self._panel_inner.bind('<Configure>',
            lambda e: self._panel_canvas.configure(
                scrollregion=(0, 0, 0, self._panel_inner.winfo_reqheight() + 12)))
        self._panel_canvas.bind('<Configure>',
            lambda e: self._panel_canvas.itemconfig(
                self._panel_inner_id, width=e.width))

        self._panel_built = True
        self.app.bind_all('<MouseWheel>', self._on_mousewheel)
        self._refresh_panel()

    def _in_panel(self, event) -> bool:
        try:
            cv = self._panel_canvas
            x, y = cv.winfo_rootx(), cv.winfo_rooty()
            w, h = cv.winfo_width(), cv.winfo_height()
            return x <= event.x_root < x + w and y <= event.y_root < y + h
        except Exception:
            return False

    def _on_mousewheel(self, event):
        if not self._in_panel(event):
            return
        delta = event.delta
        units = -int(delta / 120) if abs(delta) >= 120 else -delta / 60.0
        self._panel_canvas.yview_scroll(int(units) or (-1 if delta < 0 else 1), 'units')

    def toggle_panel(self):
        try:
            idx    = self.text.index('@73,41')
            offset = int(self.text.count('1.0', idx, 'chars')[0])
        except Exception:
            offset = None

        if self.app._annot_panel_visible:
            self.app._annot_panel_frame.pack_forget()
            self.app._annot_panel_visible = False
        else:
            self.app._annot_panel_frame.pack(side=tk.RIGHT, fill=tk.Y,
                                              before=self.app._reader)
            self.app._annot_panel_visible = True
            self._refresh_panel()

        if offset is not None:
            def restore():
                try:
                    self.text.update_idletasks()
                    target = f'1.0+{offset}c'
                    self.text.see(target)
                    self.text.update_idletasks()
                    self.text.yview(target)
                except Exception:
                    pass
            self.app.after(100, restore)
            self.app.after(350, restore)

    def _set_filter(self, val):
        self._filter_type = val
        self._update_filter_btn_styles()
        self._refresh_panel()

    def _update_filter_btn_styles(self):
        for val, cv in self._filter_btns.items():
            active = (val == self._filter_type)
            color  = C['fg'] if val == 'all' else ANNOT_STYLES[val]['dot']
            cv.delete('all')
            if active:
                cv.create_oval(1, 1, 21, 21, outline=color, width=2)
            cv.create_oval(4, 4, 18, 18, fill=color, outline='')

    def _refresh_panel(self):
        if not self._panel_built or self._panel_inner is None:
            return
        if not self.app._annot_panel_visible:
            return

        for w in self._panel_inner.winfo_children():
            w.destroy()
        self._panel_canvas.yview_moveto(0)

        if not self._current_file:
            tk.Label(self._panel_inner, text="请先打开文件",
                     bg=C['bg_sidebar'], fg=C['fg_dim2'],
                     font=('PingFang SC', 12)).pack(pady=24)
            return

        ftype  = self._filter_type
        annots = self.store.get_for_file(self._current_file)
        if ftype != 'all':
            annots = [a for a in annots if a['type'] == ftype]

        # 搜索过滤
        q = ''
        if self._panel_search_var:
            q = self._panel_search_var.get().strip()
            if q == '搜索批注…':
                q = ''
        if q:
            ql = q.lower()
            annots = [a for a in annots
                      if ql in a.get('text', '').lower()
                      or ql in a.get('note', '').lower()]

        if not annots:
            hint = ("暂无标注\n\n选中文字后弹出工具条\n或使用快捷键:\n"
                    f"{MOD_KEY}+1 黄  {MOD_KEY}+2 绿\n{MOD_KEY}+3 粉  {MOD_KEY}+4 紫")
            tk.Label(self._panel_inner, text=hint,
                     bg=C['bg_sidebar'], fg=C['fg_dim2'],
                     font=('PingFang SC', 11),
                     justify=tk.CENTER).pack(pady=30)
            return

        for annot in annots:
            self._render_card(annot)

    def _render_card(self, annot):
        style    = ANNOT_STYLES.get(annot['type'], {})
        color    = style.get('dot', C['accent'])
        WL       = 192
        BG_HOVER = C['hover_card']

        row = tk.Frame(self._panel_inner, bg=C['bg_sidebar'])
        row.pack(fill=tk.X, pady=2, padx=6)
        tk.Frame(row, bg=color, width=3).pack(side=tk.LEFT, fill=tk.Y)
        card = tk.Frame(row, bg=C['bg_input'], padx=12, pady=10)
        card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 原文预览
        preview = annot['text'][:50].replace('\n', ' ')
        if len(annot['text']) > 50:
            preview += '…'
        tk.Label(card, text=preview, bg=C['bg_input'], fg=C['fg'],
                 font=('PingFang SC', 13), wraplength=WL,
                 justify=tk.LEFT, anchor='w').pack(fill=tk.X)

        # 备注（内嵌显示）
        note = annot.get('note', '').strip()
        if note:
            short = note[:60] + ('…' if len(note) > 60 else '')
            tk.Label(card, text=short, bg=C['bg_input'], fg=C['note_fg_dim'],
                     font=('PingFang SC', 11), wraplength=WL,
                     justify=tk.LEFT, anchor='w').pack(fill=tk.X, pady=(4, 0))

        # 元信息：作者 + 时间
        meta_parts = []
        author = annot.get('author', '').strip()
        if author:
            meta_parts.append(f'@{author}')
        created = annot.get('created_at', '')
        if created:
            meta_parts.append(created[:10])
        if meta_parts:
            tk.Label(card, text='  '.join(meta_parts), bg=C['bg_input'],
                     fg=C['fg_dim2'], font=('PingFang SC', 10),
                     anchor='w').pack(fill=tk.X, pady=(5, 0))

        # 点击跳转 + 打开备注栏
        def jump(e, a=annot):
            self._jump_to(a)
            self._show_note_bar(a)

        # Hover 动画
        def _hex_to_rgb(h):
            h = h.lstrip('#')
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

        def _rgb_to_hex(r, g, b):
            return '#{:02x}{:02x}{:02x}'.format(int(r), int(g), int(b))

        def _lerp(a, b, t):
            return a + (b - a) * t

        def _collect_labels(w):
            result = []
            if isinstance(w, tk.Label):
                result.append(w)
            for ch in w.winfo_children():
                result.extend(_collect_labels(ch))
            return result

        all_labels = _collect_labels(card)
        _anim = {'after_id': None, 'entering': False}
        STEPS = 8
        INTERVAL = 18
        LBL_COLORS = {C['fg']: C['fg'], C['note_fg_dim']: C['fg_file']}
        BG_START = _hex_to_rgb(C['bg_input'])
        BG_END   = _hex_to_rgb(BG_HOVER)

        def _animate(step, entering):
            if _anim['entering'] != entering:
                return
            t = step / STEPS if entering else 1 - step / STEPS
            br, bg_, bb = (_lerp(BG_START[i], BG_END[i], t) for i in range(3))
            bg_cur = _rgb_to_hex(br, bg_, bb)
            try: card.configure(bg=bg_cur)
            except Exception: pass
            for lbl in all_labels:
                try:
                    orig = lbl._orig_fg
                    c0 = _hex_to_rgb(orig)
                    c1 = _hex_to_rgb(LBL_COLORS.get(orig, orig))
                    lbl.configure(fg=_rgb_to_hex(
                        _lerp(c0[0], c1[0], t),
                        _lerp(c0[1], c1[1], t),
                        _lerp(c0[2], c1[2], t)))
                except Exception:
                    pass
            if step < STEPS:
                _anim['after_id'] = card.after(INTERVAL,
                    lambda s=step+1, en=entering: _animate(s, en))

        for lbl in all_labels:
            lbl._orig_fg = lbl.cget('fg')

        def _on_enter(e):
            _anim['entering'] = True
            if _anim['after_id']:
                card.after_cancel(_anim['after_id'])
            _animate(1, True)

        def _on_leave(e):
            _anim['entering'] = False
            if _anim['after_id']:
                card.after_cancel(_anim['after_id'])
            _animate(1, False)

        for w in [row, card] + card.winfo_children():
            w.bind('<Button-1>', jump)
        row.bind('<Enter>', _on_enter)
        row.bind('<Leave>', _on_leave)
        card.bind('<Enter>', _on_enter)
        card.bind('<Leave>', _on_leave)

        # 右键菜单：删除 + 修改颜色
        ctx = tk.Menu(self.app, tearoff=0)
        ctx.add_command(label="编辑备注",
                        command=lambda a=annot: (self._jump_to(a), self._show_note_bar(a)))
        ctx.add_separator()
        color_sub = tk.Menu(ctx, tearoff=0)
        ctx.add_cascade(label="修改颜色", menu=color_sub)
        for ct in ('hl_yellow', 'hl_green', 'hl_pink', 'hl_purple'):
            st = ANNOT_STYLES.get(ct, {})
            color_sub.add_command(
                label=st.get('label', ct),
                command=lambda a=annot, t=ct: self._change_annot_color(a, t))
        ctx.add_separator()
        ctx.add_command(label="复制原文",
                        command=lambda a=annot: (
                            self.app.clipboard_clear(),
                            self.app.clipboard_append(a['text'])))
        ctx.add_command(label="复制备注",
                        command=lambda a=annot: (
                            self.app.clipboard_clear(),
                            self.app.clipboard_append(a.get('note', ''))))
        ctx.add_separator()
        ctx.add_command(label="删除此标注",
                        command=lambda a=annot: self.remove_annotation(a))

        for w in [row, card] + card.winfo_children():
            w.bind('<Button-2>', lambda e, m=ctx: m.tk_popup(e.x_root, e.y_root))
            w.bind('<Button-3>', lambda e, m=ctx: m.tk_popup(e.x_root, e.y_root))

    # ══════════════════════════════════════════════════════════
    # 跳转 / 工具函数
    # ══════════════════════════════════════════════════════════

    def _jump_to(self, annot):
        si = self._offset_to_index(annot['start'])
        ei = self._offset_to_index(annot['end'])
        self.text.see(si)
        self.text.tag_remove('sel', '1.0', tk.END)
        self.text.tag_add('sel', si, ei)
        self.text.mark_set('insert', si)
        self.app.lift()
        self.text.focus_set()

    def _get_char_offset(self, index):
        result = self.text.count('1.0', index, 'chars')
        return int(result[0]) if result else 0

    def _offset_to_index(self, offset):
        return f'1.0+{offset}c'

    # ══════════════════════════════════════════════════════════
    # 主题刷新
    # ══════════════════════════════════════════════════════════

    def refresh_theme(self, color_map, theme_name='dark'):
        ANNOT_STYLES.update(ANNOT_THEMES[theme_name])
        self._configure_tags()
        self._refresh_panel()
        self._update_filter_btn_styles()
