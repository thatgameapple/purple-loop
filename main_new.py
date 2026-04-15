#!/usr/bin/env python3
"""purple loop v2 — PyQt6 + inline #tag"""

import sys, os, json, re, uuid, subprocess
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QTreeWidget, QTreeWidgetItem,
    QStackedWidget, QTextEdit, QScrollArea, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QFrame, QMenu, QFileDialog, QInputDialog,
    QMessageBox, QSizePolicy, QAbstractScrollArea, QDialog, QButtonGroup,
    QProgressBar, QComboBox
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
    'accent':      '#7c6fa8',
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

    def clear_all_annotations(self, filepath: str):
        if filepath in self.data.get('annotations', {}):
            self.data['annotations'][filepath] = []
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

_FILTER_DEFS = [
    # (type_key_or_None, dot_color,  tooltip)
    (None,        '#e8e8e8', '全部'),
    ('hl_yellow', '#e8c870', '黄色'),
    ('hl_green',  '#5ec87a', '绿色'),
    ('hl_pink',   '#e86090', '粉色'),
    ('hl_purple', '#a878f0', '紫色'),
]


class AnnotPanel(QWidget):
    jump_to   = pyqtSignal(str)   # annot_id
    delete    = pyqtSignal(str)   # annot_id
    clear_all = pyqtSignal()      # 清除所有标注

    def __init__(self, store: FileStore, parent=None):
        super().__init__(parent)
        self.store  = store
        self._fp    = None
        self._cards = {}
        self._filter: str | None = None   # None = 全部

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 过滤圆点栏 ───────────────────────────────
        filter_bar = QFrame()
        filter_bar.setFixedHeight(34)
        filter_bar.setStyleSheet(
            f"background: {C['bg_sidebar']}; border-bottom: 1px solid {C['border']};")
        fb_lay = QHBoxLayout(filter_bar)
        fb_lay.setContentsMargins(10, 0, 10, 0)
        fb_lay.setSpacing(8)

        self._filter_btns: dict[str, QPushButton] = {}
        for ftype, color, tip in _FILTER_DEFS:
            btn = QPushButton()
            btn.setFixedSize(12, 12)
            btn.setCheckable(True)
            btn.setToolTip(tip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color}; border-radius: 6px;
                    border: 1.5px solid transparent;
                }}
                QPushButton:checked {{
                    border: 1.5px solid white;
                }}
                QPushButton:!checked {{
                    background: {color};
                    opacity: 0.5;
                }}
            """)
            btn.clicked.connect(lambda _, t=ftype: self._set_filter(t))
            key = str(ftype)
            self._filter_btns[key] = btn
            fb_lay.addWidget(btn)
        fb_lay.addStretch()

        # 清空全部标注按钮
        clear_btn = QPushButton('清空')
        clear_btn.setFixedHeight(20)
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setToolTip('删除当前文件所有标注')
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C['fg_dim']};
                border: none; font-size: 11px; padding: 0 4px;
            }}
            QPushButton:hover {{ color: #ff6b6b; }}
        """)
        clear_btn.clicked.connect(self._request_clear)
        fb_lay.addWidget(clear_btn)
        root.addWidget(filter_bar)

        # 默认选"全部"
        self._filter_btns['None'].setChecked(True)

        # ── 卡片滚动区 ───────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: {C['bg_sidebar']}; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: 3px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: #444448; border-radius: 1px; min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{ background: #606064; }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)

        inner = QWidget()
        inner.setStyleSheet(f"background: {C['bg_sidebar']};")
        self._layout = QVBoxLayout(inner)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(6)
        self._layout.addStretch()
        self._scroll.setWidget(inner)
        root.addWidget(self._scroll, 1)

    def _set_filter(self, ftype: str | None):
        self._filter = ftype
        for key, btn in self._filter_btns.items():
            btn.setChecked(key == str(ftype))
        self.refresh(self._fp)

    def _request_clear(self):
        if not self._fp:
            return
        n = len(self.store.get_annotations(self._fp))
        if n == 0:
            return
        reply = QMessageBox.question(
            self, '清除所有标注',
            f'删除当前文件全部 {n} 条标注？此操作不可撤销。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.clear_all.emit()

    def refresh(self, filepath: str | None):
        self._fp = filepath
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()
        if not filepath:
            return

        all_annots = self.store.get_annotations(filepath)
        if self._filter is not None:
            # 'label' 旧类型视为 hl_purple
            shown = [a for a in all_annots
                     if a['type'] == self._filter
                     or (self._filter == 'hl_purple' and a['type'] == 'label')]
        else:
            shown = all_annots

        for annot in shown:
            card = self._make_card(annot)
            self._layout.insertWidget(self._layout.count() - 1, card)
            self._cards[annot['id']] = card

    def _make_card(self, annot: dict) -> QFrame:
        # 兼容旧 'label' 类型
        if annot['type'] == 'label':
            dot = '#c4b0f8'
            bg_pill = '#1e1040'
        else:
            _, dot = C.get(annot['type'], (None, C['accent']))
            dot = dot or C['accent']
            bg_pill, _ = C.get(annot['type'], ('#1a1040', None))
            bg_pill = bg_pill or C['bg_sel']

        label_text = annot.get('label_text', '')
        card_label = label_text or ANNOT_LABEL.get(annot['type'], annot['type'])

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

        # 顶栏：类型标签 / 标签名 pill + 删除按钮
        top = QHBoxLayout()
        if label_text:
            type_lbl = QLabel(f'  # {card_label}  ')
            type_lbl.setStyleSheet(f"""
                background: {bg_pill}; color: {dot};
                border-radius: 3px; font-size: 11px; padding: 1px 0;
            """)
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


# ── 统一高亮器（#标签 + 标注颜色）────────────────────────────────────────
# 使用 QSyntaxHighlighter.setFormat()，仅在绘制时着色，完全不写入文档，
# 不触发 contentsChange，不会污染偏移量追踪，是 Qt6 官方推荐方案。

class DocHighlighter(QSyntaxHighlighter):
    """统一处理 #标签高亮 + 标注颜色，非破坏性渲染"""

    def __init__(self, doc, store: 'FileStore'):
        super().__init__(doc)
        self.store  = store
        self._fp: str | None = None
        self._tag_fmt = QTextCharFormat()
        self._tag_fmt.setForeground(QColor(C['accent']))

    def set_file(self, filepath: str | None):
        self._fp = filepath
        self.rehighlight()

    def _annot_fmt(self, annot: dict) -> QTextCharFormat:
        atype = annot['type']
        fmt = QTextCharFormat()
        if atype == 'label':
            fmt.setBackground(QColor('#1e1040'))
            fmt.setForeground(QColor('#c4b0f8'))
            fmt.setFontUnderline(True)
        else:
            bg, fg = C.get(atype, (None, None))
            if bg:
                fmt.setBackground(QColor(bg))
            if fg and atype not in ('bold', 'underline'):
                fmt.setForeground(QColor(fg))
            if atype == 'bold':
                fmt.setFontWeight(QFont.Weight.Bold)
            if atype == 'underline':
                fmt.setFontUnderline(True)
            if annot.get('label_text'):
                fmt.setFontUnderline(True)
        return fmt

    def highlightBlock(self, text: str):
        # 1. #标签高亮
        for m in TAG_RE.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._tag_fmt)

        # 2. 标注高亮
        if not self._fp:
            return
        block       = self.currentBlock()
        block_start = block.position()
        block_len   = len(text)

        for annot in self.store.get_annotations(self._fp):
            a_s = annot['start']
            a_e = annot['end']
            if a_s >= a_e:
                continue
            # 不与本块重叠
            if a_e <= block_start or a_s >= block_start + block_len:
                continue
            lo = max(0, a_s - block_start)
            hi = min(block_len, a_e - block_start)
            if lo >= hi:
                continue
            self.setFormat(lo, hi - lo, self._annot_fmt(annot))


