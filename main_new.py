#!/usr/bin/env python3
"""purple loop v2 — PyQt6 + inline #tag"""

import sys, os, json, re, uuid, subprocess
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QTreeWidget, QTreeWidgetItem,
    QStackedWidget, QTextEdit, QScrollArea, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QFrame, QMenu, QFileDialog, QInputDialog,
    QMessageBox, QSizePolicy, QAbstractScrollArea
)
from PyQt6.QtGui import (
    QColor, QFont, QTextCharFormat, QTextCursor, QTextDocument,
    QPalette, QPixmap, QImage, QAction, QKeySequence, QSyntaxHighlighter,
    QPainter, QFontDatabase, QCursor
)
from PyQt6.QtCore import (
    Qt, QTimer, QSize, QPoint, QRect, pyqtSignal, QThread, QObject
)


# ── 常量 ──────────────────────────────────────────────────────────────────
DATA_FILE = Path.home() / '.purple-loop.json'
TAG_RE    = re.compile(r'#([\w\u4e00-\u9fff]+(?:/[\w\u4e00-\u9fff]+)*)')
IS_MAC    = sys.platform == 'darwin'
MOD       = Qt.KeyboardModifier.MetaModifier if IS_MAC else Qt.KeyboardModifier.ControlModifier

# 字体目录
_APP_DIR  = Path(__file__).parent
FONTS_DIR = _APP_DIR / 'fonts'

# ── 配色 ──────────────────────────────────────────────────────────────────
C = {
    'bg':          '#1c1e1f',
    'bg_sidebar':  '#161819',
    'bg_input':    '#252729',
    'bg_sel':      '#2a2d30',
    'fg':          '#e8e8e8',
    'fg_tag':      '#a0a4a0',
    'fg_file':     '#6e726e',
    'fg_dim':      '#5a5e5a',
    'accent':      '#5b9cf6',
    'border':      '#2a2d30',
    'save_green':  '#1db070',
    # 标注颜色 (bg, fg/dot)
    'hl_yellow':   ('#3a2e00', '#e8c870'),
    'hl_green':    ('#0e2a1a', '#5ec87a'),
    'hl_pink':     ('#3a1020', '#e86090'),
    'hl_purple':   ('#1a1040', '#a878f0'),
    'bold':        (None,      '#dfe3df'),
    'underline':   (None,      '#dfe3df'),
}

ANNOT_LABEL = {
    'hl_yellow': '黄色高亮',
    'hl_green':  '绿色高亮',
    'hl_pink':   '粉色高亮',
    'hl_purple': '紫色高亮',
    'bold':      '加粗',
    'underline': '下划线',
}


# ── 数据层 ────────────────────────────────────────────────────────────────

class FileStore:
    """持久化：Word/PDF 导入记录 + 标注数据"""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict = {'annotations': {}, 'config': {}}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text('utf-8'))
            except Exception:
                pass

    def save(self):
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), 'utf-8')

    # ── 单独拖入的 .txt 文件 ───────────────────────────────
    def add_txt(self, path: str):
        lst = self.data.setdefault('txt_files', [])
        if path not in lst:
            lst.append(path)
            self.save()

    def get_txt_files(self) -> list:
        return [p for p in self.data.get('txt_files', []) if Path(p).exists()]

    def remove_txt(self, path: str):
        lst = self.data.get('txt_files', [])
        if path in lst:
            lst.remove(path)
            self.save()

    # ── 配置 ──────────────────────────────────────────────────
    def get_config(self, key, default=None):
        return self.data.get('config', {}).get(key, default)

    def set_config(self, key, value):
        self.data.setdefault('config', {})[key] = value
        self.save()

    # ── 阅读位置 ──────────────────────────────────────────────
    def get_read_pos(self, filepath: str) -> int:
        return self.data.get('read_positions', {}).get(filepath, 0)

    def set_read_pos(self, filepath: str, pos: int):
        self.data.setdefault('read_positions', {})[filepath] = pos
        self.save()

    # ── 标注 ──────────────────────────────────────────────────
    def get_annotations(self, filepath: str) -> list:
        return sorted(
            self.data.get('annotations', {}).get(filepath, []),
            key=lambda a: a['start'])

    def add_annotation(self, filepath: str, atype: str,
                       start: int, end: int, text: str, **kwargs) -> dict:
        annot = {
            'id':         str(uuid.uuid4()),
            'type':       atype,
            'start':      start,
            'end':        end,
            'text':       text,
            'note':       '',
            'created_at': datetime.now().isoformat(timespec='seconds'),
            **kwargs,
        }
        self.data.setdefault('annotations', {}).setdefault(filepath, []).append(annot)
        self.save()
        return annot

    def remove_annotation(self, filepath: str, annot_id: str):
        lst = self.data.get('annotations', {}).get(filepath, [])
        self.data['annotations'][filepath] = [a for a in lst if a['id'] != annot_id]
        self.save()

    def update_note(self, filepath: str, annot_id: str, note: str):
        for a in self.data.get('annotations', {}).get(filepath, []):
            if a['id'] == annot_id:
                a['note'] = note
                break
        self.save()

    def update_offsets(self, filepath: str, edit_pos: int, delta: int):
        """文本编辑后更新偏移量"""
        changed = False
        for a in self.data.get('annotations', {}).get(filepath, []):
            if a['start'] >= edit_pos:
                a['start'] = max(0, a['start'] + delta)
                a['end']   = max(a['start'], a['end'] + delta)
                changed = True
            elif a['end'] > edit_pos:
                a['end'] = max(a['start'], a['end'] + delta)
                changed = True
        if changed:
            self.save()


class TagScanner:
    """从 .txt 文件内容提取 #标签"""

    @staticmethod
    def scan(filepath: str) -> set:
        try:
            return set(TAG_RE.findall(Path(filepath).read_text('utf-8')))
        except Exception:
            return set()

    @staticmethod
    def build_tree(txt_files: list) -> dict:
        """返回 {tag_path: [filepath, ...]}，含各层级"""
        tree: dict = {}
        for fp in txt_files:
            for tag in TagScanner.scan(fp):
                parts = tag.split('/')
                for i in range(1, len(parts) + 1):
                    key = '/'.join(parts[:i])
                    tree.setdefault(key, [])
                    if fp not in tree[key]:
                        tree[key].append(fp)
        return tree


