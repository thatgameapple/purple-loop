"""
purple loop 文本美化算法
========================
将导入的逐字稿/PDF/DOCX 转换后的原始文本整形为适合阅读的排版。

六阶段管道：
  Stage 1  字符归一化      — NFKC、零宽字符、BOM、换行符统一
  Stage 2  行级清理        — 去尾空格、清理孤立行（页码/序号/时间戳）
  Stage 3  段落重构        — 判断 \\n 是意外断行还是真实段落边界，智能合并
  Stage 4  标点归一化      — 省略号、破折号、中文句后半角→全角
  Stage 5  间距优化        — 汉字间空格消除、汉字↔拉丁/数字边界加空格
  Stage 6  口语词清理（可选）— 嗯/啊/呃 等语气填充词、重复词

每个阶段可独立调用；normalize() 是主入口。
"""

import re
import unicodedata


# ─────────────────────────────────────────────────────────────────────────────
# 辅助正则
# ─────────────────────────────────────────────────────────────────────────────

# 中文字符范围（CJK 统一表意文字主区）
_CJK = r'\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff'

# 句末标点（结束一句话、段落自然终止）
_SENT_END = re.compile(r'[。！？…」』）\]】〕〗〙〛》\'"]+\s*$')

# 孤立行：纯页码、纯序号、纯时间戳、纯短数字
_ISOLATED = re.compile(
    r'^\s*('
    r'\d+'                                       # 纯数字（页码/序号）
    r'|[\[\(（【]\d{1,3}:\d{2}(:\d{2})?[\]\)）】]'  # [00:00] 时间戳
    r'|\d{2}:\d{2}(:\d{2})?'                    # 00:00:00
    r'|第\s*[零一二三四五六七八九十百\d]+\s*[页面]'  # 第X页
    r')\s*$'
)

# 列表/标题行首标记（保留换行）
_LIST_START = re.compile(
    r'^('
    r'[•·\-\*]+'                                # 项目符号
    r'|[０-９\d]+[\.、。）\)]'                  # 1. 一、（一）
    r'|[（(][零一二三四五六七八九十\d]+[)）]'
    r'|第\s*[零一二三四五六七八九十百\d]+\s*[章节条款项]'
    r')'
)

# 段落缩进标记（真实段落开头）
_INDENT_START = re.compile(r'^[\u3000\t]|^ {2,}')

# 口语填充词（语气词 + 重复词）
_FILLER_SINGLE = re.compile(
    r'(?<![。！？，；：\u4e00-\u9fff])'  # 不在实义词后
    r'(嗯{1,}|啊{1,}|呃{1,}|哦{1,}|哎{1,}|额{1,}|唔{1,})\s*[，,]?\s*'
)
_FILLER_REPEAT = re.compile(
    r'([\u4e00-\u9fff]{1,4})\1+'  # 重复词：就是就是 → 就是
)
_FILLER_PHRASE = re.compile(
    r'(就是说|就是|那个那个|然后然后|然后那个|那个就是)\s*[，,]?\s*',
)

# 中文↔拉丁/数字边界（pangu 风格，插空格）
_CJK_BEFORE_LATIN = re.compile(r'([' + _CJK + r'])([A-Za-z0-9])')
_LATIN_BEFORE_CJK = re.compile(r'([A-Za-z0-9%°])([' + _CJK + r'])')


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: 字符归一化
# ─────────────────────────────────────────────────────────────────────────────

def _stage1_chars(text: str) -> str:
    # 统一换行
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # BOM、零宽字符、软连字符
    text = text.replace('\ufeff', '').replace('\u200b', '').replace('\u200c', '')
    text = text.replace('\u200d', '').replace('\u00ad', '').replace('\u00a0', ' ')
    # NFKC：全角 ASCII 数字/字母 → 半角（１２３ → 123，ＡＢＣ → ABC）
    text = unicodedata.normalize('NFKC', text)
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: 行级清理
# ─────────────────────────────────────────────────────────────────────────────

def _stage2_lines(text: str) -> str:
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        line = line.rstrip()           # 去尾空格/制表符
        if _ISOLATED.match(line):      # 孤立页码/序号/时间戳 → 丢弃
            continue
        cleaned.append(line)
    # 合并 3+ 连续空行 → 1 个空行
    text = '\n'.join(cleaned)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3: 段落重构（核心算法）
# ─────────────────────────────────────────────────────────────────────────────

_MIN_CONTENT_LEN = 8   # 短于此长度的行视为标题/标签，保留换行
_MAX_MERGE_LEN   = 200 # 合并后超过此长度不再继续合并

