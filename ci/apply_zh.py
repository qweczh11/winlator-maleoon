#!/usr/bin/env python3
"""把中文翻译打进 winlator-app 资源。
用法: python3 apply_zh.py <path-to-src/app>
数据: ci/zh_strings.json  {资源名: 中文}
做法: 直接覆盖 values/strings.xml 的默认值（这样不管系统语言是啥都显示中文），
      同时补一份 values-zh-rCN/strings.xml。
"""
import io
import json
import os
import re
import sys

APP = sys.argv[1] if len(sys.argv) > 1 else 'src/app'
RES = os.path.join(APP, 'src/main/res')
HERE = os.path.dirname(os.path.abspath(__file__))

with io.open(os.path.join(HERE, 'zh_strings.json'), 'r', encoding='utf-8') as f:
    TRANS = json.load(f)

# 只翻译这些数组里的可读项
ARRAY_REPL = {
    'binding_type_entries': [('Keyboard', '键盘'), ('Mouse', '鼠标'), ('Gamepad', '游戏手柄')],
    'dinput_mapper_type_entries': [('Standard', '标准')],
    'language_entries': [('English', '英语'), ('Português', '葡萄牙语'), ('Русский', '俄语')],
}

hit = set()


def patch_strings(path):
    with io.open(path, 'r', encoding='utf-8') as f:
        src = f.read()

    def repl(m):
        name = m.group(1)
        if name in TRANS:
            hit.add(name)
            return '<string name="%s"%s>%s</string>' % (name, m.group(2), TRANS[name])
        return m.group(0)

    out = re.sub(r'<string name="([^"]+)"([^>]*)>(.*?)</string>', repl, src, flags=re.S)
    with io.open(path, 'w', encoding='utf-8') as f:
        f.write(out)


def patch_arrays(path):
    if not os.path.exists(path):
        return
    with io.open(path, 'r', encoding='utf-8') as f:
        src = f.read()
    for arr, pairs in ARRAY_REPL.items():
        m = re.search(r'(<string-array name="%s">)(.*?)(</string-array>)' % arr, src, re.S)
        if not m:
            continue
        body = m.group(2)
        for en, cn in pairs:
            body = body.replace('<item>%s</item>' % en, '<item>%s</item>' % cn)
        src = src[:m.start(2)] + body + src[m.end(2):]
    with io.open(path, 'w', encoding='utf-8') as f:
        f.write(src)


def write_zh_r_cn():
    d = os.path.join(RES, 'values-zh-rCN')
    if not os.path.isdir(d):
        os.makedirs(d)
    path = os.path.join(d, 'strings.xml')
    existing = ''
    if os.path.exists(path):
        with io.open(path, 'r', encoding='utf-8') as f:
            existing = f.read()
    add = ''
    for k, v in TRANS.items():
        if ('name="%s"' % k) in existing:
            continue
        add += '  <string name="%s">%s</string>\n' % (k, v)
    if '</resources>' in existing:
        out = existing.replace('</resources>', add + '</resources>')
    else:
        out = "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<resources>\n" + add + '</resources>\n'
    with io.open(path, 'w', encoding='utf-8') as f:
        f.write(out)


patch_strings(os.path.join(RES, 'values/strings.xml'))
patch_arrays(os.path.join(RES, 'values/arrays.xml'))
write_zh_r_cn()

print('=== zh report ===')
print('translated strings:', len(hit), '/', len(TRANS))
missing = sorted(set(TRANS) - hit)
if missing:
    print('not found in source (可忽略, 上游已删):', len(missing), missing[:10])
print('done')