#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[maleoon] 跳过 evshim / sdl2 的 native 构建。
原因：上游仓库 app/src/main/cpp/sdl2 是空目录（SDL2 源码没进仓），
      CMakeLists.txt:47 add_subdirectory(sdl2) 必然 configure 失败。
      evshim 只是一个 phase-0 stub，Java 侧没有任何地方加载它，
      而且 cpp/jniLibs/arm64-v8a/libevshim.so 已经是预编译好的，
      所以直接把 EVSHIM 之后的所有 CMake 内容剪掉即可。
"""
import io
import sys

p = sys.argv[1] if len(sys.argv) > 1 else 'app/src/main/cpp/CMakeLists.txt'
lines = io.open(p, encoding='utf-8', errors='surrogateescape').read().splitlines(True)

idx = None
for i, l in enumerate(lines):
    if l.startswith('# ---- EVSHIM'):
        idx = i
        break

if idx is None:
    # 已经 patch 过
    if any('[maleoon] evshim/sdl2 skipped' in l for l in lines):
        print('already patched:', p)
        sys.exit(0)
    print('!! MISS: EVSHIM block not found in ' + p)
    sys.exit(1)

out = lines[:idx]
out.append('# [maleoon] evshim/sdl2 skipped: SDL2 sources are not in the repo and\n')
out.append('# libevshim.so already ships prebuilt in cpp/jniLibs/arm64-v8a/.\n')
io.open(p, 'w', encoding='utf-8', errors='surrogateescape').write(''.join(out))
print('patched %s: dropped %d lines after line %d' % (p, len(lines) - idx, idx))