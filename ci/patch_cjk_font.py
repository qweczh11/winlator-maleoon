#!/usr/bin/env python3
"""把中文字体注入 container_pattern.tzst（新建容器时解压的 .wine 骨架）。

用法: python3 ci/patch_cjk_font.py src/app
做两件事:
  1. 把 wqy-microhei / Noto CJK 放进 .wine/drive_c/windows/Fonts/
  2. 在 system.reg 追加 [Software\\Wine\\Fonts\\Replacements]，把常见
     西文字体名映射到该中文字体，这样 Windows 程序里的中文不再是方框。
"""
import os
import shutil
import subprocess
import sys
import tempfile

APP = sys.argv[1] if len(sys.argv) > 1 else 'src/app'
PATTERN = os.path.join(APP, 'src/main/assets/container_pattern.tzst')

# (字体路径, 字体 family 名)
CANDIDATES = [
    ('/usr/share/fonts/truetype/wqy/wqy-microhei.ttc', 'WenQuanYi Micro Hei'),
    ('/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc', 'Noto Sans CJK SC'),
    ('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', 'Noto Sans CJK SC'),
]

font_src = target = None
for path, family in CANDIDATES:
    if os.path.isfile(path) and os.path.getsize(path) > 100000:
        font_src, target = path, family
        break

if not font_src:
    sys.exit('ERROR: no CJK font on runner (apt-get install fonts-wqy-microhei)')
if not os.path.isfile(PATTERN):
    sys.exit('ERROR: missing ' + PATTERN)

print('font  :', font_src)
print('family:', target)

tmp = tempfile.mkdtemp(prefix='cp_')
try:
    subprocess.run(
        'zstd -dc "%s" | tar -xf - -C "%s"' % (PATTERN, tmp),
        shell=True, check=True)
    print('extracted ->', tmp)

    fonts_dir = os.path.join(tmp, '.wine/drive_c/windows/Fonts')
    os.makedirs(fonts_dir, exist_ok=True)
    dst = os.path.join(fonts_dir, os.path.basename(font_src))
    shutil.copy2(font_src, dst)
    print('font ->', dst, os.path.getsize(dst), 'bytes')

    reg = os.path.join(tmp, '.wine/system.reg')
    if not os.path.isfile(reg):
        sys.exit('ERROR: system.reg missing in pattern')

    names = [
        'MS Shell Dlg', 'MS Shell Dlg2', 'MS Sans Serif', 'Microsoft Sans Serif',
        'Tahoma', 'Arial', 'Courier New', 'Times New Roman', 'Segoe UI',
        'SimSun', 'NSimSun', 'System', 'MingLiU', 'PMingLiU',
    ]
    marker = b'[Software\\\\Wine\\\\Fonts\\\\Replacements]'
    with open(reg, 'rb') as f:
        data = f.read()

    if marker in data:
        print('Replacements already present, skip')
    else:
        lines = [b'', marker + b' 1758570000']
        for name in names:
            lines.append(('"%s"="%s"' % (name, target)).encode('utf-8'))
        with open(reg, 'ab') as f:
            f.write(b'\n'.join(lines) + b'\n')
        print('system.reg patched, size', os.path.getsize(reg))

    out = PATTERN + '.new'
    subprocess.run(
        'tar -C "%s" -cf - .wine | zstd -19 -T0 -q -f -o "%s" -' % (tmp, out),
        shell=True, check=True)
    os.replace(out, PATTERN)
    print('recompressed pattern:', os.path.getsize(PATTERN), 'bytes')
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('cjk font injection done')