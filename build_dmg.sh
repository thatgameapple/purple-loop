#!/bin/bash
set -e

echo "1. 构建 app..."
pyinstaller purple_loop.spec --noconfirm

echo "2. 深度签名..."
codesign --force --deep --sign - "dist/purple loop.app"

echo "3. 准备 staging..."
rm -rf /tmp/dmg_stage && mkdir /tmp/dmg_stage
cp -R "dist/purple loop.app" /tmp/dmg_stage/
codesign --force --deep --sign - "/tmp/dmg_stage/purple loop.app"

VERSION=$(python3 -c "import re; m=re.search(r'APP_VERSION\s*=\s*\"([^\"]+)\"', open('main_new.py').read()); print(m.group(1))")
DMG="purple_loop_${VERSION}_macos.dmg"

echo "4. 打包 DMG..."
rm -f "$DMG"
create-dmg \
  --volname "purple loop" \
  --window-pos 200 120 \
  --window-size 660 400 \
  --icon-size 100 \
  --icon "purple loop.app" 180 170 \
  --app-drop-link 480 170 \
  --no-internet-enable \
  "$DMG" \
  "/tmp/dmg_stage/purple loop.app"

echo "✓ 完成：$DMG"
