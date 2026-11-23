#!/usr/bin/env python3
"""Maleoon(华为马良)适配 + 日志直写 /sdcard/workfile
用法: python3 apply_maleoon.py <path-to-src/app>
"""
import io
import os
import re
import sys

APP = sys.argv[1] if len(sys.argv) > 1 else 'src/app'
R = os.path.join(APP, 'src/main/cpp/vortekrenderer')

INCLUDE = '''#include <android/log.h>
#include <stdio.h>
#include <stdarg.h>

static void MLOG_IMPL(const char* fmt, ...) {
    va_list ap1, ap2;
    va_start(ap1, fmt);
    va_copy(ap2, ap1);
    __android_log_vprint(ANDROID_LOG_INFO, "MaleoonVK", fmt, ap1);
    va_end(ap1);
    const char* paths[2] = {"/sdcard/workfile/winlator_vk.log",
                            "/data/data/com.winlator/files/maleoon_vk.log"};
    for (int i = 0; i < 2; i++) {
        FILE* f = fopen(paths[i], "a");
        if (!f) continue;
        vfprintf(f, fmt, ap2);
        fputc('\\n', f);
        fflush(f);
        fclose(f);
    }
    va_end(ap2);
}
#define MLOGE(...) MLOG_IMPL(__VA_ARGS__)
'''

report = []


def patch_file(path, fn):
    if not os.path.exists(path):
        report.append(('NOFILE', os.path.basename(path)))
        return False
    with io.open(path, 'r', encoding='utf-8') as f:
        src = f.read()
    new, n = fn(src)
    if n == 0:
        report.append(('MISS', os.path.basename(path)))
        return False
    with io.open(path, 'w', encoding='utf-8') as f:
        f.write(new)
    report.append(('OK', os.path.basename(path), n))
    return True


def add_log_header(src):
    if 'MaleoonVK' in src:
        return src, 1
    m = re.search(r'^#include[^\n]*\n', src, re.M)
    if not m:
        return src, 0
    i = m.end()
    return src[:i] + INCLUDE + src[i:], 1


def patch_vk_context_h(src):
    old = 'VkDriverId driverID;'
    if old not in src or 'vendorID' in src:
        return src, 0
    return src.replace(old, old + '\n    uint32_t vendorID;', 1), 1


def patch_vk_context(src):
    n = 0
    src, k = add_log_header(src)
    n += k
    old = 'VkContext* createVkContext(JNIEnv* env, jobject obj, int clientFd, jobject options) {'
    if old in src and 'createVkContext enter' not in src:
        src = src.replace(old, old + '\n    MLOGE("createVkContext enter");', 1)
        n += 1
    return src, n


def patch_vulkan_helper(src):
    n = 0
    src, k = add_log_header(src)
    n += k

    old = 'context->driverID = driverProperties.driverID;'
    if old in src and 'context->vendorID' not in src:
        add = old + '''
    context->vendorID = properties2.properties.vendorID;
    MLOGE("device=%s vendorID=0x%04X driverID=%d api=%u.%u.%u driverVersion=%u",
          properties2.properties.deviceName,
          properties2.properties.vendorID,
          (int)driverProperties.driverID,
          VK_VERSION_MAJOR(properties2.properties.apiVersion),
          VK_VERSION_MINOR(properties2.properties.apiVersion),
          VK_VERSION_PATCH(properties2.properties.apiVersion),
          properties2.properties.driverVersion);'''
        src = src.replace(old, add, 1)
        n += 1

    old = 'bool isAdrenoDevice = context->driverID == VK_DRIVER_ID_QUALCOMM_PROPRIETARY;'
    if old in src and 'isHuaweiDevice' not in src:
        src = src.replace(old, old + '\n        bool isHuaweiDevice = context->vendorID == 0x19E5u;', 1)
        n += 1

    old = 'if ((isMaliDevice || isXclipseDevice) && context->engineVersion'
    if old in src:
        src = src.replace(old, 'if ((isMaliDevice || isHuaweiDevice || isXclipseDevice) && context->engineVersion', 1)
        n += 1
    return src, n


def patch_shader_inspector(src):
    n = 0
    src, k = add_log_header(src)
    n += k

    old = 'bool isMaliDevice = context->driverID == VK_DRIVER_ID_ARM_PROPRIETARY;'
    if old in src and 'isMaliLikeDevice' not in src:
        src = src.replace(old, old + '''
    bool isHuaweiDevice = context->vendorID == 0x19E5u;
    bool isMaliLikeDevice = isMaliDevice || isHuaweiDevice;''', 1)
        n += 1

    old = 'shaderInspector->removeImageBoundCheck = isMaliDevice && isDXVKEngine;'
    if old in src:
        src = src.replace(old, '''MLOGE("ShaderInspector mali=%d huawei=%d dxvk=%d clipMissing=%d engineVer=0x%x",
          isMaliDevice, isHuaweiDevice, isDXVKEngine, shaderInspector->checkClipDistance, context->engineVersion);
    shaderInspector->removeImageBoundCheck = isMaliLikeDevice && isDXVKEngine;''', 1)
        n += 1
    return src, n


def patch_texture_decoder(src):
    n = 0
    src, k = add_log_header(src)
    n += k

    old = 'if (supportedFeatures->textureCompressionBC) return NULL;'
    if old in src:
        src = src.replace(old, 'MLOGE("textureCompressionBC=%d", supportedFeatures->textureCompressionBC);\n    ' + old, 1)
        n += 1

    old = 'if (context->driverID == VK_DRIVER_ID_SAMSUNG_PROPRIETARY) textureDecoder->deviceSupportedFormats'
    if old in src:
        src = src.replace(old, 'if (context->driverID == VK_DRIVER_ID_SAMSUNG_PROPRIETARY || context->vendorID == 0x19E5u) textureDecoder->deviceSupportedFormats', 1)
        n += 1
    return src, n


def patch_request_handler(src):
    n = 0
    src, k = add_log_header(src)
    n += k

    old = 'VkResult result = vulkanWrapper.vkCreateInstance(&createInfo, NULL, &instance);'
    if old in src and 'vkCreateInstance result' not in src:
        src = src.replace(old, old + '\n    MLOGE("vkCreateInstance result=%d", (int)result);', 1)
        n += 1

    old = 'VkResult result = vulkanWrapper.vkCreateDevice(physicalDevice, &createInfo, NULL, &device);'
    if old in src and 'vkCreateDevice result' not in src:
        src = src.replace(old, old + '''
    MLOGE("vkCreateDevice result=%d extCount=%u", (int)result, createInfo.enabledExtensionCount);
    if (result != VK_SUCCESS) {
        for (uint32_t i = 0; i < createInfo.enabledExtensionCount; i++)
            MLOGE("  ext[%u]=%s", i, createInfo.ppEnabledExtensionNames[i]);
    }''', 1)
        n += 1
    return src, n


ok = True
ok &= patch_file(os.path.join(R, 'include/vk_context.h'), patch_vk_context_h)
ok &= patch_file(os.path.join(R, 'src/vk_context.c'), patch_vk_context)
ok &= patch_file(os.path.join(R, 'src/vulkan_helper.c'), patch_vulkan_helper)
ok &= patch_file(os.path.join(R, 'src/shader_inspector.c'), patch_shader_inspector)
ok &= patch_file(os.path.join(R, 'src/texture_decoder.c'), patch_texture_decoder)
ok &= patch_file(os.path.join(R, 'src/request_handler.c'), patch_request_handler)

print('=== patch report ===')
for r in report:
    print(' ', r)
if not ok:
    print('!! 有文件没替换成功')
    sys.exit(1)
print('all patches applied')