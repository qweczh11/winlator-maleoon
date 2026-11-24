#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[maleoon] Cmod 日志落盘补丁
把 ProcessHelper 里所有子进程的 stdout/stderr 从 /dev/null 改成追加写入：
  /data/data/com.winlator.cmod/files/wine_debug.log          (私有目录, run-as 可读)
  /sdcard/Android/data/com.winlator.cmod/files/wine_debug.log (外部目录, 文件管理器可直接看)
单文件超过 32MB 自动清空，避免无限增长。
"""
import io
import sys

p = sys.argv[1] if len(sys.argv) > 1 else 'app/src/main/java/com/winlator/cmod/core/ProcessHelper.java'
s = io.open(p, encoding='utf-8', errors='surrogateescape').read()
orig_len = len(s)


def rep(old, new, tag):
    global s
    if old not in s:
        print('!! MISS: ' + tag)
        sys.exit(1)
    s = s.replace(old, new, 1)
    print('ok: ' + tag)


# 1) 补 import
rep('import java.io.FileInputStream;',
    'import java.io.FileInputStream;\nimport java.io.FileOutputStream;',
    'import FileOutputStream')

# 2) 加日志字段 + 方法
rep('    private static final ArrayList<Callback<String>> debugCallbacks = new ArrayList<>();',
    '''    private static final ArrayList<Callback<String>> debugCallbacks = new ArrayList<>();
    // ===== [maleoon][log] 日志落盘 =====
    private static final File LOG_FILE = new File("/data/data/com.winlator.cmod/files/wine_debug.log");
    private static final File LOG_FILE_EXT = new File("/sdcard/Android/data/com.winlator.cmod/files/wine_debug.log");
    private static final long LOG_MAX_BYTES = 32L * 1024 * 1024;
    private static final Object LOG_LOCK = new Object();

    public static void logLine(String line) {
        if (line == null) return;
        synchronized (LOG_LOCK) {
            writeLog(LOG_FILE, line);
            writeLog(LOG_FILE_EXT, line);
        }
    }

    private static void writeLog(File file, String line) {
        try {
            File parent = file.getParentFile();
            if (parent != null && !parent.exists()) parent.mkdirs();
            if (file.length() > LOG_MAX_BYTES) file.delete();
            FileOutputStream fos = new FileOutputStream(file, true);
            try {
                fos.write((line + "\\n").getBytes("UTF-8"));
                fos.flush();
            } finally {
                fos.close();
            }
        } catch (Throwable ignored) {}
    }
    // ===== [/maleoon][log] =====''',
    'log fields + methods')

# 3) exec 开头记录命令与环境
rep('        Log.d("ProcessHelper", "env: " + Arrays.toString(envp) + "\\ncmd: " + command);',
    '''        Log.d("ProcessHelper", "env: " + Arrays.toString(envp) + "\\ncmd: " + command);
        logLine("=== CMD: " + command);
        logLine("=== ENV: " + Arrays.toString(envp));
        logLine("=== WD: " + workingDir);''',
    'exec head')

# 4) /dev/null -> 日志文件（合并 stdout+stderr，O_APPEND 多进程安全）
rep('''            if (debugCallbacks.isEmpty()) {
                File null_file = new File("/dev/null");
                pb.redirectError(null_file);
                pb.redirectOutput(null_file);
            }''',
    '''            if (debugCallbacks.isEmpty()) {
                // [maleoon][log] 不丢到 /dev/null，stdout+stderr 合并追加到日志
                pb.redirectErrorStream(true);
                pb.redirectOutput(ProcessBuilder.Redirect.appendTo(LOG_FILE));
            }''',
    'redirect to log')

# 5) 调试线程读到的每一行也落盘
rep('                    if (PRINT_DEBUG) System.out.println(line);',
    '''                    if (PRINT_DEBUG) System.out.println(line);
                    logLine(line);''',
    'debug thread line')

io.open(p, 'w', encoding='utf-8', errors='surrogateescape').write(s)
print('patched %s (%d -> %d bytes)' % (p, orig_len, len(s)))
