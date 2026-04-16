#!/bin/bash
set -e

echo "1. 构建 app..."
pyinstaller purple_loop.spec --noconfirm

echo "2. 深度签名..."
codesign --force --deep --sign - "dist/purple loop.app"

echo "3. 打包 DMG..."
rm -rf /tmp/purple_loop_dmg
mkdir /tmp/purple_loop_dmg
ditto "dist/purple loop.app" "/tmp/purple_loop_dmg/purple loop.app"
ln -s /Applications /tmp/purple_loop_dmg/Applications
codesign --force --deep --sign - "/tmp/purple_loop_dmg/purple loop.app"

VERSION=$(date +%Y%m%d)
DMG="purple_loop_${VERSION}.dmg"
hdiutil create -volname "purple loop" -srcfolder /tmp/purple_loop_dmg \
  -ov -format UDZO "$DMG"

echo "✓ 完成：$DMG"