# ── txt 编辑器 ───────────────────────────────────────────────────────────

class TxtEditor(QTextEdit):
    mouse_released = pyqtSignal()   # 鼠标松开时通知主窗口检查选区

    def __init__(self, store: FileStore, parent=None):
        super().__init__(parent)
        self.store    = store
        self._fp: str | None = None
        self._loading = False
        self._highlighter = DocHighlighter(self.document(), store)

        # 字体
        self._set_font()
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C['bg']}; color: {C['fg']};
                border: none; padding: 56px 160px;
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

        # 右下角字数显示（呼吸灯）
        self._count_lbl = QLabel('', self)
        self._count_lbl.setFont(QFont('PingFang SC', 11))
        self._count_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._count_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.document().contentsChanged.connect(self._update_count)

        import math
        self._wc_step = 0
        self._wc_timer = QTimer(self)
        self._wc_timer.setInterval(50)
        self._wc_timer.timeout.connect(self._breathe_count)
        self._wc_timer.start()

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
        blk_fmt.setLineHeight(165, 1)       # 1.65 倍行距
        blk_fmt.setBottomMargin(8)          # 段落间距 0.5em（有层次但不散）
        cur.setBlockFormat(blk_fmt)

    def load_file(self, path: str):
        # 保存当前文件的阅读位置
        if self._fp:
            self.store.set_read_pos(self._fp, self.verticalScrollBar().value())

        self._fp      = path
        self._loading = True
        text = Path(path).read_text('utf-8')
        self.setPlainText(text)
        self._apply_line_spacing()   # setPlainText 会重置 block format
        self._loading = False
        # 通知高亮器切换文件（会自动 rehighlight，不写入文档）
        self._highlighter.set_file(path)

        # 恢复阅读位置（延迟到布局完成后）
        saved_pos = self.store.get_read_pos(path)
        def _restore():
            self.verticalScrollBar().setValue(saved_pos)
            # 通知主窗口更新进度条
            mw = self.window()
            if hasattr(mw, '_update_progress'):
                mw._update_progress()
        QTimer.singleShot(50, _restore)


    def _apply_annotations(self):
        """标注变更后触发重绘（高亮器不写入文档，直接 rehighlight 即可）"""
        self._highlighter.rehighlight()

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
        self._highlighter.rehighlight()
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
                # 让标注居中显示在阅读区
                rect = self.cursorRect()
                vp_h = self.viewport().height()
                offset = rect.center().y() - vp_h // 2
                sb = self.verticalScrollBar()
                sb.setValue(sb.value() + offset)
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

    def _update_count(self):
        n = len(self.toPlainText().replace('\n', '').replace(' ', ''))
        self._count_lbl.setText(f'{n} 字')
        self._position_count_lbl()

    def _position_count_lbl(self):
        lbl = self._count_lbl
        lbl.adjustSize()
        m = 14  # 离边角的距离
        lbl.move(self.width() - lbl.width() - m,
                 self.height() - lbl.height() - m)

    def _breathe_count(self):
        import math
        self._wc_step += 1
        val = (math.sin(self._wc_step * 0.05) + 1) / 2
        v = int(0x3a + val * 0x34)
        color = f"#{v:02x}{v:02x}{v:02x}"
        self._count_lbl.setStyleSheet(
            f"color: {color}; background: transparent;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_count_lbl()

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
            # Cmd+↑ 到顶，Cmd+↓ 到底
            if event.key() == Qt.Key.Key_Up:
                self.verticalScrollBar().setValue(0)
                c = QTextCursor(self.document())
                c.movePosition(QTextCursor.MoveOperation.Start)
                self.setTextCursor(c)
                return
            if event.key() == Qt.Key.Key_Down:
                self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
                c = QTextCursor(self.document())
                c.movePosition(QTextCursor.MoveOperation.End)
                self.setTextCursor(c)
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
        self._persist_key = 'sidebar_expanded'  # store config key

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
        self.itemExpanded.connect(self._on_expand_change)
        self.itemCollapsed.connect(self._on_expand_change)

        # 拖放
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)

    def _on_expand_change(self, _item=None):
        """展开/收起时保存状态到 store"""
        self.store.set_config(self._persist_key, list(self._save_expanded()))

    # ── 置顶标签 ──────────────────────────────────────────────
    def _get_pinned(self) -> list[str]:
        return self.store.get_config('pinned_tags', [])

    def _toggle_pin(self, tag_path: str):
        pinned = self._get_pinned()
        if tag_path in pinned:
            pinned.remove(tag_path)
        else:
            pinned.insert(0, tag_path)
        self.store.set_config('pinned_tags', pinned)
        self.window()._refresh_sidebar()

    def refresh(self, txt_files: list[str]):
        self._txt_files = txt_files
        # 优先用当前内存状态，其次从 store 读取持久状态
        expanded = self._save_expanded()
        if not expanded:
            saved = self.store.get_config(self._persist_key, None)
            if saved is not None:
                expanded = set(saved)
            else:
                expanded = None   # None = 首次，默认全展开
        self.clear()

        tag_tree = TagScanner.build_tree(txt_files)
        untagged = [f for f in txt_files if not TagScanner.scan(f)]
        pinned   = self._get_pinned()

        # ── 置顶标签区 ────────────────────────────────────────
        valid_pinned = [t for t in pinned if t in tag_tree]
        if valid_pinned:
            pin_hdr = QTreeWidgetItem(self.invisibleRootItem(), ['置顶标签'])
            pin_hdr.setData(0, Qt.ItemDataRole.UserRole, ('header', '__pinned__'))
            pin_hdr.setForeground(0, QColor(C['fg_dim']))
            pin_hdr.setFont(0, QFont('PingFang SC', 11))
            pin_hdr.setFlags(pin_hdr.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for tp in valid_pinned:
                count = len(tag_tree.get(tp, []))
                pi = QTreeWidgetItem(pin_hdr, [f'# {tp.split("/")[-1]}  {count}'])
                pi.setData(0, Qt.ItemDataRole.UserRole, ('tag_pin', tp))
                pi.setForeground(0, QColor(C['accent']))
                pi.setFont(0, QFont('PingFang SC', 13))
                pi.setBackground(0, QColor('#1e1535'))
            pin_hdr.setExpanded(True)

        # ── 标签树 ───────────────────────────────────────────
        def add_tag_node(parent_item, tag_path: str, depth: int):
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
            add_tag_node(self.invisibleRootItem(), tag, 0)

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

        self._restore_expanded(expanded)  # None = 全展开（首次启动）

    def _on_double_click(self, item: QTreeWidgetItem, col: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data[0] == 'file':
            self.file_selected.emit(data[1])
        # tag_pin 单击也可以跳转（通过 itemClicked → 此处无需额外处理）

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

    def _restore_expanded(self, expanded):
        """expanded=None 时默认全部展开（首次启动），否则按记录恢复"""
        def walk(item):
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == 'tag':
                should = (expanded is None) or (data[1] in expanded)
                item.setExpanded(should)
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
            if data and data[0] in ('tag', 'tag_pin'):
                tag_path = data[1]
                tag_name = tag_path.split('/')[-1]
                pinned   = self._get_pinned()

                # 置顶 / 取消置顶
                if tag_path in pinned:
                    pa = menu.addAction('取消置顶')
                else:
                    pa = menu.addAction('⭐ 置顶')
                pa.triggered.connect(lambda _, t=tag_path: self._toggle_pin(t))
                menu.addSeparator()

                # 重命名（仅普通标签）
                if data[0] == 'tag':
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


# ── 文件内搜索浮动条 ──────────────────────────────────────────────────────

class SearchPanel(QFrame):
    """右上角单行搜索条：所有命中在编辑器里高亮，↑/↓ 逐条跳转"""
    jump_to = pyqtSignal(int)   # match index
    closed  = pyqtSignal()

    _BTN = f"""
        QPushButton {{
            background: {C['bg_sel']}; color: {C['fg']};
            border: none; border-radius: 4px; font-size: 12px;
        }}
        QPushButton:hover {{ background: {C['accent']}; color: white; }}
        QPushButton:checked {{ background: {C['accent']}; color: white; }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setFixedWidth(380)
        self.setObjectName('SearchPanel')
        self.setStyleSheet(f"""
            QFrame#SearchPanel {{
                background: {C['bg_input']};
                border: 1px solid {C['border']};
                border-radius: 8px;
            }}
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 8, 0)
        lay.setSpacing(6)

        self._input = QLineEdit()
        self._input.setPlaceholderText('在此文件中搜索…')
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent; color: {C['fg']};
                border: none; font-size: 14px;
            }}
        """)
        self._input.textChanged.connect(self._on_text)
        # Enter → 下一个；Shift+Enter → 上一个
        self._input.returnPressed.connect(self._next)
        lay.addWidget(self._input, 1)

        # 计数 "3 / 12"
        self._count_lbl = QLabel('')
        self._count_lbl.setStyleSheet(
            f"color: {C['fg_dim']}; font-size: 11px; min-width: 44px;"
            f"qproperty-alignment: AlignRight;")
        lay.addWidget(self._count_lbl)

        # 大小写
        self._case_btn = QPushButton('Aa')
        self._case_btn.setFixedSize(26, 26)
        self._case_btn.setCheckable(True)
        self._case_btn.setToolTip('区分大小写')
        self._case_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._case_btn.setStyleSheet(self._BTN)
        self._case_btn.clicked.connect(self._emit_search)
        lay.addWidget(self._case_btn)

        # 上 / 下
        for icon, tip, slot in [('↑', '上一个 (Shift+Enter)', self._prev),
                                 ('↓', '下一个 (Enter)',      self._next)]:
            b = QPushButton(icon)
            b.setFixedSize(26, 26)
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(self._BTN)
            b.clicked.connect(slot)
            lay.addWidget(b)

        # 关闭
        close = QPushButton('✕')
        close.setFixedSize(22, 22)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C['fg_dim']};
                border: none; font-size: 11px;
            }}
            QPushButton:hover {{ color: #ff6b6b; }}
        """)
        close.clicked.connect(self.closed.emit)
        lay.addWidget(close)

        self._matches: list[int] = []
        self._cur_idx = -1
        self.hide()

    def _on_text(self, _: str):
        if not hasattr(self, '_db'):
            self._db = QTimer(self)
            self._db.setSingleShot(True)
            self._db.timeout.connect(self._emit_search)
        self._db.start(180)

    def _emit_search(self):
        win = self.parent().window() if self.parent() else None
        if win and hasattr(win, '_do_search'):
            win._do_search(self._input.text(), self._case_btn.isChecked())

    def set_matches(self, matches: list[int], total_len: int):
        self._matches = matches
        self._cur_idx = 0 if matches else -1
        self._update_count()

    def _update_count(self):
        n = len(self._matches)
        if n == 0:
            self._count_lbl.setText('无结果')
        elif self._cur_idx >= 0:
            self._count_lbl.setText(f'{self._cur_idx + 1} / {n}')
        else:
            self._count_lbl.setText(f'{n}')

    def _prev(self):
        if self._matches:
            self._cur_idx = (self._cur_idx - 1) % len(self._matches)
            self._update_count()
            self.jump_to.emit(self._cur_idx)

    def _next(self):
        if self._matches:
            self._cur_idx = (self._cur_idx + 1) % len(self._matches)
            self._update_count()
            self.jump_to.emit(self._cur_idx)

    def focus(self):
        self._input.setFocus()
        self._input.selectAll()

    def is_case_sensitive(self) -> bool:
        return self._case_btn.isChecked()

    def current_keyword(self) -> str:
        return self._input.text()

    # 兼容旧调用
    def set_count(self, n: int):
        if n == 0:
            self._count_lbl.setText('无结果' if self._input.text() else '')
        else:
            self._count_lbl.setText(str(n))


