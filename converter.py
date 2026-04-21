"""
格式转换模块：SRT → TXT（阅读排版模式）
拖入 SRT 文件时自动调用，转换结果保存为同目录下的 .txt 文件。
"""
import re
from pathlib import Path


_SRT_BLOCK_RE = re.compile(
    r'^\d+\s*\n'
    r'(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\s*\n'
    r'([\s\S]*?)(?=\n\d+\s*\n|\Z)',
    re.MULTILINE
)

_READING_PUNCT_RE = re.compile(
    r'[^一-鿿㐀-䶿豈-﫿A-Za-z0-9\s]'
)

def _srt_ms(t: str) -> int:
    h, m, rest = t.split(':')
    s, ms = rest.split(',')
    return int(h) * 3_600_000 + int(m) * 60_000 + int(s) * 1_000 + int(ms)


def srt_to_txt(srt_path: str) -> str:
    """
    解析 SRT 字幕文件，按时间间隔分段、去除所有标点，返回阅读排版文本。
    自动处理 UTF-8 / UTF-8-BOM / GBK 编码。
    """
    content = None
    for enc in ('utf-8-sig', 'utf-8', 'gbk', 'latin-1'):
        try:
            content = Path(srt_path).read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if content is None:
        raise ValueError("无法识别 SRT 文件编码")

    content = content.replace('\r\n', '\n').strip()

    blocks = []
    for m in _SRT_BLOCK_RE.finditer(content + '\n\n'):
        start_ms = _srt_ms(m.group(1))
        end_ms   = _srt_ms(m.group(2))
        text = m.group(3).strip().replace('\n', ' ')
        if text:
            blocks.append((start_ms, end_ms, text))

    if not blocks:
        return ''

    GAP_THRESHOLD_MS = 1500
    groups: list[list[str]] = []
    current: list[str] = [blocks[0][2]]
    prev_end = blocks[0][1]

    for start_ms, end_ms, text in blocks[1:]:
        if start_ms - prev_end > GAP_THRESHOLD_MS:
            groups.append(current)
            current = []
        current.append(text)
        prev_end = end_ms
    groups.append(current)

    result: list[str] = []
    for group in groups:
        para = ' '.join(group)
        para = _READING_PUNCT_RE.sub(' ', para)
        para = re.sub(r'[ \t]{2,}', ' ', para).strip()
        if para:
            result.append(para)

    return '\n\n'.join(result)


def apply_reading_format(text: str) -> str:
    """
    对任意文本应用阅读排版：去除所有标点替换为空格，保留段落空行。
    用于 TXT 导入后的显示层处理，不修改磁盘文件。
    """
    paras = re.split(r'\n{2,}', text)
    result = []
    for para in paras:
        para = para.replace('\n', ' ')
        para = _READING_PUNCT_RE.sub(' ', para)
        para = re.sub(r'[ \t]{2,}', ' ', para).strip()
        if para:
            result.append(para)
    return '\n\n'.join(result)


SUPPORTED_EXTS = {'.srt'}

def convert_to_txt(src_path: str) -> str:
    """将 SRT 转换并保存为同目录下的 .txt 文件，返回生成路径。"""
    src = Path(src_path)
    if src.suffix.lower() != '.srt':
        raise ValueError(f"不支持的格式：{src.suffix}，仅支持 .srt")
    text = srt_to_txt(src_path)
    dst = src.with_suffix('.txt')
    dst.write_text(text, encoding='utf-8')
    return str(dst)