def _should_merge(above: str, below: str) -> bool:
    """判断 above 和 below 之间的 \\n 是否应合并（返回 True = 合并）"""
    if not above or not below:
        return False
    # 上行以句末标点结束 → 真实段落边界，保留
    if _SENT_END.search(above):
        return False
    # 下行以缩进或列表标记开头 → 真实段落开头，保留
    if _INDENT_START.match(below) or _LIST_START.match(below):
        return False
    # 任一行太短（标题/说话人标签等） → 保留
    if len(above.strip()) < _MIN_CONTENT_LEN or len(below.strip()) < _MIN_CONTENT_LEN:
        return False
    # 合并后过长 → 保留
    if len(above) + len(below) > _MAX_MERGE_LEN:
        return False
    return True


def _stage3_paragraphs(text: str) -> str:
    """
    处理逻辑：
    - 空行（连续两个 \\n 之间没有内容）= 真实段落边界，保留为 \\n\\n
    - 单个 \\n 根据上下文决定是否合并
    """
    # 先按空行（真实段落）拆成段落组
    raw_paras = re.split(r'\n\n+', text)
    result_paras = []

    for para in raw_paras:
        lines = para.split('\n')
        if len(lines) <= 1:
            result_paras.append(para)
            continue
        # 在段落内部，逐行判断是否合并
        merged = [lines[0]]
        for line in lines[1:]:
            if _should_merge(merged[-1], line):
                merged[-1] = merged[-1] + line
            else:
                merged.append(line)
        result_paras.append('\n'.join(merged))

    return '\n\n'.join(result_paras)


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4: 标点归一化
# ─────────────────────────────────────────────────────────────────────────────

def _stage4_punct(text: str) -> str:
    # 省略号统一为 ……（两个 U+2026）
    text = re.sub(r'\.{3,}|。{3,}|\u2026{1,2}', '……', text)
    # 破折号统一为 ——
    text = re.sub(r'(?<![—])[—\u2013\u2014]{1,2}(?![—])', '——', text)
    text = re.sub(r'-{2,}', '——', text)
    # 中文字符后紧跟半角句末标点 → 全角
    text = re.sub(r'([' + _CJK + r']),',  r'\1，', text)
    text = re.sub(r'([' + _CJK + r'])\.',  r'\1。', text)
    text = re.sub(r'([' + _CJK + r'])!',   r'\1！', text)
    text = re.sub(r'([' + _CJK + r'])\?',  r'\1？', text)
    text = re.sub(r'([' + _CJK + r']);',   r'\1；', text)
    text = re.sub(r'([' + _CJK + r']):',   r'\1：', text)
    # 重复标点折叠（三个以上 → 两个）
    text = re.sub(r'([！？。，；：])\1{2,}', r'\1\1', text)
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Stage 5: 间距优化
# ─────────────────────────────────────────────────────────────────────────────

def _stage5_spacing(text: str, pangu: bool = True) -> str:
    # 汉字之间的空格 → 删除（循环直到收敛，处理 "你 好 世 界" 这类多重空格）
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r'([' + _CJK + r'])\s+([' + _CJK + r'])', r'\1\2', text)
    # 多余空格折叠
    text = re.sub(r'[ \t]{2,}', ' ', text)
    if pangu:
        # 汉字 ↔ 拉丁/数字 之间加空格（pangu 风格）
        text = _CJK_BEFORE_LATIN.sub(r'\1 \2', text)
        text = _LATIN_BEFORE_CJK.sub(r'\1 \2', text)
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Stage 6: 口语词清理（可选）
# ─────────────────────────────────────────────────────────────────────────────

def _stage6_filler(text: str) -> str:
    text = _FILLER_PHRASE.sub('', text)
    text = _FILLER_SINGLE.sub('', text)
    # 重复词：就是就是 → 就是
    text = _FILLER_REPEAT.sub(r'\1', text)
    # 清理后可能残留多余逗号或空格
    text = re.sub(r'[，,]{2,}', '，', text)
    text = re.sub(r'([，。！？])\s+', r'\1', text)
    return text


# ─────────────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────────────

def normalize(
    text: str,
    *,
    reconstruct_paragraphs: bool = True,
    normalize_punct: bool = True,
    pangu_spacing: bool = False,
    clean_fillers: bool = False,
) -> str:
    """
    对原始导入文本执行美化管道。

    参数
    ----
    reconstruct_paragraphs : 是否启用段落重构（Stage 3）。
        对逐字稿导入建议开启；对已排版好的 txt 建议关闭。
    normalize_punct : 是否归一化标点（Stage 4）。
    pangu_spacing : 是否在汉字↔拉丁/数字边界插入空格（Stage 5 扩展）。
    clean_fillers : 是否清理口语填充词（Stage 6，破坏性，默认关闭）。
    """
    text = _stage1_chars(text)
    text = _stage2_lines(text)
    if reconstruct_paragraphs:
        text = _stage3_paragraphs(text)
    if normalize_punct:
        text = _stage4_punct(text)
    text = _stage5_spacing(text, pangu=pangu_spacing)
    if clean_fillers:
        text = _stage6_filler(text)
    # 最终首尾清理
    text = text.strip()
    return text
