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
    QProgressBar, QComboBox, QGraphicsOpacityEffect, QToolButton,
    QStyledItemDelegate, QWidgetAction
)
from PyQt6.QtGui import (
    QColor, QFont, QTextCharFormat, QTextCursor, QTextDocument,
    QPalette, QPixmap, QImage, QAction, QKeySequence, QSyntaxHighlighter,
    QPainter, QFontDatabase, QCursor, QPen, QPolygonF, QIcon
)
from PyQt6.QtCore import (
    Qt, QTimer, QSize, QPoint, QRect, pyqtSignal, QThread, QObject,
    QPropertyAnimation, QEasingCurve
)


# ── 常量 ──────────────────────────────────────────────────────────────────
DATA_FILE = Path.home() / '.purple-loop.json'
TAG_RE    = re.compile(r'#([\w\u4e00-\u9fff]+(?:/[\w\u4e00-\u9fff]+)*)')
IS_MAC    = sys.platform == 'darwin'
MOD       = Qt.KeyboardModifier.MetaModifier if IS_MAC else Qt.KeyboardModifier.ControlModifier

# ── 语气词/口语填充词 ──────────────────────────────────────────────────────
# 单字语气助词（句末）+ 叹词 + 高频口头禅
_FILLER_PARTS = [
    # 叹词 / 犹豫音
    '嗯嗯', '嗯呀', '哎呀', '诶呀', '哎哟',
    '嗯', '哎', '诶', '呃', '额', '哦', '噢', '哇', '哟', '嗐', '哼',
    # 句末语气助词
    '啊', '吧', '呢', '嘛', '呀', '啦', '咯', '哩', '喽',
    # 高频口头禅 / 话语标记（先长后短，避免短的先匹配）
    '就是说', '也就是说', '你知道吧', '你知道', '怎么说呢', '怎么说',
    '然后呢', '然后',
    '对对对', '对对', '好吧', '是吧', '是啊',
    '反正', '其实',
    # 注意：'就是'、'那个'、'这个' 语义用法太多，高亮误匹配率高，仅保留频率统计
]
# 高亮用：去掉语义歧义高的词，减少误匹配
_FILLER_HIGHLIGHT = [w for w in _FILLER_PARTS if w not in ('就是', '那个', '这个')]
FILLER_RE = re.compile('(' + '|'.join(re.escape(w) for w in _FILLER_HIGHLIGHT) + ')')

# 频率统计用：保留全部词（包括就是/那个/这个，统计价值高）
_FILLER_ALL = _FILLER_PARTS + ['就是', '那个', '这个']
FILLER_STAT_RE = re.compile('(' + '|'.join(re.escape(w) for w in _FILLER_ALL) + ')')

# ── 话语标记词（Discourse Markers）──────────────────────────────────────────
# 按功能分4类，各类对应不同颜色高亮
_DM_CAUSAL = [
    # 因果类（表原因/结果）
    '正因为如此', '也正因为', '因此可见', '由此可见',
    '所以说', '因为', '由于', '既然', '因此', '所以', '以致于', '以致',
    '结果', '原来',
]
_DM_CONTRAST = [
    # 转折/对比类
    '虽然如此', '尽管如此', '即便如此',
    '虽然', '尽管', '但是', '然而', '不过', '可是', '却', '反而',
    '与此相反', '相反',
]
_DM_PROGRESSIVE = [
    # 递进/举例类
    '不仅如此', '与此同时', '除此之外',
    '不仅', '不但', '而且', '并且', '同时', '甚至', '何况',
    '比如说', '举例来说', '例如', '比如', '譬如', '像',
    '也就是说', '换句话说', '换言之', '即',
    '还有', '另外', '此外',
]
_DM_STRUCTURE = [
    # 总结/衔接/话题类
    '综上所述', '总的来说', '总的来看', '概括来说',
    '总之', '总而言之', '一句话',
    '首先', '其次', '再次', '最后', '第一', '第二', '第三',
    '接下来', '随后', '之后', '然后',
    '那么', '关于', '至于', '说到', '说起',
    '总结一下', '回到', '继续',
]

def _build_dm_re(words: list) -> re.Pattern:
    return re.compile('(' + '|'.join(re.escape(w) for w in words) + ')')

DM_RE_CAUSAL      = _build_dm_re(_DM_CAUSAL)
DM_RE_CONTRAST    = _build_dm_re(_DM_CONTRAST)
DM_RE_PROGRESSIVE = _build_dm_re(_DM_PROGRESSIVE)
DM_RE_STRUCTURE   = _build_dm_re(_DM_STRUCTURE)

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

    # ── 阅读位置（按字符偏移记忆，不受字号/行距影响）──────────
    def get_read_pos(self, filepath: str) -> dict:
        """返回 {'char': int, 'poff': int}，兼容旧格式 int"""
        raw = self.data.get('read_positions', {}).get(filepath, 0)
        if isinstance(raw, dict):
            return raw
        return {'char': int(raw), 'poff': 0}

    def set_read_pos(self, filepath: str, char: int, poff: int):
        """poff = 字符顶边在视口内的像素 y（负值表示字符顶部在视口上方）"""
        self.data.setdefault('read_positions', {})[filepath] = {
            'char': char, 'poff': poff}
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
    """从 .txt 文件内容提取 #标签，带 mtime 缓存"""

    _cache: dict = {}   # {filepath: (mtime, tags_set)}

    @staticmethod
    def scan(filepath: str) -> set:
        try:
            mtime = Path(filepath).stat().st_mtime
            cached = TagScanner._cache.get(filepath)
            if cached and cached[0] == mtime:
                return cached[1]
            tags = set(TAG_RE.findall(Path(filepath).read_text('utf-8')))
            TagScanner._cache[filepath] = (mtime, tags)
            return tags
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
    """
    选中文字后弹出的浮动工具条。
    设计：# 按钮打开颜色+备注弹窗（合并原来的4色圆点），B/U/✕ 保留。
    工具条：  #  B  U  |  ✕
    """
    annotate        = pyqtSignal(str)
    label_requested = pyqtSignal()   # 请求输入颜色+标签名（# 按钮触发）
    remove          = pyqtSignal()

    _BTN_SS = f"""
        QPushButton {{
            background: {C['bg_sel']}; color: {C['fg']};
            border-radius: 4px; border: none; font-size: 13px;
        }}
        QPushButton:hover {{ background: {C['accent']}; color: white; }}
    """

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
        lay.setSpacing(4)

        def _btn(text, tooltip, slot, extra_ss=''):
            b = QPushButton(text)
            b.setFixedSize(30, 28)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(tooltip)
            b.setStyleSheet(self._BTN_SS + extra_ss)
            b.clicked.connect(slot)
            return b

        # # 按钮：打开颜色+备注弹窗
        hash_btn = _btn('#', '高亮 / 备注（选颜色）', self.label_requested.emit,
                        f'QPushButton {{ color: {C["accent"]}; font-weight: bold; font-size: 15px; }}'
                        f'QPushButton:hover {{ background: {C["accent"]}; color: white; }}')
        lay.addWidget(hash_btn)

        # B / U
        b_btn = QPushButton('B')
        b_btn.setFixedSize(30, 28)
        b_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        b_btn.setToolTip('加粗')
        f_b = QFont('PingFang SC', 13)
        f_b.setBold(True)
        b_btn.setFont(f_b)
        b_btn.setStyleSheet(self._BTN_SS)
        b_btn.clicked.connect(lambda: self.annotate.emit('bold'))
        lay.addWidget(b_btn)

        u_btn = QPushButton('U')
        u_btn.setFixedSize(30, 28)
        u_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        u_btn.setToolTip('下划线')
        f_u = QFont('PingFang SC', 13)
        f_u.setUnderline(True)
        u_btn.setFont(f_u)
        u_btn.setStyleSheet(self._BTN_SS)
        u_btn.clicked.connect(lambda: self.annotate.emit('underline'))
        lay.addWidget(u_btn)

        # 分隔
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {C['border']};")
        sep.setFixedWidth(1)
        lay.addWidget(sep)

        # ✕ 删除
        del_btn = QPushButton('✕')
        del_btn.setFixedSize(28, 28)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setToolTip('删除标注')
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
    ('note',      '#c4b0f8', '# 备注'),
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

        # 预读文件内容，用于计算行号
        try:
            file_text = Path(filepath).read_text('utf-8')
        except Exception:
            file_text = ''

        all_annots = self.store.get_annotations(filepath)
        if self._filter is not None:
            if self._filter == 'hl_purple':
                shown = [a for a in all_annots
                         if a['type'] in ('hl_purple', 'label')]
            elif self._filter == 'note':
                shown = [a for a in all_annots if a.get('note', '').strip()]
            else:
                shown = [a for a in all_annots if a['type'] == self._filter]
        else:
            shown = all_annots

        for annot in shown:
            line_no = file_text[:annot.get('start', 0)].count('\n') + 1 if file_text else 0
            card = self._make_card(annot, line_no)
            self._layout.insertWidget(self._layout.count() - 1, card)
            self._cards[annot['id']] = card

    def _make_card(self, annot: dict, line_no: int = 0) -> QFrame:
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

        # 顶栏：类型标签 / 标签名 pill + 行号 + 删除按钮
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
        if line_no:
            ln_lbl = QLabel(f'L{line_no}')
            ln_lbl.setStyleSheet(f"color: {C['fg_dim']}; font-size: 10px;")
            top.addWidget(ln_lbl)
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
        self._annots: list = []          # 缓存当前文件标注，避免每块重复查询
        self._show_fillers = False
        self._show_dm      = False
        self._tag_fmt = QTextCharFormat()
        self._tag_fmt.setForeground(QColor(C['accent']))
        # 语气词格式：低调暖色
        self._filler_fmt = QTextCharFormat()
        self._filler_fmt.setForeground(QColor('#a07848'))   # 哑金色
        # 话语标记词格式：4种颜色
        self._dm_causal_fmt = QTextCharFormat()
        self._dm_causal_fmt.setForeground(QColor('#c47a3a'))      # 橙：因果
        self._dm_contrast_fmt = QTextCharFormat()
        self._dm_contrast_fmt.setForeground(QColor('#5a9ac4'))    # 蓝：转折
        self._dm_progressive_fmt = QTextCharFormat()
        self._dm_progressive_fmt.setForeground(QColor('#5aab7a'))  # 绿：递进/举例
        self._dm_structure_fmt = QTextCharFormat()
        self._dm_structure_fmt.setForeground(QColor('#9e8cc0'))   # 淡紫：结构/总结

    def set_file(self, filepath: str | None, rehighlight: bool = True):
        self._fp = filepath
        self._annots = self.store.get_annotations(filepath) if filepath else []
        if rehighlight:
            self.rehighlight()

    def invalidate_annots(self):
        """标注增删改后调用，刷新缓存并重新高亮"""
        self._annots = self.store.get_annotations(self._fp) if self._fp else []
        self.rehighlight()

    def set_show_fillers(self, enabled: bool):
        self._show_fillers = enabled
        self.rehighlight()

    def set_show_dm(self, enabled: bool):
        self._show_dm = enabled
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

        for annot in self._annots:
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

        # 3. 语气词高亮
        if self._show_fillers:
            for m in FILLER_RE.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), self._filler_fmt)

        # 4. 话语标记词高亮（因果/转折/递进/结构 各色）
        if self._show_dm:
            for pat, fmt in (
                (DM_RE_CAUSAL,      self._dm_causal_fmt),
                (DM_RE_CONTRAST,    self._dm_contrast_fmt),
                (DM_RE_PROGRESSIVE, self._dm_progressive_fmt),
                (DM_RE_STRUCTURE,   self._dm_structure_fmt),
            ):
                for m in pat.finditer(text):
                    self.setFormat(m.start(), m.end() - m.start(), fmt)


