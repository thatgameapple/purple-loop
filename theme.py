"""
theme.py
全局色板 —— C 是可变 dict，主题切换时 in-place 更新，
所有模块只需 `from theme import C` 即可自动感知变化。
"""

DARK = {
    # ── 背景（iA Writer 深色基准：略带冷调的近黑）────────
    'bg':           '#1c1e1f',   # 主阅读区：iA Writer Dark 背景色
    'bg_sidebar':   '#161819',   # 侧栏略深
    'bg_input':     '#252729',   # 卡片/输入区
    'bg_sel_tag':   '#2a2d30',   # 标签选中
    'bg_sel_file':  '#252729',   # 文件选中
    # ── 文字（iA Writer Dark 文字系）─────────────────────
    'fg':           '#dfe3df',   # 主正文：柔和亮白
    'fg_tag':       '#a0a4a0',   # 侧栏标签
    'fg_file':      '#6e726e',   # 侧栏文件名：iA Writer 次级文字 #707070
    'fg_dim':       '#5a5e5a',   # 次要信息
    'fg_hint':      '#3e423e',   # 占位符
    'fg_dim2':      '#5a5e5a',   # 标注面板次要文字
    # ── 强调色 ────────────────────────────────────────────
    'accent':       '#5b9cf6',   # 主强调：蓝
    'accent_dim':   '#1a2e50',   # 标签 chip 背景
    # ── 边框 / 选区 ───────────────────────────────────────
    'border':       '#2a2d30',
    'select_bg':    '#1e3d6e',
    # ── 搜索高亮 ──────────────────────────────────────────
    'hl_all_bg':    '#3a2e00',
    'hl_all_fg':    '#e8c870',
    'hl_cur_bg':    '#1a3880',
    'hl_cur_fg':    '#ffffff',
    # ── 按钮 ──────────────────────────────────────────────
    'btn_close':    '#484848',
    'btn_hover':    '#909090',
    # ── 备注栏 ────────────────────────────────────────────
    'note_bar':     '#1e2022',
    'note_entry':   '#161819',
    'note_fg':      '#5b9cf6',
    'note_fg_dim':  '#7aabf8',
    'hover_card':   '#2a2d30',
    # ── 保存按钮（Flomo 绿）──────────────────────────────
    'save_btn_bg':  '#1db070',
    'save_btn_hov': '#25c97e',
    'save_btn_fg':  '#ffffff',
}

LIGHT = {
    # ── 背景（纸白系，柔和不刺眼）─────────────────────────
    'bg':           '#faf9f7',   # 主阅读区：暖白纸色
    'bg_sidebar':   '#f0ede8',   # 侧栏：浅暖灰，与阅读区区分
    'bg_input':     '#ffffff',   # 卡片/输入：纯白
    'bg_sel_tag':   '#e3dff7',   # 标签选中
    'bg_sel_file':  '#ece9f8',   # 文件选中
    # ── 文字 ──────────────────────────────────────────────
    'fg':           '#111111',   # 主正文：近黑，清晰易读
    'fg_tag':       '#2e2e4a',   # 侧栏标签
    'fg_file':      '#5c5c88',   # 侧栏文件名
    'fg_dim':       '#b8b4cc',   # 字数等次要信息
    'fg_hint':      '#9894b0',   # 提示占位符
    'fg_dim2':      '#9a97b0',   # 标注面板次要文字
    # ── 强调色（偏靛蓝紫，与深色版协调）─────────────────
    'accent':       '#5a4fd4',   # 主强调
    'accent_dim':   '#dddaf8',   # 浅强调背景
    # ── 边框 / 选区 ───────────────────────────────────────
    'border':       '#e2dede',   # 分割线：极浅暖灰
    'select_bg':    '#c8c3f0',   # 文字选区
    # ── 搜索高亮 ──────────────────────────────────────────
    'hl_all_bg':    '#fff5b0',   # 全匹配：浅黄
    'hl_all_fg':    '#4a3600',
    'hl_cur_bg':    '#3d5cc8',   # 当前匹配：蓝
    'hl_cur_fg':    '#ffffff',
    # ── 按钮 ──────────────────────────────────────────────
    'btn_close':    '#b8b4cc',   # 关闭按钮默认
    'btn_hover':    '#6660a0',   # 悬停
    # ── 备注栏 ────────────────────────────────────────────
    'note_bar':     '#f4f2f0',   # 备注栏背景：微暖白
    'note_entry':   '#ffffff',
    'note_fg':      '#6060b0',
    'note_fg_dim':  '#8888b0',
    'hover_card':   '#eeecf8',   # 卡片 hover
    # ── 保存按钮 ──────────────────────────────────────────
    'save_btn_bg':  '#5a4fd4',
    'save_btn_hov': '#6b61e0',
    'save_btn_fg':  '#ffffff',
}

THEMES = {'dark': DARK, 'light': LIGHT}

# 可变全局色板 —— 所有模块 `from theme import C` 获取同一引用
C: dict = dict(DARK)

# ── 标注高亮样式（随主题切换） ──────────────────────────────────
ANNOT_STYLES_DARK = {
    'hl_yellow': {'label': '黄色',   'bg': '#4a3800', 'fg': '',        'dot': '#c8a030'},
    'hl_green':  {'label': '绿色',   'bg': '#0e3020', 'fg': '',        'dot': '#3a9c5a'},
    'hl_pink':   {'label': '粉色',   'bg': '#361020', 'fg': '',        'dot': '#c05878'},
    'hl_purple': {'label': '紫色',   'bg': '#1e1448', 'fg': '',        'dot': '#7060cc'},
    'bold':      {'label': '加粗',   'bg': '',        'fg': '',        'dot': '#c8ccc8'},
    'underline': {'label': '下划线', 'bg': '',        'fg': '#5b9cf6', 'dot': '#5b9cf6'},
}

ANNOT_STYLES_LIGHT = {
    'hl_yellow': {'label': '黄色',   'bg': '#e8a000', 'fg': '#ffffff', 'dot': '#e8a000'},
    'hl_green':  {'label': '绿色',   'bg': '#2a8a2a', 'fg': '#ffffff', 'dot': '#2a8a2a'},
    'hl_pink':   {'label': '粉色',   'bg': '#cc4477', 'fg': '#ffffff', 'dot': '#cc4477'},
    'hl_purple': {'label': '紫色',   'bg': '#7040cc', 'fg': '#ffffff', 'dot': '#7040cc'},
    'bold':      {'label': '加粗',   'bg': '',        'fg': '',        'dot': '#1a1a2e'},
    'underline': {'label': '下划线', 'bg': '',        'fg': '#5a4fd4', 'dot': '#5a4fd4'},
}

ANNOT_THEMES = {'dark': ANNOT_STYLES_DARK, 'light': ANNOT_STYLES_LIGHT}


def apply(name: str):
    """将 C 切换到指定主题（in-place 更新，所有模块自动感知）"""
    C.update(THEMES[name])