# ── 全局搜索窗口 ──────────────────────────────────────────────────────────

class GlobalSearchDialog(QDialog):
    """全局搜索：左侧结果列表 + 右侧完整文件预览（所有命中全高亮）"""
    open_file = pyqtSignal(str, str)

    _MAX_RECENT = 8
    _BTN_SS = f"""
        QPushButton {{
            background: {C['bg_sel']}; color: {C['fg_dim']};
            border: none; border-radius: 5px; padding: 4px 10px; font-size: 12px;
        }}
        QPushButton:checked {{ background: {C['accent']}; color: white; }}
        QPushButton:hover:!checked {{ color: {C['fg']}; }}
    """
    _SS = f"""
        QDialog {{ background: {C['bg']}; }}
        QScrollBar:vertical {{ background: transparent; width: 3px; }}
        QScrollBar::handle:vertical {{ background: #444448; border-radius: 1px; min-height: 20px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QComboBox {{
            background: {C['bg_sel']}; color: {C['fg']};
            border: 1px solid {C['border']}; border-radius: 5px;
            padding: 3px 8px; font-size: 12px;
        }}
        QComboBox::drop-down {{ border: none; width: 16px; }}
        QComboBox QAbstractItemView {{
            background: {C['bg_input']}; color: {C['fg']};
            border: 1px solid {C['border']};
            selection-background-color: {C['bg_sel']};
        }}
    """

    def __init__(self, store: FileStore, parent=None):
        super().__init__(parent)
        self.setWindowTitle('全局搜索')
        self.store    = store
        self._recent: list[str] = store.get_config('recent_searches', [])
        # results: [(fp, full_text, [(pos, match_len), ...]), ...]
        self._results: list[tuple] = []      # [(fp, full_text, [(pos,mlen),...]), ...]
        self._flat_hits: list[tuple] = []   # [(fp, full_text, pos, mlen), ...] 全局扁平列表
        self._global_idx = 0
        self._sel_fp = ''
        self.resize(1000, 660)
        self.setMinimumSize(780, 500)
        self.setStyleSheet(self._SS)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 顶部搜索行 ───────────────────────────────────────
        header = QFrame()
        header.setFixedHeight(52)
        header.setStyleSheet(
            f"background: {C['bg_sidebar']}; border-bottom: 1px solid {C['border']};")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(14, 0, 10, 0)
        h_lay.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText('搜索所有文件…')
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {C['bg_input']}; color: {C['fg']};
                border: 1px solid {C['border']}; border-radius: 6px;
                padding: 6px 12px; font-size: 15px;
            }}
            QLineEdit:focus {{ border-color: {C['accent']}; }}
        """)
        self._input.textChanged.connect(self._on_text)
        self._input.returnPressed.connect(self._run_search)
        h_lay.addWidget(self._input, 1)

        # 大小写精确匹配
        self._case_btn = QPushButton('Aa')
        self._case_btn.setCheckable(True)
        self._case_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._case_btn.setToolTip('区分大小写')
        self._case_btn.setFixedWidth(36)
        self._case_btn.setStyleSheet(self._BTN_SS)
        self._case_btn.clicked.connect(lambda: self._run_search())
        h_lay.addWidget(self._case_btn)

        # 标签筛选
        self._tag_combo = QComboBox()
        self._tag_combo.addItem('全部标签', None)
        self._tag_combo.setFixedWidth(120)
        self._tag_combo.currentIndexChanged.connect(lambda: self._run_search())
        h_lay.addWidget(self._tag_combo)

        # 有标注
        self._annot_btn = QPushButton('有标注')
        self._annot_btn.setCheckable(True)
        self._annot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._annot_btn.setStyleSheet(self._BTN_SS)
        self._annot_btn.clicked.connect(lambda: self._run_search())
        h_lay.addWidget(self._annot_btn)

        self._result_lbl = QLabel('')
        self._result_lbl.setStyleSheet(
            f"color: {C['fg_dim']}; font-size: 12px; min-width: 80px;")
        h_lay.addWidget(self._result_lbl)
        root.addWidget(header)

        # ── 主体：左列表 + 右预览 ────────────────────────────
        body_split = QSplitter(Qt.Orientation.Horizontal)
        body_split.setHandleWidth(1)
        body_split.setStyleSheet(f"QSplitter::handle {{ background: {C['border']}; }}")

        # ── 左：结果列表 ──────────────────────────────────────
        left = QWidget()
        left.setStyleSheet(f"background: {C['bg_sidebar']};")
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        self._list_scroll = QScrollArea()
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_scroll.setStyleSheet(
            f"QScrollArea {{ background: {C['bg_sidebar']}; border: none; }}")
        self._list_inner = QWidget()
        self._list_inner.setStyleSheet(f"background: {C['bg_sidebar']};")
        self._list_vlay  = QVBoxLayout(self._list_inner)
        self._list_vlay.setContentsMargins(0, 4, 0, 4)
        self._list_vlay.setSpacing(0)
        self._list_vlay.addStretch()
        self._list_scroll.setWidget(self._list_inner)
        left_lay.addWidget(self._list_scroll)
        body_split.addWidget(left)

        # ── 右：完整文件预览 ──────────────────────────────────
        right = QWidget()
        right.setStyleSheet(f"background: {C['bg']};")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        # 右顶栏：文件名 + 命中导航
        ph = QFrame()
        ph.setFixedHeight(38)
        ph.setStyleSheet(
            f"background: {C['bg_sidebar']}; border-bottom: 1px solid {C['border']};")
        ph_lay = QHBoxLayout(ph)
        ph_lay.setContentsMargins(14, 0, 8, 0)
        ph_lay.setSpacing(6)
        self._preview_file_lbl = QLabel('选择左侧结果查看全文')
        self._preview_file_lbl.setStyleSheet(f"color: {C['fg_dim']}; font-size: 12px;")
        ph_lay.addWidget(self._preview_file_lbl, 1)
        self._hit_lbl = QLabel('')
        self._hit_lbl.setStyleSheet(f"color: {C['fg_dim']}; font-size: 11px;")
        ph_lay.addWidget(self._hit_lbl)
        for icon, tip, slot in [('↑', '上一条', self._prev_hit), ('↓', '下一条', self._next_hit)]:
            b = QPushButton(icon)
            b.setFixedSize(22, 22)
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {C['bg_sel']}; color: {C['fg']};
                    border: none; border-radius: 4px; font-size: 13px;
                }}
                QPushButton:hover {{ background: {C['accent']}; color: white; }}
            """)
            b.clicked.connect(slot)
            ph_lay.addWidget(b)
        right_lay.addWidget(ph)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        f = QFont('LXGW WenKai', 16)
        if not f.exactMatch():
            f = QFont('PingFang SC', 16)
        self._preview.setFont(f)
        self._preview.setStyleSheet(f"""
            QTextEdit {{
                background: {C['bg']}; color: {C['fg']};
                border: none; padding: 24px 40px;
            }}
            QScrollBar:vertical {{ background: transparent; width: 4px; }}
            QScrollBar::handle:vertical {{ background: #444448; border-radius: 2px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        right_lay.addWidget(self._preview, 1)

        # 右下：打开文件按钮
        pf = QFrame()
        pf.setFixedHeight(44)
        pf.setStyleSheet(
            f"background: {C['bg_sidebar']}; border-top: 1px solid {C['border']};")
        pf_lay = QHBoxLayout(pf)
        pf_lay.setContentsMargins(14, 0, 14, 0)
        self._file_lbl = QLabel('')
        self._file_lbl.setStyleSheet(f"color: {C['fg_dim']}; font-size: 12px;")
        pf_lay.addWidget(self._file_lbl, 1)
        open_btn = QPushButton('打开文件 →')
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setShortcut(QKeySequence(Qt.Key.Key_Return))
        open_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C['accent']}; color: white;
                border: none; border-radius: 5px; padding: 6px 16px; font-size: 13px;
            }}
            QPushButton:hover {{ background: #6aaaf8; }}
        """)
        open_btn.clicked.connect(self._open_selected)
        pf_lay.addWidget(open_btn)
        right_lay.addWidget(pf)
        body_split.addWidget(right)

        body_split.setSizes([300, 700])
        body_split.setCollapsible(0, False)
        body_split.setCollapsible(1, False)
        left.setMinimumWidth(220)
        right.setMinimumWidth(380)
        root.addWidget(body_split, 1)

        self._show_recent()
        self._input.setFocus()

    def populate_tags(self, tags: list[str]):
        self._tag_combo.blockSignals(True)
        self._tag_combo.clear()
        self._tag_combo.addItem('全部标签', None)
        for t in sorted(tags):
            self._tag_combo.addItem(f'#{t}', t)
        self._tag_combo.blockSignals(False)

    def _on_text(self, _text: str):
        if not hasattr(self, '_db'):
            self._db = QTimer(self)
            self._db.setSingleShot(True)
            self._db.timeout.connect(self._run_search)
        self._db.start(260)

    def _run_search(self):
        kw = self._input.text().strip()
        if not kw:
            self._show_recent()
            return
        # 更新历史
        if kw in self._recent:
            self._recent.remove(kw)
        self._recent.insert(0, kw)
        self._recent = self._recent[:self._MAX_RECENT]
        self.store.set_config('recent_searches', self._recent)

        case_sensitive = self._case_btn.isChecked()
        tag_filter     = self._tag_combo.currentData()
        annot_filter   = self._annot_btn.isChecked()
        self._results  = []

        needle = kw if case_sensitive else kw.lower()

        for fp in self.store.get_txt_files():
            if tag_filter and tag_filter not in TagScanner.scan(fp):
                continue
            if annot_filter and not self.store.get_annotations(fp):
                continue
            try:
                full = Path(fp).read_text('utf-8')
            except Exception:
                continue
            haystack = full if case_sensitive else full.lower()
            hits = []
            start = 0
            while True:
                idx = haystack.find(needle, start)
                if idx < 0:
                    break
                hits.append((idx, len(kw)))
                start = idx + 1
            if hits:
                self._results.append((fp, full, hits))

        # 构建全局扁平命中列表
        self._flat_hits = []
        for fp, full, hits in self._results:
            for pos, mlen in hits:
                self._flat_hits.append((fp, full, pos, mlen))
        self._global_idx = 0
        self._render_results(kw)

    def _render_results(self, kw: str):
        self._clear_list()
        total = len(self._flat_hits)
        if not self._results:
            self._result_lbl.setText('无结果')
            lbl = QLabel('无匹配结果')
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {C['fg_dim']}; font-size: 13px; padding: 20px;")
            self._list_vlay.insertWidget(0, lbl)
            self._preview.clear()
            self._preview_file_lbl.setText('选择左侧结果查看全文')
            self._hit_lbl.setText('')
            self._file_lbl.setText('')
            return
        self._result_lbl.setText(f'{total} 条 · {len(self._results)} 文件')

        case_sensitive = self._case_btn.isChecked()
        flat_offset = 0   # 当前文件在全局列表中的起始偏移

        for fp, full, hits in self._results:
            file_start = flat_offset   # 该文件第一条的全局编号

            # 文件标题行
            hdr = QFrame()
            hdr.setCursor(Qt.CursorShape.PointingHandCursor)
            hdr.setStyleSheet(f"""
                QFrame {{ background: {C['bg_input']}; border-bottom: 1px solid {C['border']}; }}
                QFrame:hover {{ background: #2a2d34; }}
            """)
            hdr_lay = QHBoxLayout(hdr)
            hdr_lay.setContentsMargins(12, 7, 10, 7)
            name_lbl = QLabel(Path(fp).stem)
            name_lbl.setStyleSheet(f"color: {C['fg']}; font-size: 13px; font-weight: bold;")
            hdr_lay.addWidget(name_lbl)
            cnt_lbl = QLabel(f'{len(hits)}')
            cnt_lbl.setStyleSheet(
                f"background: {C['accent']}; color: white; border-radius: 8px;"
                f"padding: 1px 6px; font-size: 11px;")
            hdr_lay.addWidget(cnt_lbl)
            hdr_lay.addStretch()
            def _hdr_click(e, gi=file_start):
                if e.button() == Qt.MouseButton.LeftButton:
                    self._jump_to_global(gi)
            hdr.mousePressEvent = _hdr_click
            self._list_vlay.insertWidget(self._list_vlay.count()-1, hdr)

            # 每条命中
            for i, (pos, mlen) in enumerate(hits):
                global_i = flat_offset + i
                row = self._make_hit_row(full, pos, mlen, global_i, kw, case_sensitive)
                self._list_vlay.insertWidget(self._list_vlay.count()-1, row)

            flat_offset += len(hits)

        # 自动跳到第一条
        if self._flat_hits:
            self._jump_to_global(0)

    def _make_hit_row(self, full: str, pos: int, mlen: int,
                      global_i: int, kw: str, case_sensitive: bool) -> QFrame:
        s = max(0, pos - 45)
        e = min(len(full), pos + mlen + 45)
        snippet = ('…' if s > 0 else '') + full[s:e].replace('\n', ' ')
        if e < len(full):
            snippet += '…'

        needle = kw if case_sensitive else kw.lower()
        snip_s = snippet if case_sensitive else snippet.lower()
        lo = snip_s.find(needle)
        if lo >= 0:
            esc_pre = snippet[:lo].replace('<', '&lt;')
            esc_mid = snippet[lo:lo+mlen].replace('<', '&lt;')
            esc_aft = snippet[lo+mlen:].replace('<', '&lt;')
            rich = (esc_pre
                    + f'<span style="color:{C["accent"]};font-weight:bold">'
                    + esc_mid + '</span>' + esc_aft)
        else:
            rich = snippet.replace('<', '&lt;')

        row = QFrame()
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setStyleSheet(f"""
            QFrame {{ background: transparent; border-bottom: 1px solid {C['bg_sel']}; }}
            QFrame:hover {{ background: {C['bg_sel']}; }}
        """)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(22, 5, 10, 5)

        lbl = QLabel(rich)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setStyleSheet(f"color: {C['fg_file']}; font-size: 12px;")
        lbl.setWordWrap(False)
        lay.addWidget(lbl, 1)

        def _click(e, gi=global_i):
            if e.button() == Qt.MouseButton.LeftButton:
                self._jump_to_global(gi)
        row.mousePressEvent = _click
        return row

    def _jump_to_global(self, idx: int):
        """跳转到全局第 idx 条命中（跨文件统一计数）"""
        if not self._flat_hits or not (0 <= idx < len(self._flat_hits)):
            return
        fp, full, pos, mlen = self._flat_hits[idx]
        self._global_idx = idx
        self._sel_fp = fp

        total = len(self._flat_hits)
        self._hit_lbl.setText(f'{idx + 1} / {total}')
        self._preview_file_lbl.setText(Path(fp).stem)
        self._file_lbl.setText(Path(fp).stem)

        # 收集该文件所有命中（用于 ExtraSelections）
        file_hits = [(p, m) for f, _, p, m in self._flat_hits if f == fp]
        cur_local = next(i for i, (p, m) in enumerate(file_hits)
                         if p == pos and m == mlen)

        # 文件切换时重新加载（避免重复 setPlainText 闪烁）
        if self._preview.toPlainText() != full:
            self._preview.setPlainText(full)
            from PyQt6.QtGui import QTextBlockFormat
            c = QTextCursor(self._preview.document())
            c.select(QTextCursor.SelectionType.Document)
            blk = QTextBlockFormat()
            blk.setLineHeight(160, 1)
            c.setBlockFormat(blk)

        fmt_all = QTextCharFormat()
        fmt_all.setBackground(QColor('#2a2400'))
        fmt_all.setForeground(QColor('#c8a850'))
        fmt_cur = QTextCharFormat()
        fmt_cur.setBackground(QColor('#3a2e00'))
        fmt_cur.setForeground(QColor('#f0d070'))
        fmt_cur.setFontWeight(QFont.Weight.Bold)

        sels = []
        for i, (p2, m2) in enumerate(file_hits):
            sel = QTextEdit.ExtraSelection()
            c = QTextCursor(self._preview.document())
            c.setPosition(p2)
            c.setPosition(p2 + m2, QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = c
            sel.format = fmt_cur if i == cur_local else fmt_all
            sels.append(sel)
        self._preview.setExtraSelections(sels)

        # 滚动居中
        c = QTextCursor(self._preview.document())
        c.setPosition(pos)
        self._preview.setTextCursor(c)
        self._preview.ensureCursorVisible()
        rect = self._preview.cursorRect(c)
        vp_h = self._preview.viewport().height()
        sb = self._preview.verticalScrollBar()
        sb.setValue(sb.value() + rect.center().y() - vp_h // 2)

    def _prev_hit(self):
        if self._flat_hits:
            self._jump_to_global((self._global_idx - 1) % len(self._flat_hits))

    def _next_hit(self):
        if self._flat_hits:
            self._jump_to_global((self._global_idx + 1) % len(self._flat_hits))

    def _open_selected(self):
        if self._sel_fp:
            self.open_file.emit(self._sel_fp, self._input.text().strip())
            self.accept()

    def _show_recent(self):
        self._clear_list()
        self._result_lbl.setText('')
        self._flat_hits = []
        self._global_idx = 0
        self._preview.clear()
        self._preview_file_lbl.setText('选择左侧结果查看全文')
        self._hit_lbl.setText('')
        self._file_lbl.setText('')
        if not self._recent:
            return
        hdr = QLabel('最近搜索')
        hdr.setContentsMargins(12, 8, 0, 4)
        hdr.setStyleSheet(f"color: {C['fg_dim']}; font-size: 11px;")
        self._list_vlay.insertWidget(0, hdr)
        for kw in self._recent:
            row = QFrame()
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setStyleSheet(f"""
                QFrame {{ background: transparent; }}
                QFrame:hover {{ background: {C['bg_sel']}; }}
            """)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 7, 12, 7)
            lbl = QLabel(kw)
            lbl.setStyleSheet(f"color: {C['fg_file']}; font-size: 13px;")
            rl.addWidget(lbl)
            rl.addStretch()
            def _click(e, k=kw):
                if e.button() == Qt.MouseButton.LeftButton:
                    self._input.setText(k)
            row.mousePressEvent = _click
            self._list_vlay.insertWidget(self._list_vlay.count()-1, row)

    def _clear_list(self):
        while self._list_vlay.count() > 1:
            item = self._list_vlay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)