# ── txt 编辑器 ───────────────────────────────────────────────────────────

class TxtEditor(QTextEdit):
    mouse_released = pyqtSignal()   # 鼠标松开时通知主窗口检查选区

    def __init__(self, store: FileStore, parent=None):
        super().__init__(parent)
        self.store       = store
        self._fp: str | None = None
        self._loading    = False
        self._highlighter = DocHighlighter(self.document(), store)

        # 字体（固定最优阅读字号，不开放调节）
        self._set_font()
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.LineWrapMode.FixedPixelWidth)
        self.setLineWrapColumnOrWidth(700)
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C['bg']}; color: {C['fg']};
                border: none; padding: 56px 8px 56px 160px;
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
        f = QFont('LXGW WenKai', 19)   # 固定最优阅读字号
        if not f.exactMatch():
            f = QFont('PingFang SC', 19)
        f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.setFont(f)
        self._apply_line_spacing()

    def _apply_line_spacing(self):
        from PyQt6.QtGui import QTextBlockFormat
        doc = self.document()
        doc.setUndoRedoEnabled(False)      # 跳过 undo stack，大幅加速批量操作
        cur = QTextCursor(doc)
        cur.select(QTextCursor.SelectionType.Document)
        blk_fmt = QTextBlockFormat()
        blk_fmt.setLineHeight(175, 1)       # 1.75 倍行距（中文阅读最优）
        blk_fmt.setBottomMargin(10)         # 段落间距
        cur.setBlockFormat(blk_fmt)
        doc.setUndoRedoEnabled(True)

    def load_file(self, path: str):
        # ── 保存当前文件阅读位置 ─────────────────────────────────────
        # 存：字符偏移 + 该字符顶边在视口内的像素 y（pixel_offset）
        # pixel_offset 捕获子行级精度（字符可能部分在视口上方）
        if self._fp:
            cur  = self.cursorForPosition(QPoint(2, 2))
            poff = self.cursorRect(cur).top()   # 负值 = 字符顶部在视口上方
            self.store.set_read_pos(self._fp, char=cur.position(), poff=poff)

        self._fp      = path
        self._loading = True
        self._highlighter.set_file(path, rehighlight=False)
        text = Path(path).read_text('utf-8')

        # ── 屏蔽绘制，避免用户看到文档头部闪烁 ──────────────────────
        self.setUpdatesEnabled(False)
        self.document().setUndoRedoEnabled(False)
        self.setPlainText(text)
        self._apply_line_spacing()
        self.document().setUndoRedoEnabled(True)
        self._loading = False
        self._update_count()

        pos = self.store.get_read_pos(path)   # {'char': int, 'poff': int}

        def _restore_and_show():
            saved_char = pos['char']
            saved_poff = pos['poff']   # 保存时字符顶边的视口 y

            cur     = QTextCursor(self.document())
            max_pos = max(0, self.document().characterCount() - 1)
            cur.setPosition(min(saved_char, max_pos))
            self.setTextCursor(cur)
            self.ensureCursorVisible()   # 让光标进入视口（触发布局）

            # 精确调整：把字符还原到保存时的像素 y 位置
            # cr.top() = 恢复后字符顶边的视口 y
            # 目标：使 cr.top() == saved_poff
            cr = self.cursorRect(cur)
            delta = cr.top() - saved_poff
            if delta != 0:
                sb = self.verticalScrollBar()
                sb.setValue(sb.value() + delta)

            # 解锁绘制——第一帧直接在正确位置
            self.setUpdatesEnabled(True)
            self.update()
            mw = self.window()
            if hasattr(mw, '_update_progress'):
                mw._update_progress()

        def _after_layout():
            self._apply_reading_width()
            QTimer.singleShot(0, _restore_and_show)

        QTimer.singleShot(0, _after_layout)


    def _apply_annotations(self):
        """标注变更后刷新缓存并重绘"""
        self._highlighter.invalidate_annots()

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
        self._apply_annotations()   # 更新 _annots 缓存后再重绘
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
        if self._loading:
            return
        # characterCount() 是 O(1)，避免 toPlainText() 在大文件中复制全文
        n = max(0, self.document().characterCount() - 1)
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

    def _apply_reading_width(self):
        """FixedPixelWidth 硬限行宽，左侧 padding 居中，右侧 8px 使滚动条贴边"""
        w = self.width()
        max_content = 680   # 约 35 个汉字，中文阅读黄金行宽
        right_pad, scrollbar_w = 8, 6
        wrap_w = min(max_content, max(200, w - 2 * 60 - right_pad - scrollbar_w))
        self.setLineWrapColumnOrWidth(wrap_w)
        # 左侧 padding 让内容居中（两侧视觉空白对称）
        left_pad = max(60, (w - wrap_w - right_pad - scrollbar_w) // 2)
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C['bg']}; color: {C['fg']};
                border: none; padding: 56px 8px 56px {left_pad}px;
                selection-background-color: #4a4a55;
                selection-color: #e0e0e0;
            }}
            QScrollBar:vertical {{
                background: transparent; width: 6px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: #3a3a3e; border-radius: 3px; min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{ background: #555558; }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_count_lbl()
        self._apply_reading_width()


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



# ── 菜单图标：用系统字体渲染 Unicode 字符，清晰无锯齿 ─────────────────────

# 选用标准 Unicode，macOS 下这几个字符在 Apple Symbols / PingFang 里都有干净的矢量字形
_MENU_ICON_CHARS = {
    'pin':    '\u2605',   # ★  实心五角星 → 置顶
    'pencil': '\u270e',   # ✎  铅笔
    'trash':  '\U0001F43E', # 🐾  猫爪
}

def _mk_menu_icon(shape: str, color: str = '#9a9a9a', lsize: int = 14) -> QIcon:
    """用 QPainter.drawText 渲染 Unicode 字形，HiDPI 清晰。"""
    from PyQt6.QtCore import QRectF
    char = _MENU_ICON_CHARS.get(shape, '•')
    dpr  = 2
    pw   = lsize * dpr
    px   = QPixmap(pw, pw)
    px.setDevicePixelRatio(dpr)
    px.fill(Qt.GlobalColor.transparent)

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setPen(QColor(color))
    # 用 Apple Symbols 优先，fallback 到 PingFang SC
    f = QFont('Apple Symbols')
    f.setPixelSize(int(lsize * 0.9))
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    p.setFont(f)
    p.drawText(QRectF(0, 0, lsize, lsize), Qt.AlignmentFlag.AlignCenter, char)
    p.end()
    return QIcon(px)


# ── 红色删除菜单项（QWidgetAction） ──────────────────────────────────────

class _RedMenuAction(QWidgetAction):
    """菜单内删除条目：低饱和紫色，与 app 整体风格统一。"""
    _CLR = '#9a8fcc'   # 低饱和紫，比 accent 稍亮，区别于普通项

    def __init__(self, text: str, callback, menu: QMenu):
        super().__init__(menu)
        self._menu = menu
        self._cb   = callback

        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(6, 4, 20, 4)
        lay.setSpacing(6)

        # 图标
        ico_lbl = QLabel()
        pix = _mk_menu_icon('trash', self._CLR, 14).pixmap(QSize(15, 15))
        ico_lbl.setPixmap(pix)
        ico_lbl.setFixedSize(QSize(15, 15))
        lay.addWidget(ico_lbl)

        # 文字
        txt_lbl = QLabel(text)
        txt_lbl.setStyleSheet(
            f'color: {self._CLR}; font-size: 13px; background: transparent;')
        lay.addWidget(txt_lbl)
        lay.addStretch()

        w.setStyleSheet(
            'QWidget { border-radius: 4px; background: transparent; }'
            'QWidget:hover { background: rgba(124, 111, 168, 40); }'
        )
        w.setCursor(Qt.CursorShape.PointingHandCursor)
        w.mousePressEvent = lambda ev: (self._menu.close(), self._cb())
        self.setDefaultWidget(w)


# ── 侧边栏委托：hover / active 视觉 + tag 行 ··· 按钮 ───────────────────

class _SidebarTagDelegate(QStyledItemDelegate):
    """
    统一处理所有侧边栏行的绘制：
    - tag 行：hover 时右侧显示 ··· 按钮
    - file 行：hover 时文字变亮 + 左侧 2px 线；active 时 accent 色 + 左侧 3px 线
    - 所有行：hover/selected 背景透明（由 QSS 关闭默认背景，委托自己画）
    """
    _BTN_W    = 26
    _FG_IDLE  = QColor(160, 155, 175, 130)  # 和侧边栏文字同色系，低对比度融入背景
    _BTN_HV   = QColor(255, 255, 255, 0)    # 无背景，不画框
    _HV_BG    = QColor(255, 255, 255, 8)    # 极浅白色背景，hover 时显示
    _HV_LINE  = QColor(100, 95, 130, 180)   # hover 左侧细线
    _ACT_LINE = QColor(C['accent'])          # active 左侧亮线
    _ACT_FG   = QColor(C['fg'])             # active 文字颜色

    def paint(self, painter, option, index):
        from PyQt6.QtWidgets import QStyle
        from PyQt6.QtCore import QRectF
        data     = index.data(Qt.ItemDataRole.UserRole)
        is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        is_sel   = bool(option.state & QStyle.StateFlag.State_Selected)
        r        = option.rect

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── file 行：自定义绘制 ─────────────────────────────────
        if data and data[0] == 'file':
            fp      = data[1]
            tree    = self.parent()
            is_act  = hasattr(tree, '_active_fp') and tree._active_fp == fp

            # 背景（hover 时极淡白）
            if is_hover and not is_act:
                painter.fillRect(r, self._HV_BG)

            # active 背景（比 hover 略深）
            if is_act:
                painter.fillRect(r, QColor(255, 255, 255, 14))

            # 左侧竖线
            line_w = 3 if is_act else (2 if is_hover else 0)
            if line_w:
                line_color = self._ACT_LINE if is_act else self._HV_LINE
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(line_color)
                painter.drawRoundedRect(
                    QRectF(r.left(), r.top() + 2, line_w, r.height() - 4), 1, 1)

            # 文字颜色
            text = index.data(Qt.ItemDataRole.DisplayRole) or ''
            if is_act:
                fg = self._ACT_FG
            elif is_hover:
                fg = QColor(C['fg_file']).lighter(160)
            else:
                fg = QColor(C['fg_file'])

            painter.setPen(fg)
            f = QFont('PingFang SC', 12)
            if is_act:
                f.setWeight(QFont.Weight.Medium)
            painter.setFont(f)
            text_rect = r.adjusted(line_w + 6, 0, 0, 0)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, text)
            painter.restore()
            return

        # ── tag / header 行：交给 super() 正常绘制，再叠加 ··· ─
        super().paint(painter, option, index)

        if not data or data[0] not in ('tag', 'tag_pin'):
            painter.restore()
            return

        if not is_hover:
            painter.restore()
            return

        btn = self._btn_rect(r)
        painter.setPen(self._FG_IDLE)
        f2 = QFont('PingFang SC', 12)
        painter.setFont(f2)
        painter.drawText(btn, Qt.AlignmentFlag.AlignCenter, '···')
        painter.restore()

    def _btn_rect(self, item_rect: QRect) -> QRect:
        margin = 4
        h = item_rect.height() - margin * 2
        return QRect(item_rect.right() - self._BTN_W - margin,
                     item_rect.top() + margin,
                     self._BTN_W, h)

    def editorEvent(self, event, model, option, index):
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.MouseButtonRelease:
            data = index.data(Qt.ItemDataRole.UserRole)
            if data and data[0] in ('tag', 'tag_pin'):
                btn = self._btn_rect(option.rect)
                if btn.contains(event.pos()):
                    tree = self.parent()
                    item = tree.itemFromIndex(index)
                    if item:
                        global_pos = tree.viewport().mapToGlobal(event.pos())
                        tree._show_tag_menu(item, data, global_pos)
                    return True
        return super().editorEvent(event, model, option, index)


# ── 侧边栏 ────────────────────────────────────────────────────────────────

class Sidebar(QTreeWidget):
    file_selected = pyqtSignal(str)
    tag_rename    = pyqtSignal(str, str)   # old_full_tag, new_name
    tag_merge     = pyqtSignal(str, str)   # src_tag, dst_tag
    tag_delete    = pyqtSignal(str)        # tag_path

    def __init__(self, store: FileStore, parent=None):
        super().__init__(parent)
        self.store        = store
        self._txt_files: list[str] = []
        self._persist_key = 'sidebar_expanded'
        self._active_fp: str = ''   # 当前打开的文件路径

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
                background: transparent;
                color: {C['fg']};
            }}
            QTreeWidget::item:hover {{
                background: transparent;
            }}
            QTreeWidget::branch {{
                background: {C['bg_sidebar']};
            }}
        """)

        # 安装 ··· 悬停委托
        self.setItemDelegate(_SidebarTagDelegate(self))
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

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

    def set_active(self, fp: str):
        """标记当前打开的文件，委托会用 accent 色高亮它"""
        self._active_fp = fp
        self.viewport().update()

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

    _MENU_SS = f"""
        QMenu {{
            background: {C['bg_input']}; color: {C['fg']};
            border: 1px solid {C['border']}; border-radius: 6px;
            padding: 4px;
        }}
        QMenu::item {{
            padding: 5px 20px 5px 6px;
            border-radius: 4px;
        }}
        QMenu::item:selected {{ background: {C['bg_sel']}; }}
        QMenu::icon {{ padding-left: 6px; }}
        QMenu::separator {{ background: {C['border']}; height: 1px; margin: 4px 8px; }}
    """
    # 图标颜色与侧边栏 fg 一致
    _ICO_CLR  = '#8c82bb'   # 低饱和紫，与 app 调性一致

    def _show_tag_menu(self, item: QTreeWidgetItem, data: tuple, global_pos: QPoint):
        """弹出标签操作菜单（供右键和 ··· 按钮共用）"""
        tag_path = data[1]
        tag_name = tag_path.split('/')[-1]
        pinned   = self._get_pinned()

        menu = QMenu(self)
        menu.setStyleSheet(self._MENU_SS)

        # 置顶 / 取消置顶
        pin_text = '取消置顶' if tag_path in pinned else '置顶'
        pa = menu.addAction(pin_text)
        pa.setIcon(_mk_menu_icon('pin', C['accent']))
        pa.triggered.connect(lambda _, t=tag_path: self._toggle_pin(t))

        # 重命名 / 合并 / 删除（仅普通标签）
        if data[0] == 'tag':
            menu.addSeparator()

            act = menu.addAction(f'重命名「{tag_name}」')
            act.setIcon(_mk_menu_icon('pencil', self._ICO_CLR))
            act.triggered.connect(lambda: self._rename_tag(tag_path))

            # 合并到
            all_tags = self._collect_all_tags()
            if len(all_tags) > 1:
                merge_menu = menu.addMenu('合并到')
                merge_menu.setStyleSheet(self._MENU_SS)
                for t in all_tags:
                    if t != tag_path:
                        a = merge_menu.addAction(t)
                        a.triggered.connect(
                            lambda _, s=tag_path, d=t: self._merge_tag(s, d))

            menu.addSeparator()
            # 红色删除（QWidgetAction，内含对齐好的垃圾桶图标）
            del_act = _RedMenuAction(
                '删除标签',
                lambda t=tag_path: self.tag_delete.emit(t),
                menu)
            menu.addAction(del_act)

        menu.exec(global_pos)

    def _on_ctx(self, pos: QPoint):
        item = self.itemAt(pos)
        if not item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data[0] in ('tag', 'tag_pin'):
            self._show_tag_menu(item, data, self.mapToGlobal(pos))
            return

        # 文件行右键菜单
        menu = QMenu(self)
        menu.setStyleSheet(self._MENU_SS)
        if data and data[0] == 'file':
            fp = data[1]
            act_reveal = menu.addAction('在 Finder 中显示')
            act_reveal.triggered.connect(
                lambda checked=False, f=fp: subprocess.run(['open', '-R', f]))
            if fp in self.store.get_txt_files():
                act_rm = menu.addAction('移除')
                act_rm.triggered.connect(
                    lambda checked=False, f=fp: (self.store.remove_txt(f),
                             self.window()._refresh_sidebar()))
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
        self._db.start(350)   # 350ms 防抖，大文件搜索不卡 UI

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

    def clear_search(self):
        """切换文件时调用：清空关键词 + 重置计数"""
        self._input.blockSignals(True)
        self._input.clear()
        self._input.blockSignals(False)
        self._matches = []
        self._cur_idx = -1
        self._count_lbl.setText('')
        self.set_count(0)

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


# ── 下拉列表 hover delegate（macOS 原生样式会覆盖 stylesheet，需手动绘制）──

class _ComboHoverDelegate(QStyledItemDelegate):
    """给 QComboBox 的下拉列表提供低饱和紫色 hover/selected 效果"""
    _HOVER    = QColor(124, 111, 168, 55)
    _SELECTED = QColor(124, 111, 168, 90)
    _BG       = QColor(C['bg_input'])
    _FG       = QColor(C['fg'])

    def paint(self, painter, option, index):
        from PyQt6.QtWidgets import QStyle
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hover    = bool(option.state & QStyle.StateFlag.State_MouseOver)

        if is_selected:
            painter.fillRect(option.rect, self._SELECTED)
        elif is_hover:
            painter.fillRect(option.rect, self._HOVER)
        else:
            painter.fillRect(option.rect, self._BG)

        # 勾选标记（当前选中项）
        check_data = index.data(Qt.ItemDataRole.CheckStateRole)
        left = option.rect.left() + 10
        if check_data == Qt.CheckState.Checked:
            painter.setPen(self._FG)
            painter.drawText(
                option.rect.adjusted(left - 8, 0, 0, 0),
                Qt.AlignmentFlag.AlignVCenter, '✓')
            left += 14

        painter.setPen(self._FG)
        text_rect = option.rect.adjusted(left, 0, -8, 0)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ''
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, text)
        painter.restore()

    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        return sh.__class__(sh.width(), max(sh.height(), 26))


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
            selection-background-color: transparent;
            outline: none;
        }}
        QComboBox QAbstractItemView::item {{
            padding: 4px 8px;
        }}
        QComboBox QAbstractItemView::item:hover {{
            background: {C['accent']}28; color: {C['fg']};
        }}
        QComboBox QAbstractItemView::item:selected {{
            background: {C['accent']}40; color: {C['fg']};
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
        self._input.setMaximumWidth(280)
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
        self._tag_combo.setMinimumWidth(80)
        self._tag_combo.setMaximumWidth(200)
        self._tag_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._tag_combo.currentIndexChanged.connect(lambda: self._run_search())
        # macOS 原生样式覆盖 stylesheet，用自定义 delegate 绘制 hover
        self._tag_combo.view().setStyleSheet(
            f"QAbstractItemView {{ background: {C['bg_input']};"
            f"border: 1px solid {C['border']}; outline: none; }}")
        self._tag_combo.view().setItemDelegate(_ComboHoverDelegate(self._tag_combo))
        self._tag_combo.view().setMouseTracking(True)
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
            QPushButton:hover {{ background: #9b8cc4; }}
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

        files = self.store.get_txt_files()
        for i, fp in enumerate(files):
            # 每处理 10 个文件释放一次事件循环，避免卡 UI
            if i % 10 == 0:
                QApplication.processEvents()
            if tag_filter:
                scanned = TagScanner.scan(fp)
                if not any(t == tag_filter or t.startswith(tag_filter + '/') for t in scanned):
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

            # 每条命中（每文件最多渲染 50 条，避免大文件卡顿）
            _MAX_PER_FILE = 50
            for i, (pos, mlen) in enumerate(hits):
                if i >= _MAX_PER_FILE:
                    rest = len(hits) - _MAX_PER_FILE
                    more_lbl = QLabel(f'  …还有 {rest} 条，请缩小搜索范围')
                    more_lbl.setStyleSheet(
                        f'color: {C["fg_dim"]}; font-size: 12px; padding: 4px 12px;')
                    self._list_vlay.insertWidget(self._list_vlay.count()-1, more_lbl)
                    break
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
            QPushButton:hover {{ background: #9b8cc4; }}
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


# ── 帮助说明 ──────────────────────────────────────────────────────────────

class HelpDialog(QDialog):
    _SS = f"""
        QDialog {{ background: {C['bg']}; }}
        QScrollArea {{ background: transparent; border: none; }}
        QWidget#content {{ background: transparent; }}
        QLabel {{ background: transparent; }}
        QScrollBar:vertical {{ background: transparent; width: 4px; }}
        QScrollBar::handle:vertical {{ background: #444448; border-radius: 2px; min-height: 20px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QPushButton {{
            background: {C['bg_sel']}; color: {C['fg_dim']};
            border: none; border-radius: 5px; padding: 5px 20px; font-size: 13px;
        }}
        QPushButton:hover {{ color: {C['fg']}; }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('功能说明')
        self.resize(580, 720)
        self.setMinimumSize(460, 500)
        self.setStyleSheet(self._SS)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content.setObjectName('content')
        lay = QVBoxLayout(content)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(0)
        scroll.setWidget(content)
        root.addWidget(scroll)

        def title(text):
            lbl = QLabel(text)
            lbl.setStyleSheet(f'color: {C["fg"]}; font-size: 17px; font-weight: bold; padding-top: 18px; padding-bottom: 6px;')
            lay.addWidget(lbl)

        def subtitle(text):
            lbl = QLabel(text)
            lbl.setStyleSheet(f'color: {C["fg_tag"]}; font-size: 13px; padding-bottom: 10px;')
            lbl.setWordWrap(True)
            lay.addWidget(lbl)

        def sep():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setStyleSheet(f'color: {C["border"]}; margin: 6px 0;')
            lay.addWidget(line)

        def color_row(dot_color: str, label: str, desc: str, examples: str):
            row = QWidget()
            row.setStyleSheet(f'background: {C["bg_input"]}; border-radius: 7px; margin-bottom: 8px;')
            h = QVBoxLayout(row)
            h.setContentsMargins(14, 10, 14, 10)
            h.setSpacing(4)
            # 首行：色点 + 标签
            top_row = QHBoxLayout()
            top_row.setSpacing(8)
            dot = QLabel('●')
            dot.setStyleSheet(f'color: {dot_color}; font-size: 16px;')
            dot.setFixedWidth(18)
            top_row.addWidget(dot)
            lbl = QLabel(label)
            lbl.setStyleSheet(f'color: {C["fg"]}; font-size: 14px; font-weight: bold;')
            top_row.addWidget(lbl)
            top_row.addStretch()
            h.addLayout(top_row)
            # 说明
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(f'color: {C["fg_tag"]}; font-size: 12px; padding-left: 26px;')
            desc_lbl.setWordWrap(True)
            h.addWidget(desc_lbl)
            # 例词
            ex_lbl = QLabel(examples)
            ex_lbl.setStyleSheet(f'color: {dot_color}; font-size: 12px; padding-left: 26px; opacity: 0.85;')
            ex_lbl.setWordWrap(True)
            h.addWidget(ex_lbl)
            lay.addWidget(row)

        def shortcut_row(keys: str, desc: str):
            row = QWidget()
            row.setStyleSheet('background: transparent; margin-bottom: 4px;')
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 2, 0, 2)
            h.setSpacing(12)
            key_lbl = QLabel(keys)
            key_lbl.setFixedWidth(160)
            key_lbl.setStyleSheet(f"""
                color: {C['fg']};
                background: {C['bg_input']};
                border-radius: 5px;
                padding: 3px 10px;
                font-size: 12px;
                font-family: monospace;
            """)
            h.addWidget(key_lbl)
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(f'color: {C["fg_tag"]}; font-size: 13px;')
            h.addWidget(desc_lbl)
            h.addStretch()
            lay.addWidget(row)

        # ── 话语标记词
        title('话语标记词高亮')
        subtitle('话语标记词（Discourse Markers）是演讲和写作中用于组织逻辑、连接句子的词语。'
                 '开启高亮后，可以直观看出说话人的逻辑结构和表达习惯。')
        subtitle('开启方式：视图 → 话语标记词高亮')
        sep()

        color_row('#c47a3a', '橙色 · 因果类',
                  '表示原因与结果的连接，揭示说话人的推理链条。',
                  '因为、所以、由于、因此、既然、由此可见、以致、原来…')
        color_row('#5a9ac4', '蓝色 · 转折类',
                  '表示观点的反转或对比，常出现在论证的关键节点。',
                  '但是、不过、然而、可是、虽然、尽管、反而、与此相反…')
        color_row('#5aab7a', '绿色 · 递进 / 举例类',
                  '表示补充、加强或具体说明，帮助理解论点的展开方式。',
                  '而且、比如说、例如、换句话说、不仅、同时、还有、另外…')
        color_row('#9e8cc0', '淡紫 · 结构 / 衔接类',
                  '标示演讲的节奏和段落划分，如开头、推进、收尾。',
                  '首先、其次、最后、接下来、那么、总之、总的来说、关于…')

        # ── 语气词
        title('语气词高亮')
        subtitle('语气词是口语中的填充音和习惯用语，在逐字稿中频繁出现。高亮后可快速识别口头禅密度。')
        subtitle('开启方式：视图 → 语气词高亮　　分析频率：视图 → 口头禅频率分析')
        sep()

        ex = QLabel('嗯、哎、呃、额、哦、哟、嗐、哼　/　啊、吧、呢、嘛、呀\n'
                    '就是、那个、这个、然后、其实、反正　/　对对对、好吧、是吧…')
        ex.setStyleSheet(f'color: #a07848; font-size: 12px; padding: 4px 0 12px 0;')
        ex.setWordWrap(True)
        lay.addWidget(ex)

        # ── 标注功能
        title('标注功能 · 像剪辑师一样精读逐字稿')
        subtitle('选中 5 个字以上，松开鼠标，浮动工具条自动弹出。选择颜色即完成标注，无需额外操作。')
        sep()

        # # 自由备注（重点功能）
        note_box = QWidget()
        note_box.setStyleSheet(
            f'background: {C["bg_sel"]}; border: 1px solid {C["accent"]}; '
            f'border-radius: 8px; margin-bottom: 10px;'
        )
        nb = QVBoxLayout(note_box)
        nb.setContentsMargins(16, 12, 16, 12)
        nb.setSpacing(5)
        nb_title = QLabel('# 自由备注标签　←　最核心的功能')
        nb_title.setStyleSheet(f'color: {C["accent"]}; font-size: 14px; font-weight: bold;')
        nb.addWidget(nb_title)
        nb_desc = QLabel(
            '选中任意文字后，点击浮动工具条里的 # 按钮，选一个底色，再输入你自己的备注文字，回车确认。\n\n'
            '备注会显示在右侧标注面板，格式为  # 你写的内容 ，点击可跳转到原文位置。\n\n'
            '适合场景：\n'
            '・「这段可以剪掉」「嘉宾最强观点」「需要加 B-roll」\n'
            '・「第二集用」「和第3分钟那句呼应」「语速太快需要处理」\n'
            '・任何你想记录的导演/剪辑思路，直接写在原文上，不影响文字本身。'
        )
        nb_desc.setStyleSheet(f'color: {C["fg_tag"]}; font-size: 12px; line-height: 1.6;')
        nb_desc.setWordWrap(True)
        nb.addWidget(nb_desc)
        lay.addWidget(note_box)

        annot_rows = [
            ('#e8c870', '黄色高亮', '核心观点 / 关键结论',
             '适合标记嘉宾的核心论断、精华金句，剪辑时优先保留。'),
            ('#5ec87a', '绿色高亮', '精彩表达 / 可直接用',
             '语言流畅、表达完整，可作为成片素材直接使用。'),
            ('#e86090', '粉色高亮', '需要关注 / 存疑内容',
             '事实待核实、逻辑跳跃、或需要补拍的段落。'),
            ('#a878f0', '紫色高亮', '延伸话题 / 备用素材',
             '有趣但主题外，或可用于下一期节目的内容。'),
            (C['fg'], '加粗', '强调重点词',
             '在长段落中标出最重要的词或短语，快速定位。'),
            (C['fg'], '下划线', '专有名词 / 需查证',
             '人名、地名、术语等需要核实或添加字幕注释的词。'),
        ]

        for dot_c, label, usage, tip in annot_rows:
            row = QWidget()
            row.setStyleSheet(f'background: {C["bg_input"]}; border-radius: 7px; margin-bottom: 6px;')
            rv = QVBoxLayout(row)
            rv.setContentsMargins(14, 9, 14, 9)
            rv.setSpacing(3)
            top_h = QHBoxLayout()
            top_h.setSpacing(8)
            dot = QLabel('●')
            dot.setStyleSheet(f'color: {dot_c}; font-size: 15px;')
            dot.setFixedWidth(18)
            top_h.addWidget(dot)
            lbl_w = QLabel(f'<b>{label}</b>　<span style="color:{C["fg_tag"]}; font-size:12px;">{usage}</span>')
            lbl_w.setStyleSheet(f'color: {C["fg"]}; font-size: 13px;')
            top_h.addWidget(lbl_w)
            top_h.addStretch()
            rv.addLayout(top_h)
            tip_w = QLabel(tip)
            tip_w.setStyleSheet(f'color: {C["fg_dim"]}; font-size: 12px; padding-left: 26px;')
            tip_w.setWordWrap(True)
            rv.addWidget(tip_w)
            lay.addWidget(row)

        workflow = QLabel(
            '💡 推荐工作流：读完全文先用「语气词高亮」找出节奏断点 → '
            '再开「话语标记词」看逻辑骨架 → '
            '最后用黄/绿/粉/紫标注段落，打开标注面板（Ctrl+\\）纵览全局，'
            '确定剪辑取舍。'
        )
        workflow.setStyleSheet(
            f'color: {C["fg_tag"]}; font-size: 12px; '
            f'background: {C["bg_sel"]}; border-radius: 6px; '
            f'padding: 10px 14px; margin-top: 8px; margin-bottom: 4px;'
        )
        workflow.setWordWrap(True)
        lay.addWidget(workflow)

        # ── 快捷键
        title('常用快捷键')
        sep()
        pairs = [
            ('Ctrl+K',         '全局搜索'),
            ('Ctrl+F',         '当前文件内搜索'),
            ('Ctrl+S',         '保存当前文件'),
            ('Ctrl+\\\\',        '显示 / 隐藏标注面板'),
            ('Ctrl+Shift+Z',   '禅定模式（隐藏所有界面）'),
            ('Cmd / Ctrl + ↑', '跳到文章开头'),
            ('Cmd / Ctrl + ↓', '跳到文章末尾'),
            ('F5',             '刷新侧栏标签'),
        ]
        for keys, desc in pairs:
            shortcut_row(keys, desc)

        lay.addStretch()

        # 底部关闭按钮
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(32, 10, 32, 16)
        btn_row.addStretch()
        close_btn = QPushButton('关闭')
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)


