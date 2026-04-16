"""
purple loop app icon — 高级感版
深色渐变背景 + PL 字母微发光
"""
import os, shutil, subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter

SIZE   = 1024
RADIUS = 190

# ── 颜色 ─────────────────────────────────────────────────────
BG_TOP    = (28,  22,  42)   # 顶部：深紫
BG_BOTTOM = (14,  11,  20)   # 底部：更深
TEXT_COL  = (180, 148, 240)  # 淡紫字 #b494f0

# ── 渐变背景 ─────────────────────────────────────────────────
def make_gradient(size, top, bottom):
    grad = Image.new('RGBA', (size, size))
    pixels = grad.load()
    for y in range(size):
        t = y / (size - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(size):
            pixels[x, y] = (r, g, b, 255)
    return grad

grad = make_gradient(SIZE, BG_TOP, BG_BOTTOM)

# ── 圆角遮罩 ─────────────────────────────────────────────────
mask = Image.new('L', (SIZE, SIZE), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, SIZE, SIZE], radius=RADIUS, fill=255)

bg = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
bg.paste(grad, mask=mask)


# ── 字体 ────────────────────────────────────────────────────
light_fonts = [
    '/System/Library/Fonts/HelveticaNeue.ttc',
    '/System/Library/Fonts/Helvetica.ttc',
    '/Library/Fonts/Arial.ttf',
]

def load_font(size):
    for path in light_fonts:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()

font_P = load_font(540)
font_L = load_font(360)

# ── 发光层（模糊文字）────────────────────────────────────────
def draw_text_layer(alpha=255):
    layer = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    pb = font_P.getbbox('P')
    pw, ph = pb[2]-pb[0], pb[3]-pb[1]
    lb = font_L.getbbox('L')
    lw, lh = lb[2]-lb[0], lb[3]-lb[1]

    total_w = pw + lw - 30
    px = (SIZE - total_w) // 2 - pb[0]
    py = (SIZE - ph) // 2 - pb[1] - 30
    lx = px + pb[0] + pw - 30 - lb[0]
    ly = py + pb[1] + ph - lh - lb[1]

    col = (*TEXT_COL, alpha)
    d.text((px, py), 'P', font=font_P, fill=col)
    d.text((lx, ly), 'L', font=font_L, fill=col)
    return layer, (px, py, lx, ly)

# 光晕层（低透明度 + 模糊）
glow_layer, _ = draw_text_layer(alpha=140)
glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=18))
bg = Image.alpha_composite(bg, glow_layer)

# 主文字层（清晰）
main_layer, _ = draw_text_layer(alpha=255)
bg = Image.alpha_composite(bg, main_layer)

# ── 微弱外框（深色描边提升精致感）──────────────────────────
frame = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
ImageDraw.Draw(frame).rounded_rectangle(
    [1, 1, SIZE-1, SIZE-1], radius=RADIUS,
    outline=(255, 255, 255, 18), width=2)
bg = Image.alpha_composite(bg, frame)

# ── 保存 ────────────────────────────────────────────────────
bg.save('logo.png')
print('logo.png saved')

iconset = 'AppIcon.iconset'
os.makedirs(iconset, exist_ok=True)
pairs = [
    (16,   'icon_16x16.png'),
    (32,   'icon_16x16@2x.png'),
    (32,   'icon_32x32.png'),
    (64,   'icon_32x32@2x.png'),
    (128,  'icon_128x128.png'),
    (256,  'icon_128x128@2x.png'),
    (256,  'icon_256x256.png'),
    (512,  'icon_256x256@2x.png'),
    (512,  'icon_512x512.png'),
    (1024, 'icon_512x512@2x.png'),
]
for size, name in pairs:
    bg.resize((size, size), Image.LANCZOS).save(os.path.join(iconset, name))

r = subprocess.run(['iconutil', '-c', 'icns', iconset, '-o', 'AppIcon.icns'], capture_output=True)
print('AppIcon.icns saved' if r.returncode == 0 else r.stderr.decode())
shutil.rmtree(iconset)
