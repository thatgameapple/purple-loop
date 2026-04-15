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

try:
    import fitz          # pymupdf
    _HAS_PDF = True
except ImportError:
    _HAS_PDF = False

try:
    import docx          # python-docx
    _HAS_DOCX = True
except ImportError:
    _HAS_DOCX = False

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
    'fg':          '#dfe3df',
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
        self.data: dict = {'imports': {}, 'annotations': {}, 'config': {}}
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

    # ── 导入记录 ──────────────────────────────────────────────
    def add_import(self, path: str, ftype: str):
        self.data.setdefault('imports', {})[path] = ftype
        self.save()

    def remove_import(self, path: str):
        self.data.get('imports', {}).pop(path, None)
        self.save()

    def get_imports(self) -> dict:
        return dict(self.data.get('imports', {}))

    # ── 单独拖入的 .txt 文件 ───────────────────────────────
    def add_txt(self, path: str):
        lst = self.data.setdefault('txt_files', [])
        if path not in lst:
            lst.append(path)
            self.save()

    def get_txt_files(self) -> list:
        return [p for p in self.data.get('txt_files', []) if Path(p).exists()]

    # ── 配置 ──────────────────────────────────────────────────
    def get_config(self, key, default=None):
        return self.data.get('config', {}).get(key, default)

    def set_config(self, key, value):
        self.data.setdefault('config', {})[key] = value
        self.save()

    # ── 标注 ──────────────────────────────────────────────────
    def get_annotations(self, filepath: str) -> list:
        return sorted(
            self.data.get('annotations', {}).get(filepath, []),
            key=lambda a: a['start'])

    def add_annotation(self, filepath: str, atype: str,
                       start: int, end: int, text: str) -> dict:
        annot = {
            'id':         str(uuid.uuid4()),
            'type':       atype,
            'start':      start,
            'end':        end,
            'text':       text,
            'note':       '',
            'created_at': datetime.now().isoformat(timespec='seconds'),
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
    annotate = pyqtSignal(str)
    remove   = pyqtSignal()

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
        bg, dot = C.get(annot['type'], (C['bg_input'], C['accent']))
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {C['bg_input']}; border-radius: 6px;
                border-left: 3px solid {dot or C['accent']};
            }}
        """)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        # 类型标签
        type_lbl = QLabel(ANNOT_LABEL.get(annot['type'], annot['type']))
        type_lbl.setStyleSheet(f"color: {dot or C['accent']}; font-size: 11px;")
        lay.addWidget(type_lbl)

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

        aid = annot['id']
        card.mousePressEvent = lambda e, a=aid: self.jump_to.emit(a)
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
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C['bg']}; color: {C['fg']};
                border: none; padding: 40px 60px;
                selection-background-color: #7c6af7;
                selection-color: #ffffff;
            }}
        """)
        # 用 QPalette 强制紫色选区（覆盖 macOS 系统色）
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Highlight,        QColor('#7c6af7'))
        pal.setColor(QPalette.ColorRole.HighlightedText,  QColor('#ffffff'))
        self.setPalette(pal)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setReadOnly(False)

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
        # 行间距
        fmt = self.document().defaultTextOption()
        self.document().setDefaultTextOption(fmt)

    def load_file(self, path: str):
        self._fp      = path
        self._loading = True
        text = Path(path).read_text('utf-8')
        self.setPlainText(text)
        self._loading = False
        self._apply_annotations()

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
        bg, fg = C.get(annot['type'], (None, None))
        if bg:
            fmt.setBackground(QColor(bg))
        if fg and annot['type'] not in ('bold', 'underline'):
            fmt.setForeground(QColor(fg))
        if annot['type'] == 'bold':
            fmt.setFontWeight(QFont.Weight.Bold)
        if annot['type'] == 'underline':
            fmt.setFontUnderline(True)
        cur.mergeCharFormat(fmt)

    def annotate(self, atype: str) -> dict | None:
        if not self._fp:
            return None
        cur = self.textCursor()
        if not cur.hasSelection():
            return None
        start = min(cur.position(), cur.anchor())
        end   = max(cur.position(), cur.anchor())
        text  = cur.selectedText().replace('\u2029', '\n')
        annot = self.store.add_annotation(self._fp, atype, start, end, text)
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
            QMenu::item:selected {{ background: #2a3a5a; color: {C['fg']}; }}
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


# ── PDF 查看器 ────────────────────────────────────────────────────────────

class PdfViewer(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet(f"background: {C['bg']}; border: none;")
        inner = QWidget()
        inner.setStyleSheet(f"background: {C['bg']};")
        self._layout = QVBoxLayout(inner)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._layout.setSpacing(12)
        self._layout.setContentsMargins(40, 40, 40, 40)
        self.setWidget(inner)

    def load(self, path: str):
        # 清空
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not _HAS_PDF:
            lbl = QLabel("需要安装 pymupdf\npip install pymupdf")
            lbl.setStyleSheet(f"color: {C['fg_dim']}; font-size: 16px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._layout.addWidget(lbl)
            return

        doc = fitz.open(path)
        for page in doc:
            mat  = fitz.Matrix(2, 2)        # 2× 分辨率
            pix  = page.get_pixmap(matrix=mat)
            img  = QImage(pix.samples, pix.width, pix.height,
                          pix.stride, QImage.Format.Format_RGB888)
            lbl  = QLabel()
            pm   = QPixmap.fromImage(img)
            lbl.setPixmap(pm)
            lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lbl.setStyleSheet("background: transparent;")
            # 缩放到 800px 宽
            if pm.width() > 800:
                lbl.setPixmap(pm.scaledToWidth(
                    800, Qt.TransformationMode.SmoothTransformation))
            self._layout.addWidget(lbl)
        doc.close()


# ── Word 查看器 ───────────────────────────────────────────────────────────

class WordViewer(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        f = QFont('LXGW WenKai', 18)
        if not f.exactMatch():
            f = QFont('PingFang SC', 18)
        self.setFont(f)
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C['bg']}; color: {C['fg']};
                border: none; padding: 40px 60px;
            }}
        """)

    def load(self, path: str):
        if not _HAS_DOCX:
            self.setPlainText("需要安装 python-docx\npip install python-docx")
            return
        doc  = docx.Document(path)
        text = '\n'.join(p.text for p in doc.paragraphs)
        self.setPlainText(text)


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
        imports    = self.store.get_imports()
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

        # ── 导入文件（Word / PDF）────────────────────────────
        if imports:
            hdr2 = QTreeWidgetItem(self.invisibleRootItem(), ['导入文件'])
            hdr2.setData(0, Qt.ItemDataRole.UserRole, ('header', ''))
            hdr2.setForeground(0, QColor(C['fg_dim']))
            hdr2.setFont(0, QFont('PingFang SC', 11))
            for fp, ftype in imports.items():
                icon = '📄' if ftype == 'pdf' else '📝'
                fi = QTreeWidgetItem(hdr2, [f"  {icon} {Path(fp).stem}"])
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
                    lambda: subprocess.run(['open', '-R', fp]))
                if fp in self.store.get_imports():
                    act_rm = menu.addAction('从导入列表移除')
                    act_rm.triggered.connect(
                        lambda: (self.store.remove_import(fp),
                                 self.window()._refresh_sidebar()))
                menu.addSeparator()

        # 通用操作
        act_scan = menu.addAction('设置 TXT 目录…')
        act_scan.triggered.connect(self.window()._set_txt_dir)
        act_import = menu.addAction('导入 Word / PDF…')
        act_import.triggered.connect(self.window()._import_file)

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
        _import_btn = QPushButton('+')
        _import_btn.setFixedSize(28, 28)
        _import_btn.setToolTip('导入文件 / 设置目录')
        _import_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C['bg_input']}; color: {C['fg_dim']};
                border: none; border-radius: 14px; font-size: 18px;
            }}
            QPushButton:hover {{ background: {C['bg_sel']}; color: {C['fg']}; }}
        """)
        _import_btn.clicked.connect(self._show_import_menu)
        _top_lay.addWidget(_import_btn)
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
        self._pdf_viewer = PdfViewer()
        self._word_viewer = WordViewer()
        self._empty_lbl  = QLabel('将文件拖入此处，或双击左侧文件打开')
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(
            f"color: {C['fg_dim']}; font-size: 16px; background: {C['bg']};")

        self._stack.addWidget(self._empty_lbl)
        self._stack.addWidget(self._txt_editor)
        self._stack.addWidget(self._pdf_viewer)
        self._stack.addWidget(self._word_viewer)
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
        self._annot_panel.setMinimumWidth(160)
        self._annot_panel.setMaximumWidth(300)
        self._content_split.addWidget(self._annot_panel)
        self._content_split.setSizes([900, 220])

        right_lay.addWidget(self._content_split, 1)
        self._split.addWidget(right_wrap)
        self._split.setSizes([240, 1040])

        # 浮动标注工具条
        self._annot_bar = AnnotBar()
        self._annot_bar.annotate.connect(self._do_annotate)
        self._annot_bar.remove.connect(self._do_remove_annot)
        self._annot_bar.hide()

        # 状态栏
        self.statusBar().setStyleSheet(
            f"background: {C['bg_input']}; color: {C['fg_dim']}; font-size: 12px;")

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
        _act(fm, '设置 TXT 目录…', self._set_txt_dir)
        _act(fm, '导入 Word / PDF…', self._import_file)
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
        _act(vm, '刷新侧栏', self._refresh_sidebar, 'F5')

    def _apply_theme(self):
        self.setStyleSheet(f"QMainWindow {{ background: {C['bg']}; }}")
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(C['bg']))
        self.setPalette(pal)

    # ── 侧栏刷新 ──────────────────────────────────────────────
    def _refresh_sidebar(self):
        txt_files = []
        # 1. txt_dir 目录扫描
        txt_dir = self.store.get_config('txt_dir')
        if txt_dir and Path(txt_dir).exists():
            txt_files += [str(f) for f in Path(txt_dir).rglob('*.txt')
                          if not f.name.startswith('.')]
        # 2. 单独拖入的 .txt 文件
        for p in self.store.get_txt_files():
            if p not in txt_files:
                txt_files.append(p)
        self._sidebar.refresh(txt_files)

    # ── 文件操作 ──────────────────────────────────────────────
    def _show_import_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {C['bg_input']}; color: {C['fg']};
                border: 1px solid {C['border']}; border-radius: 6px; padding: 4px;
            }}
            QMenu::item {{ padding: 6px 20px; border-radius: 4px; }}
            QMenu::item:selected {{ background: {C['bg_sel']}; }}
        """)
        a1 = QAction('设置 TXT 目录…', self)
        a1.triggered.connect(self._set_txt_dir)
        menu.addAction(a1)
        a2 = QAction('导入 Word / PDF…', self)
        a2.triggered.connect(self._import_file)
        menu.addAction(a2)
        btn = self.sender()
        menu.exec(btn.mapToGlobal(QPoint(0, btn.height())))

    def _set_txt_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, '选择 TXT 文件目录',
            self.store.get_config('txt_dir') or str(Path.home()))
        if d:
            self.store.set_config('txt_dir', d)
            self._refresh_sidebar()
            self.statusBar().showMessage(f'TXT 目录：{d}', 3000)

    def _import_file(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, '导入文件', str(Path.home()),
            'Word / PDF (*.docx *.doc *.pdf)')
        for p in paths:
            ext = Path(p).suffix.lower()
            ftype = 'pdf' if ext == '.pdf' else 'docx'
            self.store.add_import(p, ftype)
        if paths:
            self._refresh_sidebar()

    def _open_file(self, path: str):
        self._fp = path
        ext = Path(path).suffix.lower()
        self._annot_bar.hide()
        self._note_bar.hide()

        if ext == '.txt':
            self._txt_editor.load_file(path)
            self._stack.setCurrentWidget(self._txt_editor)
        elif ext == '.pdf':
            self._pdf_viewer.load(path)
            self._stack.setCurrentWidget(self._pdf_viewer)
        else:  # docx
            self._word_viewer.load(path)
            self._stack.setCurrentWidget(self._word_viewer)

        self._annot_panel.refresh(path if ext == '.txt' else None)
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

        txt_dir = self.store.get_config('txt_dir')
        if not txt_dir:
            return
        changed = 0
        for fp in Path(txt_dir).rglob('*.txt'):
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
        txt_dir = self.store.get_config('txt_dir')
        if not txt_dir:
            return
        changed = 0
        for fp in Path(txt_dir).rglob('*.txt'):
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

    def _do_annotate(self, atype: str):
        annot = self._txt_editor.annotate(atype)
        if annot:
            self._annot_bar.hide()
            self._annot_panel.refresh(self._fp)

    def _do_remove_annot(self):
        self._txt_editor.remove_at_cursor()
        self._annot_bar.hide()
        self._annot_panel.refresh(self._fp)

    def _jump_to_annot(self, annot_id: str):
        self._txt_editor.jump_to_annot(annot_id)
        # 显示备注栏
        for a in self.store.get_annotations(self._fp or ''):
            if a['id'] == annot_id:
                self._note_bar.show_for(a, self._fp)
                break

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
            if exts & {'.txt', '.pdf', '.docx', '.doc'}:
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            fp  = url.toLocalFile()
            ext = Path(fp).suffix.lower()
            if ext == '.txt':
                self.store.add_txt(fp)   # 记录到持久化列表
                self._open_file(fp)
            elif ext in ('.pdf', '.docx', '.doc'):
                ftype = 'pdf' if ext == '.pdf' else 'docx'
                self.store.add_import(fp, ftype)
                self._open_file(fp)
        self._refresh_sidebar()
        event.acceptProposedAction()

    def closeEvent(self, event):
        self._txt_editor.save()
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