# ── 个人口头禅自动发现算法（基于改造版 TF-IDF + 中文口语参考语料）────────

# 通用中文口语参考词频（每千汉字出现次数，基于 BCC 口语子库估算）
# 数值越大 = 越通用，该词对个人分析价值越低
_SPOKEN_REF: dict = {
    # 极高频通用词（人人都说，个人价值 ≈ 0）
    '这个': 18.0, '就是': 14.0, '那个':  9.0, '一个': 12.0, '什么': 12.0,
    '我们':  9.0, '没有':  8.0, '这是':  6.0, '那是':  4.0, '不是':  7.0,
    '可以':  6.0, '知道':  5.0, '所以':  5.0, '因为':  4.5, '但是':  4.5,
    '然后':  5.5, '觉得':  4.5, '他们':  5.0, '你们':  3.0, '感觉':  3.5,
    '应该':  3.0, '已经':  4.0, '如果':  3.0, '虽然':  2.0, '还是':  4.0,
    '或者':  2.0, '而且':  3.0, '非常':  3.0, '很多':  4.0, '真的':  4.5,
    '其实':  4.0, '只是':  2.5, '一些':  3.0, '一样':  3.0, '这样':  4.0,
    '那样':  2.0, '这种':  3.0, '那种':  2.0, '最后':  3.0, '之后':  3.0,
    '之前':  2.0, '开始':  3.0, '发现':  2.0, '认为':  2.0, '希望':  2.0,
    '需要':  2.5, '问题':  4.0, '情况':  2.0, '关系':  2.0, '时候':  5.5,
    '地方':  2.5, '事情':  2.5, '工作':  2.5, '生活':  2.5, '自己':  4.0,
    '比如':  2.5, '那么':  3.0, '这么':  3.0, '怎么':  3.5, '好像':  2.5,
    '不过':  2.0, '比较':  2.0, '大家':  3.0, '所有':  2.0, '真正':  1.5,
    '一种':  2.0, '每个':  1.5, '对于':  2.0, '关于':  1.5, '里面':  2.5,
    '个人':  2.0, '还有':  4.5, '我想':  2.0, '的话':  2.5, '是的':  2.0,
    '有人':  1.5, '任何':  1.0, '来说':  2.5, '就好':  1.5, '能够':  1.5,
    # 3字通用短语
    '的时候':  5.5, '就是说':  2.0, '我觉得':  1.5, '比如说':  1.2,
    '也就是':  0.9, '不知道':  2.5, '不一定':  1.0, '不一样':  1.0,
    '你知道':  1.0, '所以说':  1.0, '是一个':  1.5, '有一个':  1.5,
    '但是我':  0.8, '然后我':  0.8, '其实我':  0.6, '因为我':  0.6,
    '所以我':  0.7, '一定要':  0.8, '可以的':  0.6, '没有的':  0.4,
    # 4字通用短语
    '也就是说':  0.7, '就是这样':  0.3, '总的来说':  0.4, '简单来说': 0.2,
}