# ── 文字标签弹窗（颜色 + 可选标签名）────────────────────────────────────

class LabelDialog(QDialog):
    """选颜色 + 输入标签名，两步合一"""

    _COLORS = [
        ('hl_yellow', '#e8c870', '#3a2e00'),
        ('hl_green',  '#5ec87a', '#0e2a1a'),
        ('hl_pink',   '#e86090', '#3a1020'),
        ('hl_purple', '#a878f0', '#1a1040'),
    ]

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self._color_type = 'hl_yellow'
        self.setStyleSheet(f"""
            QDialog {{
                background: {C['bg_input']};
                border: 1px solid {C['border']};
                border-radius: 10px;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        # 提示
        hint = QLabel('选择颜色，输入标签名（可留空）')
        hint.setStyleSheet(f"color: {C['fg_dim']}; font-size: 12px;")
        lay.addWidget(hint)

        # 4 色选择
        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        self._btn_group = QButtonGroup(self)
        for i, (ctype, dot, bg) in enumerate(self._COLORS):
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setCheckable(True)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {dot}; border-radius: 14px;
                    border: 2px solid transparent;
                }}
                QPushButton:checked {{
                    border: 2px solid white;
                }}
            """)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, t=ctype: self._pick(t))
            self._btn_group.addButton(btn, i)
            color_row.addWidget(btn)
        color_row.addStretch()
        lay.addLayout(color_row)
        # 默认选第一个
        self._btn_group.button(0).setChecked(True)

        # 标签名输入
        self._input = QLineEdit()
        self._input.setPlaceholderText('标签名（可选）…')
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {C['bg']}; color: {C['fg']};
                border: 1px solid {C['border']}; border-radius: 6px;
                padding: 7px 10px; font-size: 14px;
            }}
            QLineEdit:focus {{ border-color: {C['accent']}; }}
        """)
        self._input.returnPressed.connect(self.accept)
        lay.addWidget(self._input)

        # 确认 / 取消
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        cancel = QPushButton('取消')
        cancel.setFixedHeight(32)
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(f"""
            QPushButton {{
                background: {C['bg_sel']}; color: {C['fg_dim']};
                border: none; border-radius: 6px; font-size: 13px;
            }}
            QPushButton:hover {{ color: {C['fg']}; }}
        """)
        cancel.clicked.connect(self.reject)
        ok = QPushButton('应用')
        ok.setFixedHeight(32)
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setStyleSheet(f"""
            QPushButton {{
                background: {C['accent']}; color: white;
                border: none; border-radius: 6px; font-size: 13px;
            }}
            QPushButton:hover {{ background: #6aaaf8; }}
        """)
        ok.clicked.connect(self.accept)
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        lay.addLayout(btn_row)

        self._input.setFocus()

    def _pick(self, ctype: str):
        self._color_type = ctype

    def result_data(self) -> tuple[str, str]:
        """返回 (color_type, label_text)"""
        return self._color_type, self._input.text().strip()


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
        self._pending_annot_id: str | None = None
        self._zen = False

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

        # 搜索面板（浮动，叠加在编辑器右上角）
        self._search_bar = SearchPanel(self._txt_editor)
        self._search_bar.jump_to.connect(self._jump_to_match)
        self._search_bar.closed.connect(self._close_search)
        self._search_bar.hide()

        # 备注栏
        self._note_bar = NoteBar(self.store)
        self._note_bar.saved.connect(lambda: self._annot_panel.refresh(self._fp))
        ew_lay.addWidget(self._note_bar)

        # 阅读进度条（底部细条）
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(3)
        self._progress_bar.setRange(0, 1000)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {C['bg_input']};
                border: none; border-radius: 0;
            }}
            QProgressBar::chunk {{
                background: {C['accent']};
                border-radius: 0;
            }}
        """)
        ew_lay.addWidget(self._progress_bar)
        self._txt_editor.verticalScrollBar().valueChanged.connect(self._update_progress)

        self._content_split.addWidget(editor_wrap)

        # 标注面板
        self._annot_panel = AnnotPanel(self.store)
        self._annot_panel.jump_to.connect(self._jump_to_annot)
        self._annot_panel.delete.connect(self._delete_annot_by_id)
        self._annot_panel.clear_all.connect(self._clear_all_annots)
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
        _act(am, '清除所有标注…', self._confirm_clear_all)

        # 视图
        vm = mb.addMenu('视图')
        vm.setStyleSheet(_ms)
        _act(vm, '全局搜索', self._open_global_search, 'Ctrl+K')
        _act(vm, '当前文件搜索', self._toggle_search, 'Ctrl+F')
        vm.addSeparator()
        self._annot_panel_action = QAction('显示标注面板', self)
        self._annot_panel_action.setShortcut(QKeySequence('Ctrl+\\'))
        self._annot_panel_action.setCheckable(True)
        self._annot_panel_action.setChecked(False)
        self._annot_panel_action.triggered.connect(self._toggle_annot_panel)
        vm.addAction(self._annot_panel_action)
        vm.addSeparator()
        _act(vm, '禅定模式', self._toggle_zen, 'Ctrl+Shift+Z')
        vm.addSeparator()
        _act(vm, '跳到文章开头', self._go_top,    'Ctrl+Up')
        _act(vm, '跳到文章末尾', self._go_bottom, 'Ctrl+Down')
        vm.addSeparator()
        _act(vm, '刷新侧栏', self._refresh_sidebar, 'F5')

    def _apply_theme(self):
        self.setStyleSheet(f"QMainWindow {{ background: {C['bg']}; }}")
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(C['bg']))
        self.setPalette(pal)

    # ── 全局搜索 ──────────────────────────────────────────────
    def _open_global_search(self):
        dlg = GlobalSearchDialog(self.store, self)
        # 注入所有标签
        all_tags = list(TagScanner.build_tree(self.store.get_txt_files()).keys())
        dlg.populate_tags(all_tags)
        dlg.open_file.connect(self._global_open_file)
        # 居中显示在窗口
        dlg.adjustSize()
        geo = self.geometry()
        dlg.move(
            geo.x() + (geo.width()  - dlg.width())  // 2,
            geo.y() + (geo.height() - dlg.height()) // 3,
        )
        dlg.exec()

    def _global_open_file(self, fp: str, kw: str):
        """打开文件并高亮关键词"""
        self._open_file(fp)
        if kw:
            def _show_search(k=kw):
                self._search_bar.show()
                self._do_search(k)
            QTimer.singleShot(100, _show_search)

    # ── 禅定模式 ──────────────────────────────────────────────
    def _toggle_zen(self):
        self._zen = not self._zen
        if self._zen:
            self._pre_zen_annot = self._annot_panel_action.isChecked()
            self._split.widget(0).hide()
            self._annot_panel.hide()
            self._annot_panel_action.setChecked(False)
            self.menuBar().hide()
            self.statusBar().hide()
            self._progress_bar.hide()
            self._txt_editor._count_lbl.hide()
        else:
            self._split.widget(0).show()
            if self._pre_zen_annot:
                self._annot_panel.show()
                self._annot_panel_action.setChecked(True)
            self.menuBar().show()
            self.statusBar().show()
            self._progress_bar.show()
            self._txt_editor._count_lbl.show()

    def _go_top(self):
        ed = self._txt_editor
        ed.verticalScrollBar().setValue(0)
        c = QTextCursor(ed.document())
        c.movePosition(QTextCursor.MoveOperation.Start)
        ed.setTextCursor(c)

    def _go_bottom(self):
        ed = self._txt_editor
        ed.verticalScrollBar().setValue(ed.verticalScrollBar().maximum())
        c = QTextCursor(ed.document())
        c.movePosition(QTextCursor.MoveOperation.End)
        ed.setTextCursor(c)

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

    def _update_progress(self, value: int = -1):
        sb = self._txt_editor.verticalScrollBar()
        if value < 0:
            value = sb.value()
        maximum = sb.maximum()
        self._progress_bar.setValue(
            int(value / maximum * 1000) if maximum > 0 else 0)

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
        """点击 # 按钮：保存选区 → 关浮动条 → 弹颜色+标签名弹窗"""
        cur = self._txt_editor.textCursor()
        if not cur.hasSelection():
            self._annot_bar.hide()
            return
        saved_anchor   = cur.anchor()
        saved_position = cur.position()
        self._annot_bar.hide()

        dlg = LabelDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        color_type, label_text = dlg.result_data()

        # 恢复选区后应用
        c = self._txt_editor.textCursor()
        c.setPosition(saved_anchor)
        c.setPosition(saved_position, QTextCursor.MoveMode.KeepAnchor)
        self._txt_editor.setTextCursor(c)
        annot = self._txt_editor.annotate(color_type, label_text)
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

    def _clear_all_annots(self):
        if not self._fp:
            return
        self.store.clear_all_annotations(self._fp)
        self._txt_editor._apply_annotations()
        self._annot_panel.refresh(self._fp)

    def _confirm_clear_all(self):
        if not self._fp:
            return
        n = len(self.store.get_annotations(self._fp))
        if n == 0:
            self.statusBar().showMessage('当前文件没有标注', 2000)
            return
        reply = QMessageBox.question(
            self, '清除所有标注',
            f'删除当前文件全部 {n} 条标注？此操作不可撤销。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._clear_all_annots()

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
    def _position_search_panel(self):
        """将搜索面板定位到编辑器右上角"""
        p = self._search_bar
        p.adjustSize()
        editor = self._txt_editor
        margin = 12
        p.move(editor.width() - p.width() - margin, margin)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_search_panel()

    def _toggle_search(self):
        if self._search_bar.isVisible():
            self._close_search()
        else:
            self._search_bar.setParent(self._txt_editor)
            self._position_search_panel()
            self._search_bar.show()
            self._search_bar.raise_()
            self._search_bar.focus()

    def _close_search(self):
        self._search_bar.hide()
        self._clear_search_hl()
        if self._stack.currentWidget() == self._txt_editor:
            self._txt_editor.setFocus()

    def _do_search(self, kw: str, case_sensitive: bool = False):
        self._clear_search_hl()
        if not kw or self._stack.currentWidget() != self._txt_editor:
            self._search_bar.set_count(0)
            return
        doc  = self._txt_editor.document()
        full = doc.toPlainText()
        needle   = kw if case_sensitive else kw.lower()
        haystack = full if case_sensitive else full.lower()

        fmt_all = QTextCharFormat()
        fmt_all.setBackground(QColor('#2a2400'))
        fmt_all.setForeground(QColor('#c8a850'))

        self._search_matches = []
        selections = []
        start = 0
        while True:
            idx = haystack.find(needle, start)
            if idx < 0:
                break
            self._search_matches.append(idx)
            sel = QTextEdit.ExtraSelection()
            c = QTextCursor(doc)
            c.setPosition(idx)
            c.setPosition(idx + len(kw), QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = c
            sel.format = fmt_all
            selections.append(sel)
            start = idx + 1

        self._txt_editor.setExtraSelections(selections)
        self._search_bar.set_matches(self._search_matches, len(full))
        if self._search_matches:
            self._jump_to_match(0)

    def _jump_to_match(self, idx: int):
        if not self._search_matches or idx >= len(self._search_matches):
            return
        doc = self._txt_editor.document()
        pos = self._search_matches[idx]
        kw  = self._search_bar.current_keyword()

        # 当前条：更亮
        fmt_cur = QTextCharFormat()
        fmt_cur.setBackground(QColor('#3a2e00'))
        fmt_cur.setForeground(QColor('#f0d070'))
        fmt_cur.setFontWeight(QFont.Weight.Bold)

        fmt_all = QTextCharFormat()
        fmt_all.setBackground(QColor('#2a2400'))
        fmt_all.setForeground(QColor('#c8a850'))

        sels = []
        for i, p in enumerate(self._search_matches):
            sel = QTextEdit.ExtraSelection()
            c = QTextCursor(doc)
            c.setPosition(p)
            c.setPosition(p + len(kw), QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = c
            sel.format = fmt_cur if i == idx else fmt_all
            sels.append(sel)
        self._txt_editor.setExtraSelections(sels)

        # 更新面板计数
        self._search_bar._cur_idx = idx
        self._search_bar._update_count()

        # 居中滚动
        c = QTextCursor(doc)
        c.setPosition(pos)
        self._txt_editor.setTextCursor(c)
        self._txt_editor.ensureCursorVisible()
        rect = self._txt_editor.cursorRect(c)
        vp_h = self._txt_editor.viewport().height()
        sb   = self._txt_editor.verticalScrollBar()
        sb.setValue(sb.value() + rect.center().y() - vp_h // 2)

    def _clear_search_hl(self):
        self._txt_editor.setExtraSelections([])

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self._zen:
                self._toggle_zen()
            elif self._search_bar.isVisible():
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