# ── 标注浮动工具条 ────────────────────────────────────────────────────────

class AnnotBar(QFrame):
    """选中文字后弹出的浮动工具条"""
    annotate        = pyqtSignal(str)
    label_requested = pyqtSignal()   # 请求输入标签名
    remove          = pyqtSignal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(f"""
            QFrame {{
                background: {C['bg_input']};
                border: 1px solid {C['border']};
                border-radius: 6px;
            }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(6)

        _types = [
            ('hl_yellow', '#e8c870', ''),
            ('hl_green',  '#5ec87a', ''),
            ('hl_pink',   '#e86090', ''),
            ('hl_purple', '#a878f0', ''),
            ('bold',      None,      'B'),
            ('underline', None,      'U'),
        ]

        for atype, color, label in _types:
            btn = QPushButton()
            btn.setFixedSize(26, 26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(ANNOT_LABEL.get(atype, atype))
            if color:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {color}; border-radius: 13px; border: none;
                    }}
                    QPushButton:hover {{ border: 2px solid white; }}
                """)
            else:
                f = QFont('PingFang SC', 12)
                f.setBold(atype == 'bold')
                f.setUnderline(atype == 'underline')
                btn.setFont(f)
                btn.setText(label)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {C['bg_sel']}; color: {C['fg']};
                        border-radius: 4px; border: none;
                    }}
                    QPushButton:hover {{ background: {C['accent']}; color: white; }}
                """)
            btn.clicked.connect(lambda _, t=atype: self.annotate.emit(t))
            lay.addWidget(btn)

        # ── 文字标签按钮 ──────────────────────────
        sep_lbl = QFrame()
        sep_lbl.setFrameShape(QFrame.Shape.VLine)
        sep_lbl.setStyleSheet(f"color: {C['border']};")
        lay.addWidget(sep_lbl)

        lbl_btn = QPushButton('#')
        lbl_btn.setFixedSize(26, 26)
        lbl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        lbl_btn.setToolTip('文字标签')
        lbl_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C['bg_sel']}; color: {C['accent']};
                border-radius: 4px; border: none; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {C['accent']}; color: white; }}
        """)
        lbl_btn.clicked.connect(self.label_requested.emit)
        lay.addWidget(lbl_btn)

        # ── 删除按钮 ──────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {C['border']};")
        lay.addWidget(sep)

        del_btn = QPushButton('✕')
        del_btn.setFixedSize(26, 26)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C['fg_dim']}; border: none; font-size: 12px;
            }}
            QPushButton:hover {{ color: #ff6b6b; }}
        """)
        del_btn.clicked.connect(self.remove.emit)
        lay.addWidget(del_btn)


# ── 标注面板（右侧卡片列表）─────────────────────────────────────────────

class AnnotPanel(QScrollArea):
    jump_to = pyqtSignal(str)   # annot_id
    delete  = pyqtSignal(str)   # annot_id

    def __init__(self, store: FileStore, parent=None):
        super().__init__(parent)
        self.store    = store
        self._fp      = None
        self._cards   = {}     # annot_id -> card widget
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(f"background: {C['bg_sidebar']}; border: none;")

        inner = QWidget()
        inner.setStyleSheet(f"background: {C['bg_sidebar']};")
        self._layout = QVBoxLayout(inner)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(6)
        self._layout.addStretch()
        self.setWidget(inner)

    def refresh(self, filepath: str | None):
        self._fp = filepath
        # 清空
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()
        if not filepath:
            return
        for annot in self.store.get_annotations(filepath):
            card = self._make_card(annot)
            self._layout.insertWidget(self._layout.count() - 1, card)
            self._cards[annot['id']] = card

    def _make_card(self, annot: dict) -> QFrame:
        if annot['type'] == 'label':
            dot = '#c4b0f8'
            card_label = annot.get('label_text', '标签')
        else:
            _, dot = C.get(annot['type'], (None, C['accent']))
            dot = dot or C['accent']
            card_label = ANNOT_LABEL.get(annot['type'], annot['type'])
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {C['bg_input']}; border-radius: 6px;
                border-left: 3px solid {dot};
            }}
            QFrame:hover {{ background: #2a2d32; }}
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 6, 8)
        lay.setSpacing(4)

        # 顶栏：类型标签 + 删除按钮
        top = QHBoxLayout()
        if annot['type'] == 'label':
            # 以 pill 样式显示标签名
            pill = QLabel(f'  # {card_label}  ')
            pill.setStyleSheet(f"""
                background: #1e1040; color: {dot};
                border-radius: 3px; font-size: 11px; padding: 1px 0;
            """)
            type_lbl = pill
        else:
            type_lbl = QLabel(card_label)
            type_lbl.setStyleSheet(f"color: {dot}; font-size: 11px;")
        top.addWidget(type_lbl)
        top.addStretch()
        del_btn = QPushButton('✕')
        del_btn.setFixedSize(18, 18)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C['fg_dim']};
                border: none; font-size: 10px;
            }}
            QPushButton:hover {{ color: #ff6b6b; }}
        """)
        aid = annot['id']
        del_btn.clicked.connect(lambda _, a=aid: self.delete.emit(a))
        top.addWidget(del_btn)
        lay.addLayout(top)

        # 原文预览
        preview = annot['text'][:50].replace('\n', ' ')
        if len(annot['text']) > 50:
            preview += '…'
        text_lbl = QLabel(f'"{preview}"')
        text_lbl.setStyleSheet(f"color: {C['fg_file']}; font-size: 12px;")
        text_lbl.setWordWrap(True)
        lay.addWidget(text_lbl)

        # 备注（如有）
        if annot.get('note', '').strip():
            note_lbl = QLabel(annot['note'][:80])
            note_lbl.setStyleSheet(f"color: {C['fg']}; font-size: 13px;")
            note_lbl.setWordWrap(True)
            lay.addWidget(note_lbl)

        card.mousePressEvent = lambda e, a=aid: (
            self.jump_to.emit(a) if e.button() == Qt.MouseButton.LeftButton else None)
        return card


# ── 底部备注输入栏 ────────────────────────────────────────────────────────

class NoteBar(QFrame):
    saved = pyqtSignal()

    def __init__(self, store: FileStore, parent=None):
        super().__init__(parent)
        self.store   = store
        self._fp     = None
        self._annot  = None
        self.setStyleSheet(f"background: {C['bg_input']}; border-top: 1px solid {C['border']};")
        self.setFixedHeight(110)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)

        top = QHBoxLayout()
        self._type_lbl = QLabel('')
        self._type_lbl.setStyleSheet(f"color: {C['accent']}; font-size: 12px;")
        top.addWidget(self._type_lbl)
        top.addStretch()
        close_btn = QPushButton('✕')
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet(
            f"background: transparent; color: {C['fg_dim']}; border: none;")
        close_btn.clicked.connect(self.hide)
        top.addWidget(close_btn)
        lay.addLayout(top)

        row = QHBoxLayout()
        self._entry = QTextEdit()
        self._entry.setFixedHeight(54)
        self._entry.setStyleSheet(f"""
            QTextEdit {{
                background: {C['bg']}; color: {C['fg']};
                border: none; border-radius: 4px;
                font-family: 'LXGW WenKai'; font-size: 14px;
                padding: 4px 8px;
            }}
        """)
        row.addWidget(self._entry)

        save_btn = QPushButton('✓')
        save_btn.setFixedSize(36, 54)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C['save_green']}; color: white;
                border: none; border-radius: 4px; font-size: 18px;
            }}
            QPushButton:hover {{ background: #25c97e; }}
        """)
        save_btn.clicked.connect(self._save)
        row.addWidget(save_btn)
        lay.addLayout(row)
        self.hide()

    def show_for(self, annot: dict, filepath: str):
        self._annot = annot
        self._fp    = filepath
        dot = C.get(annot['type'], (None, C['accent']))[1] or C['accent']
        self._type_lbl.setText(f"● {ANNOT_LABEL.get(annot['type'], '标注')}")
        self._type_lbl.setStyleSheet(f"color: {dot}; font-size: 12px;")
        self._entry.setPlainText(annot.get('note', ''))
        self.show()
        self._entry.setFocus()

    def _save(self):
        if self._annot and self._fp:
            self.store.update_note(self._fp, self._annot['id'],
                                   self._entry.toPlainText().strip())
        self.saved.emit()
        self.hide()


# ── #标签语法高亮 ─────────────────────────────────────────────────────────

class TagHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        self._fmt = QTextCharFormat()
        self._fmt.setForeground(QColor(C['accent']))

    def highlightBlock(self, text: str):
        for m in TAG_RE.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._fmt)


# ── txt 编辑器 ───────────────────────────────────────────────────────────

class TxtEditor(QTextEdit):
    mouse_released = pyqtSignal()   # 鼠标松开时通知主窗口检查选区

    def __init__(self, store: FileStore, parent=None):
        super().__init__(parent)
        self.store    = store
        self._fp: str | None = None
        self._loading = False
        self._highlighter = TagHighlighter(self.document())

        # 字体
        self._set_font()
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C['bg']}; color: {C['fg']};
                border: none; padding: 48px 120px;
                selection-background-color: #4a4a55;
                selection-color: #e0e0e0;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: #3a3a3e;
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #555558;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Highlight,       QColor('#4a4a55'))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor('#e0e0e0'))
        self.setPalette(pal)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # 偏移追踪
        self.document().contentsChange.connect(self._on_change)

        # 自动保存：文字变化后 2 秒触发
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self.save)
        self.document().contentsChanged.connect(self._schedule_save)

        pass  # 选区检测改为 mouseReleaseEvent

    def _set_font(self):
        # 尝试加载 LXGW WenKai，回退到系统字体
        f = QFont('LXGW WenKai', 18)
        if not f.exactMatch():
            f = QFont('PingFang SC', 18)
        f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.setFont(f)
        # 行间距 1.65（研究最优值：中文黑底）
        self._apply_line_spacing()

    def _apply_line_spacing(self):
        from PyQt6.QtGui import QTextBlockFormat
        cur = QTextCursor(self.document())
        cur.select(QTextCursor.SelectionType.Document)
        blk_fmt = QTextBlockFormat()
        blk_fmt.setLineHeight(165, 1)  # 1 = ProportionalHeight (百分比)
        cur.setBlockFormat(blk_fmt)

    def load_file(self, path: str):
        # 保存当前文件的阅读位置
        if self._fp:
            self.store.set_read_pos(self._fp, self.verticalScrollBar().value())

        self._fp      = path
        self._loading = True
        text = Path(path).read_text('utf-8')
        self.setPlainText(text)
        self._loading = False
        self._apply_line_spacing()   # setPlainText 会重置 block format
        self._apply_annotations()

        # 恢复阅读位置（延迟到布局完成后）
        saved_pos = self.store.get_read_pos(path)
        QTimer.singleShot(50, lambda: self.verticalScrollBar().setValue(saved_pos))


    def _apply_annotations(self):
        if not self._fp:
            return
        # 先清除所有格式
        cur = QTextCursor(self.document())
        cur.select(QTextCursor.SelectionType.Document)
        cur.setCharFormat(QTextCharFormat())
        cur.clearSelection()
        # 再应用标注
        for a in self.store.get_annotations(self._fp):
            self._apply_fmt(a)

    def _apply_fmt(self, annot: dict):
        doc = self.document()
        cur = QTextCursor(doc)
        cur.setPosition(min(annot['start'], doc.characterCount() - 1))
        cur.setPosition(min(annot['end'],   doc.characterCount() - 1),
                        QTextCursor.MoveMode.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setFont(self.font())
        fmt.setForeground(QColor(C['fg']))
        if annot['type'] == 'label':
            fmt.setBackground(QColor('#1e1040'))
            fmt.setForeground(QColor('#c4b0f8'))
            fmt.setFontUnderline(True)
        else:
            bg, fg = C.get(annot['type'], (None, None))
            if bg:
                fmt.setBackground(QColor(bg))
            if fg and annot['type'] not in ('bold', 'underline'):
                fmt.setForeground(QColor(fg))
            if annot['type'] == 'bold':
                fmt.setFontWeight(QFont.Weight.Bold)
            if annot['type'] == 'underline':
                fmt.setFontUnderline(True)
        cur.setCharFormat(fmt)

    def annotate(self, atype: str, label_text: str = '') -> dict | None:
        if not self._fp:
            return None
        cur = self.textCursor()
        if not cur.hasSelection():
            return None
        start = min(cur.position(), cur.anchor())
        end   = max(cur.position(), cur.anchor())
        text  = cur.selectedText().replace('\u2029', '\n')
        extra = {'label_text': label_text} if label_text else {}
        annot = self.store.add_annotation(self._fp, atype, start, end, text, **extra)
        self._apply_fmt(annot)
        return annot

    def remove_at_cursor(self):
        if not self._fp:
            return
        pos = self.textCursor().position()
        for a in self.store.get_annotations(self._fp):
            if a['start'] <= pos <= a['end']:
                self.store.remove_annotation(self._fp, a['id'])
                self._apply_annotations()
                return

    def jump_to_annot(self, annot_id: str):
        if not self._fp:
            return
        for a in self.store.get_annotations(self._fp):
            if a['id'] == annot_id:
                cur = QTextCursor(self.document())
                cur.setPosition(a['start'])
                cur.setPosition(a['end'], QTextCursor.MoveMode.KeepAnchor)
                self.setTextCursor(cur)
                self.ensureCursorVisible()
                return

    def annot_at_cursor(self) -> dict | None:
        if not self._fp:
            return None
        pos = self.textCursor().position()
        for a in self.store.get_annotations(self._fp):
            if a['start'] <= pos <= a['end']:
                return a
        return None

    def _on_change(self, pos: int, removed: int, added: int):
        if self._loading or not self._fp:
            return
        delta = added - removed
        if delta:
            self.store.update_offsets(self._fp, pos, delta)

    def _schedule_save(self):
        if not self._loading:
            self._save_timer.start(2000)   # 2 秒防抖

    def save(self):
        if self._fp:
            try:
                Path(self._fp).write_text(self.toPlainText(), 'utf-8')
            except Exception:
                pass

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {C['bg_input']}; color: {C['fg']};
                border: 1px solid {C['border']}; border-radius: 6px; padding: 4px;
            }}
            QMenu::item {{ padding: 6px 20px; border-radius: 4px; }}
            QMenu::item:selected {{ background: #3a3a3e; color: {C['fg']}; }}
            QMenu::item:disabled {{ color: {C['fg_dim']}; }}
            QMenu::separator {{ background: {C['border']}; height: 1px; margin: 4px 8px; }}
        """)
        cur = self.textCursor()
        has_sel = cur.hasSelection()

        a_copy = QAction('复制', self)
        a_copy.setShortcut(QKeySequence.StandardKey.Copy)
        a_copy.setEnabled(has_sel)
        a_copy.triggered.connect(self.copy)
        menu.addAction(a_copy)

        a_cut = QAction('剪切', self)
        a_cut.setShortcut(QKeySequence.StandardKey.Cut)
        a_cut.setEnabled(has_sel)
        a_cut.triggered.connect(self.cut)
        menu.addAction(a_cut)

        a_paste = QAction('粘贴', self)
        a_paste.setShortcut(QKeySequence.StandardKey.Paste)
        a_paste.triggered.connect(self.paste)
        menu.addAction(a_paste)

        menu.addSeparator()

        a_all = QAction('全选', self)
        a_all.setShortcut(QKeySequence.StandardKey.SelectAll)
        a_all.triggered.connect(self.selectAll)
        menu.addAction(a_all)

        menu.exec(event.globalPos())

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            QTimer.singleShot(30, self.mouse_released.emit)

    def keyPressEvent(self, event):
        if event.modifiers() & MOD:
            if event.key() == Qt.Key.Key_C:
                self.copy(); return
            if event.key() == Qt.Key.Key_V:
                self.paste(); return
            if event.key() == Qt.Key.Key_X:
                self.cut(); return
            if event.key() == Qt.Key.Key_A:
                self.selectAll(); return
            key_map = {
                Qt.Key.Key_1: 'hl_yellow',
                Qt.Key.Key_2: 'hl_green',
                Qt.Key.Key_3: 'hl_pink',
                Qt.Key.Key_4: 'hl_purple',
                Qt.Key.Key_B: 'bold',
                Qt.Key.Key_U: 'underline',
            }
            if event.key() in key_map:
                self.window()._do_annotate(key_map[event.key()])
                return
        super().keyPressEvent(event)



# ── 侧边栏 ────────────────────────────────────────────────────────────────

class Sidebar(QTreeWidget):
    file_selected = pyqtSignal(str)
    tag_rename    = pyqtSignal(str, str)   # old_full_tag, new_name
    tag_merge     = pyqtSignal(str, str)   # src_tag, dst_tag

    def __init__(self, store: FileStore, parent=None):
        super().__init__(parent)
        self.store   = store
        self._txt_files: list[str] = []

        self.setHeaderHidden(True)
        self.setIndentation(16)
        self.setAnimated(True)
        self.setStyleSheet(f"""
            QTreeWidget {{
                background: {C['bg_sidebar']};
                color: {C['fg_tag']};
                border: none;
                font-size: 13px;
            }}
            QTreeWidget::item {{
                padding: 3px 4px;
                border-radius: 4px;
            }}
            QTreeWidget::item:selected {{
                background: {C['bg_sel']};
                color: {C['fg']};
            }}
            QTreeWidget::item:hover {{
                background: {C['bg_input']};
            }}
            QTreeWidget::branch {{
                background: {C['bg_sidebar']};
            }}
        """)

        self.itemDoubleClicked.connect(self._on_double_click)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_ctx)

        # 拖放
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)

    def refresh(self, txt_files: list[str]):
        self._txt_files = txt_files
        expanded = self._save_expanded()
        self.clear()

        tag_tree   = TagScanner.build_tree(txt_files)
        untagged   = [f for f in txt_files
                      if not TagScanner.scan(f)]

        # ── 标签树 ───────────────────────────────────────────
        def add_tag_node(parent_item, tag_path: str, depth: int):
            tag    = self.store  # unused, just tag_path
            parts  = tag_path.split('/')
            name   = parts[-1]
            files  = tag_tree.get(tag_path, [])
            count  = len(files)
            item   = QTreeWidgetItem(
                parent_item, [f"# {name}  {count}"])
            item.setData(0, Qt.ItemDataRole.UserRole, ('tag', tag_path))
            item.setForeground(0, QColor(C['fg_tag']))
            item.setFont(0, QFont('PingFang SC', 13))

            # 子标签
            children = {t for t in tag_tree
                        if t.startswith(tag_path + '/') and
                        t.count('/') == tag_path.count('/') + 1}
            for child in sorted(children):
                add_tag_node(item, child, depth + 1)

            # 该标签下的 .txt 文件（仅直属，非子标签的）
            child_tags_files = set()
            for c in children:
                child_tags_files.update(tag_tree.get(c, []))
            direct_files = [f for f in files if f not in child_tags_files]
            for fp in sorted(direct_files, key=lambda x: Path(x).stat().st_mtime, reverse=True):
                fi = QTreeWidgetItem(item, [f"  {Path(fp).stem}"])
                fi.setData(0, Qt.ItemDataRole.UserRole, ('file', fp))
                fi.setForeground(0, QColor(C['fg_file']))
                fi.setFont(0, QFont('PingFang SC', 12))
            return item

        roots = {t for t in tag_tree if '/' not in t}
        for tag in sorted(roots):
            node = add_tag_node(self.invisibleRootItem(), tag, 0)

        # ── 未分类 .txt ───────────────────────────────────────
        if untagged:
            hdr = QTreeWidgetItem(self.invisibleRootItem(), ['未分类'])
            hdr.setData(0, Qt.ItemDataRole.UserRole, ('header', ''))
            hdr.setForeground(0, QColor(C['fg_dim']))
            hdr.setFont(0, QFont('PingFang SC', 11))
            for fp in sorted(untagged, key=lambda x: Path(x).stat().st_mtime, reverse=True):
                fi = QTreeWidgetItem(hdr, [f"  {Path(fp).stem}"])
                fi.setData(0, Qt.ItemDataRole.UserRole, ('file', fp))
                fi.setForeground(0, QColor(C['fg_file']))

        self._restore_expanded(expanded)

    def _on_double_click(self, item: QTreeWidgetItem, col: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data[0] == 'file':
            self.file_selected.emit(data[1])

    def _save_expanded(self) -> set:
        result = set()
        def walk(item):
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == 'tag' and item.isExpanded():
                result.add(data[1])
            for i in range(item.childCount()):
                walk(item.child(i))
        for i in range(self.topLevelItemCount()):
            walk(self.topLevelItem(i))
        return result

    def _restore_expanded(self, expanded: set):
        def walk(item):
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == 'tag':
                item.setExpanded(data[1] in expanded or True)  # 默认展开
            for i in range(item.childCount()):
                walk(item.child(i))
        for i in range(self.topLevelItemCount()):
            walk(self.topLevelItem(i))

    def _on_ctx(self, pos: QPoint):
        item = self.itemAt(pos)
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {C['bg_input']}; color: {C['fg']};
                border: 1px solid {C['border']}; border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{ padding: 6px 20px; border-radius: 4px; }}
            QMenu::item:selected {{ background: {C['bg_sel']}; }}
            QMenu::separator {{ background: {C['border']}; height: 1px; margin: 4px 8px; }}
        """)

        if item:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == 'tag':
                tag_path = data[1]
                tag_name = tag_path.split('/')[-1]

                # 重命名
                act = menu.addAction(f'重命名「{tag_name}」')
                act.triggered.connect(lambda: self._rename_tag(tag_path))

                # 合并到
                all_tags = self._collect_all_tags()
                if len(all_tags) > 1:
                    merge_menu = menu.addMenu('合并到')
                    merge_menu.setStyleSheet(menu.styleSheet())
                    for t in all_tags:
                        if t != tag_path:
                            a = merge_menu.addAction(t)
                            a.triggered.connect(
                                lambda _, s=tag_path, d=t: self._merge_tag(s, d))

                menu.addSeparator()

            elif data and data[0] == 'file':
                fp = data[1]
                act_reveal = menu.addAction('在 Finder 中显示')
                act_reveal.triggered.connect(
                    lambda checked=False, f=fp: subprocess.run(['open', '-R', f]))
                if fp in self.store.get_txt_files():
                    act_rm = menu.addAction('移除')
                    act_rm.triggered.connect(
                        lambda checked=False, f=fp: (self.store.remove_txt(f),
                                 self.window()._refresh_sidebar()))
                menu.addSeparator()

        menu.exec(self.mapToGlobal(pos))

    def _collect_all_tags(self) -> list[str]:
        result = []
        def walk(item):
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == 'tag':
                result.append(data[1])
            for i in range(item.childCount()):
                walk(item.child(i))
        for i in range(self.topLevelItemCount()):
            walk(self.topLevelItem(i))
        return result

    def _rename_tag(self, tag_path: str):
        old_name = tag_path.split('/')[-1]
        new_name, ok = QInputDialog.getText(
            self, '重命名标签', f'标签「{old_name}」新名称：', text=old_name)
        if ok and new_name.strip() and new_name.strip() != old_name:
            self.tag_rename.emit(tag_path, new_name.strip())

    def _merge_tag(self, src: str, dst: str):
        ok = QMessageBox.question(
            self, '合并标签',
            f'将所有 #{src} 替换为 #{dst}？\n此操作会修改 .txt 文件内容。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ok == QMessageBox.StandardButton.Yes:
            self.tag_merge.emit(src, dst)


# ── 搜索栏 ────────────────────────────────────────────────────────────────

class SearchBar(QFrame):
    search   = pyqtSignal(str)
    closed   = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: {C['bg_input']};
                border-top: 1px solid {C['border']};
            }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)

        self._input = QLineEdit()
        self._input.setPlaceholderText('搜索…')
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {C['bg']}; color: {C['fg']};
                border: none; border-radius: 4px;
                padding: 6px 10px; font-size: 14px;
            }}
        """)
        self._input.returnPressed.connect(lambda: self.search.emit(self._input.text()))
        self._input.textChanged.connect(lambda t: self.search.emit(t) if len(t) >= 2 else None)
        lay.addWidget(self._input)

        self._count_lbl = QLabel('')
        self._count_lbl.setStyleSheet(f"color: {C['fg_dim']}; font-size: 12px;")
        lay.addWidget(self._count_lbl)

        close = QPushButton('✕')
        close.setFixedSize(24, 24)
        close.setStyleSheet(
            f"background: transparent; color: {C['fg_dim']}; border: none;")
        close.clicked.connect(self.closed.emit)
        lay.addWidget(close)

    def focus(self):
        self._input.setFocus()
        self._input.selectAll()

    def set_count(self, n: int):
        self._count_lbl.setText(f'{n} 处' if n else '')