# 未知 n-gram 的默认参考频率（长度越长越稀有）
_REF_DEFAULT = {2: 2.0, 3: 0.15, 4: 0.025, 5: 0.006}


def discover_verbal_tics(files: list, all_files: list | None = None,
                         top_n: int = 30) -> list:
    """
    从逐字稿文件中自动发现说话人的个人口头禅。

    核心算法：双层 TF-IDF
    ─────────────────────────────────────────────
    第一层：BCC 基准（过滤通用中文高频词，如"这个"、"就是"）
    第二层：全库基准（过滤话题词，如"知行合一"在阳明专题里高频但不是口头禅）

    scoring = BCC_excess × topic_distribution × cross_file_conf × √len
      BCC_excess        = 全库词频 / 通用中文基准词频（过滤通用词）
      topic_distribution = 全库词频 / 所选文件词频（过滤话题词；越接近1越像口头禅）
      cross_file_conf   = 出现文件比例（跨文件一致性）
    """
    import math
    _CHINESE = re.compile(r'[^\u4e00-\u9fff]')
    _CLAUSE_SEP = re.compile(r'[，。！？、；：\n""''【】（）\[\]…—~～]')

    def _scan_files(fps: list) -> tuple:
        """返回 (file_grams_list, total_dict, file_cnt_dict, total_chars)"""
        fgs, tot, fcnt, tchars = [], {}, {}, 0
        for fp in fps:
            try:
                raw = Path(fp).read_text('utf-8', errors='ignore')
            except Exception:
                continue
            local: dict = {}
            for clause in _CLAUSE_SEP.split(raw):
                chars = _CHINESE.sub('', clause)
                tchars += len(chars)
                if len(chars) < 2:
                    continue
                for n in range(2, 6):
                    for i in range(len(chars) - n + 1):
                        g = chars[i:i+n]
                        local[g] = local.get(g, 0) + 1
            fgs.append(local)
            for g, c in local.items():
                tot[g] = tot.get(g, 0) + c
                fcnt[g] = fcnt.get(g, 0) + 1
        return fgs, tot, fcnt, tchars

    # 扫描所选文件（TF）
    sel_grams, sel_total, sel_fcnt, sel_chars = _scan_files(files)
    if not sel_grams or sel_chars == 0:
        return []
    n_files = len(sel_grams)

    # 扫描全库文件（全局基准，过滤话题词）
    _all = list(dict.fromkeys((all_files or []) + files))  # 去重，确保包含所选
    _, all_total, _, all_chars = _scan_files(_all) if _all != files else (None, sel_total, None, sel_chars)
    all_is_same = (set(_all) == set(files))   # 所选文件 = 全库时无法区分话题词

    # 自适应最低绝对频次
    min_count = max(3, sel_chars // 3000)

    # 候选筛选：BCC 超额比值 > 1.5（过滤通用词）
    candidates: dict = {}
    for g, c in sel_total.items():
        if c < min_count:
            continue
        bcc_ref  = _SPOKEN_REF.get(g, _REF_DEFAULT.get(len(g), 0.006))
        sel_rate = c / sel_chars * 1000
        bcc_excess = sel_rate / bcc_ref
        if bcc_excess < 1.5:
            continue

        # 话题浓度惩罚：该词在所选文件的频率 vs 全库频率
        # topic_dist ∈ (0,1]：越接近 1 = 越均匀分布 = 越像口头禅
        if not all_is_same and all_chars > 0:
            all_c    = all_total.get(g, c)
            all_rate = all_c / all_chars * 1000
            # 话题浓度 = sel_rate / all_rate，>1 表示该词集中于所选话题
            topic_conc   = sel_rate / max(all_rate, 0.001)
            topic_dist   = 1.0 / max(topic_conc, 1.0) ** 0.6  # 浓度越高惩罚越重
            global_excess = all_rate / bcc_ref   # 基于全库的超额（更准确）
        else:
            topic_dist    = 1.0
            global_excess = bcc_excess

        candidates[g] = (c, global_excess, topic_dist)

    if not candidates:
        return []

    # 去重 ①：子串抑制
    by_len = sorted(candidates, key=len, reverse=True)
    suppressed: set = set()
    for i, longer in enumerate(by_len):
        if longer in suppressed:
            continue
        c_long = candidates[longer][0]
        for shorter in by_len[i+1:]:
            if shorter in suppressed:
                continue
            if shorter in longer and c_long >= candidates[shorter][0] * 0.50:
                suppressed.add(shorter)

    # 去重 ②：同长度滑窗相邻碎片抑制
    all_cands = [g for g in by_len if g not in suppressed]
    for i, a in enumerate(all_cands):
        if a in suppressed:
            continue
        for b in all_cands[i+1:]:
            if b in suppressed or len(b) != len(a):
                continue
            if a[1:] == b[:-1] or b[1:] == a[:-1]:
                ca, ea, _ = candidates[a]
                cb, eb, _ = candidates[b]
                if abs(ca - cb) / max(ca, cb) < 0.30:
                    suppressed.add(a if ea < eb else b)

    # 综合评分
    results = []
    for g in by_len:
        if g in suppressed:
            continue
        c, g_excess, t_dist = candidates[g]
        fc = sel_fcnt[g]
        file_conf = 0.4 + 0.6 * (fc / n_files)
        score = g_excess * t_dist * file_conf * math.sqrt(len(g))
        rate  = c / sel_chars * 1000
        results.append({
            'phrase': g, 'count': c, 'file_count': fc,
            'n_files': n_files, 'rate': rate,
            'excess': g_excess, 'topic_dist': t_dist, 'score': score,
        })

    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:top_n]


# ── 口头禅频率分析 ────────────────────────────────────────────────────────

class FillerAnalysisDialog(QDialog):
    """高频口头禅分析：按标签筛选文件，统计各语气词出现频率"""

    _SS = f"""
        QDialog {{ background: {C['bg']}; color: {C['fg']}; }}
        QLabel {{ color: {C['fg']}; }}
        QComboBox {{
            background: {C['bg_sel']}; color: {C['fg']};
            border: 1px solid {C['border']}; border-radius: 5px;
            padding: 3px 10px; font-size: 13px;
        }}
        QComboBox::drop-down {{ border: none; width: 16px; }}
        QComboBox QAbstractItemView {{
            background: {C['bg_input']}; color: {C['fg']};
            border: 1px solid {C['border']};
            selection-background-color: transparent;
            outline: none;
        }}
        QComboBox QAbstractItemView::item {{
            padding: 4px 8px;
        }}
        QComboBox QAbstractItemView::item:hover {{
            background: {C['accent']}28; color: {C['fg']};
        }}
        QComboBox QAbstractItemView::item:selected {{
            background: {C['accent']}40; color: {C['fg']};
        }}
        QPushButton {{
            background: {C['accent']}; color: white;
            border: none; border-radius: 5px;
            padding: 5px 18px; font-size: 13px;
        }}
        QPushButton:hover {{ background: #9b8cc4; }}
        QScrollBar:vertical {{ background: transparent; width: 4px; }}
        QScrollBar::handle:vertical {{ background: #444448; border-radius: 2px; min-height: 20px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """

    def __init__(self, store: 'FileStore', parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle('个人口头禅发现')
        self.resize(560, 680)
        self.setMinimumSize(420, 400)
        self.setStyleSheet(self._SS)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        # ── 顶部：标签选择 + 分析按钮
        top = QHBoxLayout()
        top.setSpacing(10)
        lbl = QLabel('分析范围：')
        lbl.setStyleSheet(f'color: {C["fg_tag"]}; font-size: 13px;')
        top.addWidget(lbl)

        self._tag_combo = QComboBox()
        self._tag_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        top.addWidget(self._tag_combo)

        btn = QPushButton('开始分析')
        btn.setFixedWidth(90)
        btn.clicked.connect(self._run)
        top.addWidget(btn)
        root.addLayout(top)

        # ── 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f'color: {C["border"]};')
        root.addWidget(sep)

        # ── 结果区（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._result_widget = QWidget()
        self._result_layout = QVBoxLayout(self._result_widget)
        self._result_layout.setContentsMargins(0, 4, 0, 4)
        self._result_layout.setSpacing(6)
        self._result_layout.addStretch()
        scroll.setWidget(self._result_widget)
        root.addWidget(scroll)

        # ── 底部统计
        self._summary_lbl = QLabel('')
        self._summary_lbl.setStyleSheet(f'color: {C["fg_dim"]}; font-size: 11px;')
        root.addWidget(self._summary_lbl)

        self._populate_tags()

    def _populate_tags(self):
        self._tag_combo.clear()
        # 用单独列表维护对应关系，避免 currentData() 类型问题
        self._tag_list: list[str | None] = [None]   # index 0 → 全部
        self._tag_combo.addItem('全部文件')
        txt_files = self.store.get_txt_files()
        self._tree = TagScanner.build_tree(txt_files)
        for tag in sorted(self._tree.keys()):
            self._tag_list.append(tag)
            count = len(self._tree[tag])
            self._tag_combo.addItem(f'#{tag}  ({count})')

    def _get_files(self) -> list[str]:
        idx = self._tag_combo.currentIndex()
        if idx <= 0 or idx >= len(self._tag_list):
            return self.store.get_txt_files()
        tag = self._tag_list[idx]
        if tag is None:
            return self.store.get_txt_files()
        return self._tree.get(tag, [])

    def _run(self):
        files = self._get_files()

        # 清空旧结果
        while self._result_layout.count() > 1:
            item = self._result_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not files:
            self._show_empty('没有找到文件')
            return

        all_files = self.store.get_txt_files()
        results = discover_verbal_tics(files, all_files)

        if not results:
            self._show_empty('语料不足，暂未发现高频短语')
            return

        max_count = results[0]['count']
        for rank, r in enumerate(results, 1):
            row = self._make_row(rank, r, max_count)
            self._result_layout.insertWidget(rank - 1, row)

        same_as_all = set(files) == set(all_files)
        hint = '（建议导入更多不同话题的文件，结果会更准确）' if same_as_all else ''
        self._summary_lbl.setText(
            f'分析 {len(files)}/{len(all_files)} 个文件 · 发现 {len(results)} 个高频短语 {hint}'
        )

    def _show_empty(self, msg: str):
        lbl = QLabel(msg)
        lbl.setStyleSheet(f'color: {C["fg_dim"]}; font-size: 13px;')
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._result_layout.insertWidget(0, lbl)
        self._summary_lbl.setText('')

    def _make_row(self, rank: int, r: dict, max_count: int) -> QWidget:
        phrase     = r['phrase']
        count      = r['count']
        file_count = r['file_count']
        n_files    = r['n_files']
        rate       = r['rate']

        row = QWidget()
        row.setStyleSheet(f'QWidget {{ background: {C["bg_input"]}; border-radius: 6px; }}')
        h = QHBoxLayout(row)
        h.setContentsMargins(12, 8, 12, 8)
        h.setSpacing(10)

        # 排名
        rank_lbl = QLabel(f'{rank}')
        rank_lbl.setFixedWidth(24)
        rank_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        rank_lbl.setStyleSheet(f'color: {C["fg_dim"]}; font-size: 11px; background: transparent;')
        h.addWidget(rank_lbl)

        # 短语
        phrase_lbl = QLabel(phrase)
        phrase_lbl.setFixedWidth(90)
        phrase_lbl.setStyleSheet(f'color: {C["fg"]}; font-size: 14px; background: transparent;')
        h.addWidget(phrase_lbl)

        # 进度条
        bar = QProgressBar()
        bar.setRange(0, max_count)
        bar.setValue(count)
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        ratio = count / max_count if max_count > 0 else 0
        bar_color = C['accent'] if ratio > 0.5 else ('#9b8cc4' if ratio > 0.2 else '#4a4060')
        bar.setStyleSheet(f"""
            QProgressBar {{ background: {C['bg_sel']}; border: none; border-radius: 3px; }}
            QProgressBar::chunk {{ background: {bar_color}; border-radius: 3px; }}
        """)
        h.addWidget(bar, 1)

        # 次数 + 超额倍数
        excess = r.get('excess', 1.0)
        meta_lbl = QLabel(f'{count}次  ×{excess:.0f}')
        meta_lbl.setFixedWidth(90)
        meta_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        meta_lbl.setToolTip(f'你说这个词的频率是普通人的 {excess:.1f} 倍')
        meta_lbl.setStyleSheet(
            f'color: {C["accent"] if count == max_count else C["fg_tag"]}; '
            f'font-size: 12px; background: transparent;'
        )
        h.addWidget(meta_lbl)

        # 跨文件指示（越满越像口头禅）
        spread = file_count / n_files if n_files > 1 else 1.0
        spread_lbl = QLabel(f'{file_count}/{n_files}')
        spread_lbl.setFixedWidth(36)
        spread_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spread_color = C['accent'] if spread >= 0.8 else ('#9b8cc4' if spread >= 0.5 else C['fg_dim'])
        spread_lbl.setToolTip(f'在 {n_files} 个文件中的 {file_count} 个出现（越高越像口头禅）')
        spread_lbl.setStyleSheet(
            f'color: {spread_color}; font-size: 11px; background: transparent;'
        )
        h.addWidget(spread_lbl)

        return row


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
        sidebar_wrap.setMinimumWidth(240)
        sidebar_wrap.setMaximumWidth(400)
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
        self._sidebar.tag_delete.connect(self._delete_tag)
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
        import random
        _mottos = [
            'purple loop\n祝你引流无量',
            '把逐字稿读透\n才能剪出真正好的内容',
        ]
        self._empty_lbl = QLabel(random.choice(_mottos))
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(f"""
            color: #2e2f33;
            font-size: 22px;
            font-family: 'LXGW WenKai', 'PingFang SC';
            line-height: 2;
            background: {C['bg']};
        """)

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
        self._split.setSizes([280, 1000])

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
        self._filler_action = QAction('语气词高亮', self)
        self._filler_action.setCheckable(True)
        self._filler_action.setChecked(False)
        self._filler_action.triggered.connect(self._toggle_fillers)
        vm.addAction(self._filler_action)
        self._dm_action = QAction('话语标记词高亮', self)
        self._dm_action.setCheckable(True)
        self._dm_action.setChecked(False)
        self._dm_action.triggered.connect(self._toggle_dm)
        vm.addAction(self._dm_action)
        _act(vm, '口头禅频率分析…', self._open_filler_analysis)
        vm.addSeparator()
        _act(vm, '刷新侧栏', self._refresh_sidebar, 'F5')

        # 帮助
        hm = mb.addMenu('帮助')
        hm.setStyleSheet(_ms)
        _act(hm, '功能说明…', self._open_help)

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
        entering = self._zen

        # 需要淡出/淡入的 widget 列表
        targets = [
            self._split.widget(0),   # 侧栏
            self.menuBar(),
            self.statusBar(),
            self._progress_bar,
            self._txt_editor._count_lbl,
        ]
        if self._annot_panel_action.isChecked():
            targets.append(self._annot_panel)

        if entering:
            self._pre_zen_annot = self._annot_panel_action.isChecked()
            self._annot_panel_action.setChecked(False)
            self._fade_widgets(targets, fade_in=False,
                               on_done=lambda: [w.hide() for w in targets])
        else:
            for w in targets:
                w.show()
            self._fade_widgets(targets, fade_in=True)
            # 只恢复进入禅定前的状态，不多做
            if self._pre_zen_annot:
                self._annot_panel.show()
            else:
                self._annot_panel.hide()
            self._annot_panel_action.setChecked(self._pre_zen_annot)

    def _fade_widgets(self, widgets, fade_in: bool, on_done=None):
        """对多个 widget 同时做淡入/淡出动画（150ms）"""
        start, end = (0.0, 1.0) if fade_in else (1.0, 0.0)
        anims = []
        for w in widgets:
            effect = QGraphicsOpacityEffect(w)
            w.setGraphicsEffect(effect)
            anim = QPropertyAnimation(effect, b'opacity', self)
            anim.setDuration(150)
            anim.setStartValue(start)
            anim.setEndValue(end)
            anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
            anims.append(anim)
        if on_done and anims:
            anims[-1].finished.connect(on_done)
        for a in anims:
            a.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _toggle_fillers(self):
        enabled = self._filler_action.isChecked()
        self._txt_editor._highlighter.set_show_fillers(enabled)

    def _toggle_dm(self):
        enabled = self._dm_action.isChecked()
        self._txt_editor._highlighter.set_show_dm(enabled)

    def _open_filler_analysis(self):
        dlg = FillerAnalysisDialog(self.store, self)
        geo = self.geometry()
        dlg.move(
            geo.x() + (geo.width()  - dlg.width())  // 2,
            geo.y() + (geo.height() - dlg.height()) // 3,
        )
        dlg.exec()

    def _open_help(self):
        dlg = HelpDialog(self)
        geo = self.geometry()
        dlg.move(
            geo.x() + (geo.width()  - dlg.width())  // 2,
            geo.y() + (geo.height() - dlg.height()) // 3,
        )
        dlg.exec()

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
        self._pending_annot_id = None   # 防止跨文件标注误操作
        # 清除旧文件的搜索状态，防止 QTextCursor 悬空
        self._search_matches = []
        self._search_idx = -1
        self._clear_search_hl()
        if self._search_bar.isVisible():
            self._search_bar.clear_search()   # 同时清空搜索框文字
        # 重置标注面板过滤器，避免跨文件保留上个文件的过滤状态
        self._annot_panel._set_filter(None)
        self._txt_editor.load_file(path)
        self._annot_panel.refresh(path)
        self._stack.setCurrentWidget(self._txt_editor)
        self._sidebar.set_active(path)
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

        reply = QMessageBox.question(
            self, '确认重命名',
            f'将所有 {old_tag} 重命名为 {new_tag}？\n此操作会修改 .txt 文件内容，无法撤销。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 用正则精确匹配：#old_path 后跟 / 或非标签字符，避免误改同前缀的其他标签
        # 例如重命名 #阳明心学智慧 时不误改 #阳明心学智慧好
        _pat = re.compile(
            r'(?<=#)' + re.escape(old_path) + r'(?=/|\s|$|[，。！？、；：\n\r])'
        )

        changed = 0
        for fp_str in self.store.get_txt_files():
            fp = Path(fp_str)
            try:
                text = fp.read_text('utf-8')
                new_text = _pat.sub(new_path, text)
                if new_text != text:
                    fp.write_text(new_text, 'utf-8')
                    changed += 1
                    if fp_str == self._fp:
                        self._txt_editor.load_file(fp_str)
            except Exception:
                pass
        self._refresh_sidebar()
        self.statusBar().showMessage(
            f'已将 #{old_path} 重命名为 #{new_path}，影响 {changed} 个文件', 4000)

    def _merge_tag(self, src: str, dst: str):
        """将 #src 全部替换为 #dst（含子标签）"""
        _pat = re.compile(
            r'(?<=#)' + re.escape(src) + r'(?=/|\s|$|[，。！？、；：\n\r])'
        )
        changed = 0
        for fp_str in self.store.get_txt_files():
            fp = Path(fp_str)
            try:
                text = fp.read_text('utf-8')
                new_text = _pat.sub(dst, text)
                if new_text != text:
                    fp.write_text(new_text, 'utf-8')
                    changed += 1
                    if fp_str == self._fp:
                        self._txt_editor.load_file(fp_str)
            except Exception:
                pass
        self._refresh_sidebar()
        self.statusBar().showMessage(
            f'已将 #{src} 合并到 #{dst}，影响 {changed} 个文件', 4000)

    def _delete_tag(self, tag_path: str):
        """从所有 .txt 文件中删除 #tag_path（仅移除标签标记，保留内容）"""
        reply = QMessageBox.question(
            self, '删除标签',
            f'确认删除标签 #{tag_path}？\n这会从所有文件中移除该标签标记，内容本身不受影响。\n此操作无法撤销。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 匹配 #tag_path 及其所有子标签（如 #tag_path/子级）
        _pat = re.compile(
            r'\s*#' + re.escape(tag_path) + r'(?:/[\w\u4e00-\u9fff]+)*'
            r'(?=\s|$|[，。！？、；：\n\r])'
        )
        changed = 0
        for fp_str in self.store.get_txt_files():
            fp = Path(fp_str)
            try:
                text = fp.read_text('utf-8')
                new_text = _pat.sub('', text)
                if new_text != text:
                    fp.write_text(new_text, 'utf-8')
                    changed += 1
                    if fp_str == self._fp:
                        self._txt_editor.load_file(fp_str)
            except Exception:
                pass
        self._refresh_sidebar()
        self.statusBar().showMessage(
            f'已删除标签 #{tag_path}，影响 {changed} 个文件', 4000)

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
        # 定位到选区末尾正下方（贴近被选文字，更直观）
        end = max(cur.position(), cur.anchor())
        tmp = QTextCursor(self._txt_editor.document())
        tmp.setPosition(end)
        rect = self._txt_editor.cursorRect(tmp)
        gp   = self._txt_editor.mapToGlobal(rect.bottomLeft())
        sh   = self._annot_bar.sizeHint()
        x    = gp.x() - sh.width() // 2
        y    = gp.y() + 8
        scr  = QApplication.primaryScreen().geometry()
        x    = max(4, min(x, scr.width()  - sh.width()  - 4))
        # 如果下方空间不足，改到选区上方
        if y + sh.height() + 4 > scr.height():
            start = min(cur.position(), cur.anchor())
            tmp2  = QTextCursor(self._txt_editor.document())
            tmp2.setPosition(start)
            rect2 = self._txt_editor.cursorRect(tmp2)
            gp2   = self._txt_editor.mapToGlobal(rect2.topLeft())
            y     = gp2.y() - sh.height() - 8
        y = max(4, y)
        self._annot_bar.move(x, y)
        self._annot_bar.show()
        # 记录光标处已有的标注（供 ✕ 删除用）
        a = self._txt_editor.annot_at_cursor()
        self._pending_annot_id = a['id'] if a else None

    def _do_annotate(self, atype: str):
        self._annot_bar.hide()   # 无论结果如何立即隐藏
        annot = self._txt_editor.annotate(atype)
        if annot:
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
        self._annot_panel.refresh(self._fp)   # 统一在最后刷新
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
        from PyQt6.QtGui import QTextDocument as _QTD
        doc = self._txt_editor.document()

        flags = _QTD.FindFlag(0)
        if case_sensitive:
            flags |= _QTD.FindFlag.FindCaseSensitively

        fmt_all = QTextCharFormat()
        fmt_all.setBackground(QColor('#2a2400'))
        fmt_all.setForeground(QColor('#c8a850'))

        # 用 Qt 自带 find()，cursor 位置天然正确，无需手动转换
        self._search_matches = []   # 存 QTextCursor
        selections = []
        c = doc.find(kw, 0, flags)
        while not c.isNull():
            self._search_matches.append(QTextCursor(c))
            sel = QTextEdit.ExtraSelection()
            sel.cursor = QTextCursor(c)
            sel.format = fmt_all
            selections.append(sel)
            c = doc.find(kw, c, flags)

        self._txt_editor.setExtraSelections(selections)
        self._search_bar.set_matches(
            [m.selectionStart() for m in self._search_matches],
            doc.characterCount())
        if self._search_matches:
            self._jump_to_match(0)

    def _jump_to_match(self, idx: int):
        if not self._search_matches or not (0 <= idx < len(self._search_matches)):
            return
        doc = self._txt_editor.document()

        fmt_cur = QTextCharFormat()
        fmt_cur.setBackground(QColor('#3a2e00'))
        fmt_cur.setForeground(QColor('#f0d070'))
        fmt_cur.setFontWeight(QFont.Weight.Bold)

        fmt_all = QTextCharFormat()
        fmt_all.setBackground(QColor('#2a2400'))
        fmt_all.setForeground(QColor('#c8a850'))

        sels = []
        for i, mc in enumerate(self._search_matches):
            sel = QTextEdit.ExtraSelection()
            sel.cursor = QTextCursor(mc)
            sel.format = fmt_cur if i == idx else fmt_all
            sels.append(sel)
        self._txt_editor.setExtraSelections(sels)

        self._search_bar._cur_idx = idx
        self._search_bar._update_count()

        # 居中滚动到当前命中
        cur = QTextCursor(self._search_matches[idx])
        cur.setPosition(cur.selectionStart())
        self._txt_editor.setTextCursor(cur)
        self._txt_editor.ensureCursorVisible()
        rect = self._txt_editor.cursorRect(cur)
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

        # ── 键盘快捷标注：选中文字后按键直接标注，无需鼠标点工具条 ──
        # 仅在编辑器有选区且输入焦点不在搜索/备注栏时生效
        elif (self._fp and self._fp.endswith('.txt')
              and not self._search_bar._input.hasFocus()
              and not self._note_bar.isVisible()):
            cur = self._txt_editor.textCursor()
            if cur.hasSelection() and len(cur.selectedText().strip()) >= 5:
                _KEY_ANNOT = {
                    Qt.Key.Key_1: 'hl_yellow',
                    Qt.Key.Key_2: 'hl_green',
                    Qt.Key.Key_3: 'hl_pink',
                    Qt.Key.Key_4: 'hl_purple',
                    Qt.Key.Key_B: 'bold',
                    Qt.Key.Key_U: 'underline',
                }
                atype = _KEY_ANNOT.get(event.key())
                if atype:
                    self._annot_bar.hide()
                    annot = self._txt_editor.annotate(atype)
                    if annot:
                        self._annot_panel.refresh(self._fp)
                    return   # 不传递给 super，避免触发其他行为

        super().keyPressEvent(event)

    # ── 拖放文件 ──────────────────────────────────────────────
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            exts = {Path(u.toLocalFile()).suffix.lower() for u in urls}
            if exts & {'.txt', '.pdf', '.docx', '.srt'}:
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        from converter import convert_to_txt, SUPPORTED_EXTS
        any_success = False
        for url in event.mimeData().urls():
            fp  = url.toLocalFile()
            ext = Path(fp).suffix.lower()
            try:
                if ext in SUPPORTED_EXTS:
                    self.statusBar().showMessage(f'正在转换 {Path(fp).name} …', 0)
                    QApplication.processEvents()
                    fp = convert_to_txt(fp)
                if ext in {'.txt'} | SUPPORTED_EXTS:
                    self.store.add_txt(fp)
                    self._open_file(fp)
                    self.statusBar().showMessage(
                        f'已转换并打开：{Path(fp).name}', 3000)
                    any_success = True
            except Exception as e:
                self.statusBar().showMessage(f'转换失败：{e}', 5000)
        if any_success:
            self._refresh_sidebar()   # 只有成功时才刷新侧栏
        event.acceptProposedAction()

    def closeEvent(self, event):
        self._txt_editor.save()
        if self._fp:
            ed   = self._txt_editor
            cur  = ed.cursorForPosition(QPoint(2, 2))
            poff = ed.cursorRect(cur).top()
            self.store.set_read_pos(self._fp, char=cur.position(), poff=poff)
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