# ── 主窗口 ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('purple loop')
        self.resize(1280, 800)
        self.setAcceptDrops(True)

        self.store = FileStore(DATA_FILE)
        self._fp:  str | None = None
        self._search_matches: list = []
        self._search_idx = -1
        self._pending_annot_id: str | None = None  # 工具条对应的标注 id

        self._load_fonts()
        self._build_ui()
        self._build_menu()
        self._refresh_sidebar()
        self._apply_theme()

    # ── 字体 ──────────────────────────────────────────────────
    def _load_fonts(self):
        if FONTS_DIR.exists():
            for f in FONTS_DIR.glob('*.ttf'):
                QFontDatabase.addApplicationFont(str(f))

    # ── UI ────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 主分割：侧栏 | 内容区
        self._split = QSplitter(Qt.Orientation.Horizontal)
        self._split.setHandleWidth(1)
        self._split.setStyleSheet(
            f"QSplitter::handle {{ background: {C['border']}; }}")
        root.addWidget(self._split)

        # ── 左侧栏 ─────────────────────────────────────────────
        sidebar_wrap = QWidget()
        sidebar_wrap.setMinimumWidth(180)
        sidebar_wrap.setMaximumWidth(320)
        sidebar_wrap.setStyleSheet(f"background: {C['bg_sidebar']};")
        sw_lay = QVBoxLayout(sidebar_wrap)
        sw_lay.setContentsMargins(0, 0, 0, 0)
        sw_lay.setSpacing(0)

        # 侧栏顶栏
        _top = QFrame()
        _top.setFixedHeight(48)
        _top.setStyleSheet(
            f"background: {C['bg_sidebar']}; border-bottom: 1px solid {C['border']};")
        _top_lay = QHBoxLayout(_top)
        _top_lay.setContentsMargins(12, 0, 8, 0)
        _lbl = QLabel('purple loop')
        _lbl.setStyleSheet(
            f"color: {C['fg_dim']}; font-size: 13px; font-weight: bold;")
        _top_lay.addWidget(_lbl)
        _top_lay.addStretch()
        sw_lay.addWidget(_top)

        self._sidebar = Sidebar(self.store)
        self._sidebar.file_selected.connect(self._open_file)
        self._sidebar.tag_rename.connect(self._rename_tag)
        self._sidebar.tag_merge.connect(self._merge_tag)
        sw_lay.addWidget(self._sidebar)

        self._split.addWidget(sidebar_wrap)

        # ── 右侧内容区 ─────────────────────────────────────────
        right_wrap = QWidget()
        right_lay  = QVBoxLayout(right_wrap)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        # 内容分割：编辑区 | 标注面板
        self._content_split = QSplitter(Qt.Orientation.Horizontal)
        self._content_split.setHandleWidth(1)
        self._content_split.setStyleSheet(
            f"QSplitter::handle {{ background: {C['border']}; }}")

        # 编辑器堆叠
        editor_wrap = QWidget()
        ew_lay = QVBoxLayout(editor_wrap)
        ew_lay.setContentsMargins(0, 0, 0, 0)
        ew_lay.setSpacing(0)

        self._stack = QStackedWidget()
        self._txt_editor = TxtEditor(self.store)
        self._txt_editor.mouse_released.connect(self._on_mouse_released)
        self._txt_editor._save_timer.timeout.connect(self._refresh_sidebar)
        self._empty_lbl  = QLabel('将文件拖入此处，或双击左侧文件打开')
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(
            f"color: {C['fg_dim']}; font-size: 16px; background: {C['bg']};")

        self._stack.addWidget(self._empty_lbl)
        self._stack.addWidget(self._txt_editor)
        ew_lay.addWidget(self._stack, 1)

        # 搜索栏
        self._search_bar = SearchBar()
        self._search_bar.search.connect(self._do_search)
        self._search_bar.closed.connect(self._close_search)
        self._search_bar.hide()
        ew_lay.addWidget(self._search_bar)

        # 备注栏
        self._note_bar = NoteBar(self.store)
        self._note_bar.saved.connect(lambda: self._annot_panel.refresh(self._fp))
        ew_lay.addWidget(self._note_bar)

        self._content_split.addWidget(editor_wrap)

        # 标注面板
        self._annot_panel = AnnotPanel(self.store)
        self._annot_panel.jump_to.connect(self._jump_to_annot)
        self._annot_panel.delete.connect(self._delete_annot_by_id)
        self._annot_panel.setMinimumWidth(160)
        self._annot_panel.setMaximumWidth(300)
        self._content_split.addWidget(self._annot_panel)
        self._content_split.setSizes([1120, 0])
        self._annot_panel.hide()   # 默认隐藏

        right_lay.addWidget(self._content_split, 1)
        self._split.addWidget(right_wrap)
        self._split.setSizes([240, 1040])

        # 浮动标注工具条
        self._annot_bar = AnnotBar()
        self._annot_bar.annotate.connect(self._do_annotate)
        self._annot_bar.label_requested.connect(self._request_label)
        self._annot_bar.remove.connect(self._do_remove_annot)
        self._annot_bar.hide()

        # 状态栏
        self.statusBar().setStyleSheet(
            f"background: {C['bg_input']}; color: {C['fg_dim']}; font-size: 12px;")

        # 呼吸灯：状态栏文字颜色缓慢呼吸
        import math
        self._breath_step = 0
        self._breath_timer = QTimer(self)
        self._breath_timer.setInterval(50)
        self._breath_timer.timeout.connect(self._breathe)
        self._breath_timer.start()

    def _breathe(self):
        import math
        self._breath_step += 1
        # 6秒一个周期，在 #3a3a3a 和 #6e6e6e 之间缓慢变化
        val = (math.sin(self._breath_step * 0.05) + 1) / 2
        v = int(0x3a + val * 0x34)
        color = f"#{v:02x}{v:02x}{v:02x}"
        self.statusBar().setStyleSheet(
            f"background: {C['bg_input']}; color: {color}; font-size: 12px;")

    # ── 菜单 ──────────────────────────────────────────────────
    def _build_menu(self):
        mb = self.menuBar()
        mb.setStyleSheet(f"""
            QMenuBar {{
                background: {C['bg_sidebar']}; color: {C['fg_tag']};
            }}
            QMenuBar::item:selected {{ background: {C['bg_sel']}; }}
        """)
        _ms = f"""
            QMenu {{
                background: {C['bg_input']}; color: {C['fg']};
                border: 1px solid {C['border']}; border-radius: 6px; padding: 4px;
            }}
            QMenu::item {{ padding: 6px 20px; border-radius: 4px; }}
            QMenu::item:selected {{ background: {C['bg_sel']}; }}
            QMenu::separator {{ background: {C['border']}; height: 1px; margin: 4px 8px; }}
        """

        def _act(menu, label, slot, shortcut=None):
            a = QAction(label, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            menu.addAction(a)
            return a

        # 文件
        fm = mb.addMenu('文件')
        fm.setStyleSheet(_ms)
        fm.addSeparator()
        _act(fm, '保存', self._save, 'Ctrl+S')
        fm.addSeparator()
        _act(fm, '退出', self.close)

        # 标注
        am = mb.addMenu('标注')
        am.setStyleSheet(_ms)
        for key, atype, label in [
            ('1', 'hl_yellow', '黄色高亮'),
            ('2', 'hl_green',  '绿色高亮'),
            ('3', 'hl_pink',   '粉色高亮'),
            ('4', 'hl_purple', '紫色高亮'),
        ]:
            _act(am, label, lambda t=atype: self._do_annotate(t), f'Ctrl+{key}')
        am.addSeparator()
        _act(am, '加粗', lambda: self._do_annotate('bold'), 'Ctrl+B')
        _act(am, '下划线', lambda: self._do_annotate('underline'), 'Ctrl+U')
        am.addSeparator()
        _act(am, '删除光标处标注', self._do_remove_annot)

        # 视图
        vm = mb.addMenu('视图')
        vm.setStyleSheet(_ms)
        _act(vm, '搜索', self._toggle_search, 'Ctrl+F')
        vm.addSeparator()
        self._annot_panel_action = QAction('显示标注面板', self)
        self._annot_panel_action.setShortcut(QKeySequence('Ctrl+\\'))
        self._annot_panel_action.setCheckable(True)
        self._annot_panel_action.setChecked(False)
        self._annot_panel_action.triggered.connect(self._toggle_annot_panel)
        vm.addAction(self._annot_panel_action)
        vm.addSeparator()
        _act(vm, '刷新侧栏', self._refresh_sidebar, 'F5')

    def _apply_theme(self):
        self.setStyleSheet(f"QMainWindow {{ background: {C['bg']}; }}")
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(C['bg']))
        self.setPalette(pal)

    # ── 侧栏刷新 ──────────────────────────────────────────────
    def _refresh_sidebar(self):
        txt_files = self.store.get_txt_files()
        self._sidebar.refresh(txt_files)

    # ── 文件操作 ──────────────────────────────────────────────
    def _open_file(self, path: str):
        self._fp = path
        self._annot_bar.hide()
        self._note_bar.hide()
        self._txt_editor.load_file(path)
        self._annot_panel.refresh(path)
        self._stack.setCurrentWidget(self._txt_editor)
        self.statusBar().showMessage(Path(path).name, 0)

    def _save(self):
        self._txt_editor.save()
        self._refresh_sidebar()
        self.statusBar().showMessage('已保存', 2000)

    def _on_editor_saved(self):
        """编辑器自动保存后刷新侧栏"""
        self._refresh_sidebar()

    # ── 标签操作（批量替换 txt 内容）────────────────────────
    def _rename_tag(self, old_path: str, new_name: str):
        """改写所有 .txt 文件中的 #old_path → #new_path"""
        parent = '/'.join(old_path.split('/')[:-1])
        new_path = f"{parent}/{new_name}" if parent else new_name
        old_tag = f"#{old_path}"
        new_tag = f"#{new_path}"

        changed = 0
        for fp_str in self.store.get_txt_files():
            fp = Path(fp_str)
            try:
                text = fp.read_text('utf-8')
                if old_tag in text:
                    fp.write_text(text.replace(old_tag, new_tag), 'utf-8')
                    changed += 1
            except Exception:
                pass
        self._refresh_sidebar()
        self.statusBar().showMessage(
            f'已将 #{old_path} 重命名为 #{new_path}，影响 {changed} 个文件', 4000)

    def _merge_tag(self, src: str, dst: str):
        """将 #src 全部替换为 #dst"""
        changed = 0
        for fp_str in self.store.get_txt_files():
            fp = Path(fp_str)
            try:
                text = fp.read_text('utf-8')
                if f'#{src}' in text:
                    fp.write_text(text.replace(f'#{src}', f'#{dst}'), 'utf-8')
                    changed += 1
            except Exception:
                pass
        self._refresh_sidebar()
        self.statusBar().showMessage(
            f'已将 #{src} 合并到 #{dst}，影响 {changed} 个文件', 4000)

    # ── 标注操作 ──────────────────────────────────────────────
    def _on_mouse_released(self):
        """鼠标松开后检查选区，选中 ≥5 字才弹工具条"""
        if not (self._fp and self._fp.endswith('.txt')):
            self._annot_bar.hide()
            return
        cur = self._txt_editor.textCursor()
        if not cur.hasSelection():
            self._annot_bar.hide()
            return
        sel_text = cur.selectedText().replace('\u2029', '\n').strip()
        if len(sel_text) < 5:
            # 短选区：只是阅读定位，不弹工具条
            self._annot_bar.hide()
            return
        # 定位到选区起点上方
        start = min(cur.position(), cur.anchor())
        tmp = QTextCursor(self._txt_editor.document())
        tmp.setPosition(start)
        rect = self._txt_editor.cursorRect(tmp)
        gp   = self._txt_editor.mapToGlobal(rect.topLeft())
        sh   = self._annot_bar.sizeHint()
        x    = gp.x() - sh.width() // 2
        y    = gp.y() - sh.height() - 12
        scr  = QApplication.primaryScreen().geometry()
        x    = max(4, min(x, scr.width()  - sh.width()  - 4))
        y    = max(4, min(y, scr.height() - sh.height() - 4))
        self._annot_bar.move(x, y)
        self._annot_bar.show()
        # 记录光标处已有的标注（供 ✕ 删除用）
        a = self._txt_editor.annot_at_cursor()
        self._pending_annot_id = a['id'] if a else None

    def _do_annotate(self, atype: str):
        annot = self._txt_editor.annotate(atype)
        if annot:
            self._annot_bar.hide()
            self._annot_panel.refresh(self._fp)

    def _request_label(self):
        """点击 # 按钮后：先关浮动条，再弹输入框（IME 在 Popup 里不工作）"""
        # 保存当前选区
        cur = self._txt_editor.textCursor()
        if not cur.hasSelection():
            self._annot_bar.hide()
            return
        saved_anchor   = cur.anchor()
        saved_position = cur.position()
        self._annot_bar.hide()

        label_text, ok = QInputDialog.getText(
            self, '文字标签', '标签名：')
        if not ok or not label_text.strip():
            return

        # 恢复选区后应用标签
        c = self._txt_editor.textCursor()
        c.setPosition(saved_anchor)
        c.setPosition(saved_position, QTextCursor.MoveMode.KeepAnchor)
        self._txt_editor.setTextCursor(c)
        annot = self._txt_editor.annotate('label', label_text.strip())
        if annot:
            self._annot_panel.refresh(self._fp)

    def _do_remove_annot(self):
        """工具条 ✕：优先用记录的 id，其次用光标位置"""
        if self._pending_annot_id and self._fp:
            self._delete_annot_by_id(self._pending_annot_id)
        else:
            self._txt_editor.remove_at_cursor()
            self._annot_panel.refresh(self._fp)
        self._annot_bar.hide()
        self._pending_annot_id = None

    def _delete_annot_by_id(self, annot_id: str):
        if not self._fp:
            return
        self.store.remove_annotation(self._fp, annot_id)
        self._txt_editor._apply_annotations()
        self._annot_panel.refresh(self._fp)

    def _jump_to_annot(self, annot_id: str):
        self._txt_editor.jump_to_annot(annot_id)
        # 显示备注栏
        for a in self.store.get_annotations(self._fp or ''):
            if a['id'] == annot_id:
                self._note_bar.show_for(a, self._fp)
                break

    def _toggle_annot_panel(self):
        visible = self._annot_panel_action.isChecked()
        if visible:
            self._annot_panel.show()
            self._content_split.setSizes([900, 220])
            self._annot_panel.refresh(self._fp)
        else:
            self._annot_panel.hide()
            self._content_split.setSizes([1120, 0])

    # ── 搜索 ──────────────────────────────────────────────────
    def _toggle_search(self):
        if self._search_bar.isVisible():
            self._close_search()
        else:
            self._search_bar.show()
            self._search_bar.focus()

    def _close_search(self):
        self._search_bar.hide()
        self._clear_search_hl()
        if self._stack.currentWidget() == self._txt_editor:
            self._txt_editor.setFocus()

    def _do_search(self, kw: str):
        self._clear_search_hl()
        if not kw or self._stack.currentWidget() != self._txt_editor:
            self._search_bar.set_count(0)
            return
        doc  = self._txt_editor.document()
        fmt  = QTextCharFormat()
        fmt.setBackground(QColor('#3a2e00'))
        fmt.setForeground(QColor('#e8c870'))

        cursor = QTextCursor(doc)
        self._search_matches = []
        while True:
            cursor = doc.find(kw, cursor,
                              QTextDocument.FindFlag.FindCaseSensitively)
            if cursor.isNull():
                break
            cursor.mergeCharFormat(fmt)
            self._search_matches.append(cursor.position() - len(kw))

        self._search_bar.set_count(len(self._search_matches))
        if self._search_matches:
            c = QTextCursor(doc)
            c.setPosition(self._search_matches[0])
            self._txt_editor.setTextCursor(c)
            self._txt_editor.ensureCursorVisible()

    def _clear_search_hl(self):
        if self._fp:
            self._txt_editor._apply_annotations()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self._search_bar.isVisible():
                self._close_search()
            elif self._note_bar.isVisible():
                self._note_bar.hide()
        super().keyPressEvent(event)

    # ── 拖放文件 ──────────────────────────────────────────────
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            exts = {Path(u.toLocalFile()).suffix.lower() for u in urls}
            if exts & {'.txt'}:
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            fp  = url.toLocalFile()
            ext = Path(fp).suffix.lower()
            try:
                if ext == '.txt':
                    self.store.add_txt(fp)
                    self._open_file(fp)
            except Exception as e:
                self.statusBar().showMessage(f'无法打开：{e}', 3000)
        self._refresh_sidebar()
        event.acceptProposedAction()

    def closeEvent(self, event):
        self._txt_editor.save()
        # 保存当前阅读位置
        if self._fp:
            self.store.set_read_pos(
                self._fp, self._txt_editor.verticalScrollBar().value())
        super().closeEvent(event)


# ── 入口 ──────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName('purple loop')

    # 加载字体
    if FONTS_DIR.exists():
        for f in FONTS_DIR.glob('*.ttf'):
            QFontDatabase.addApplicationFont(str(f))

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
