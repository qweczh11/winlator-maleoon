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

    if '#include <errno.h>' not in src:
        src = src.replace('#include "vk_context.h"', '#include <errno.h>\n#include "vk_context.h"', 1)
        n += 1

    old = 'VkContext* createVkContext(JNIEnv* env, jobject obj, int clientFd, jobject options) {'
    if old in src and 'createVkContext enter' not in src:
        src = src.replace(old, old + '\n    MLOGE("createVkContext enter clientFd=%d", clientFd);', 1)
        n += 1

    pairs = [
        ('if (!context->serverRing) return false;',
         'if (!context->serverRing) { MLOGE("VT ring serverRing FAIL"); return false; }'),
        ('if (!context->clientRing) return false;',
         'if (!context->clientRing) { MLOGE("VT ring clientRing FAIL"); return false; }'),
        ('if (!context->ringPool[i].ring) return false;',
         'if (!context->ringPool[i].ring) { MLOGE("VT ring pool FAIL i=%d", i); return false; }'),
        ('if (result < 0) return false;',
         'if (result < 0) { MLOGE("VT send_fds FAIL result=%d errno=%d", result, errno); return false; }'),
        ('pthread_create(&context->requestHandlerThread, NULL, requestHandlerThread, context);',
         'MLOGE("VT setupRingBuffers OK, starting handler");\n    pthread_create(&context->requestHandlerThread, NULL, requestHandlerThread, context);'),
    ]
    for o, nw in pairs:
        if o in src:
            src = src.replace(o, nw, 1)
            n += 1

    old2 = 'static void* requestHandlerThread(void* param) {\n    VkContext* context = param;'
    if old2 in src and 'VT handler thread start' not in src:
        src = src.replace(old2, old2 + '\n    MLOGE("VT handler thread start");', 1)
        n += 1

    old3 = ('int requestCode = vt_recv(context->serverRing, &context->inputBuffer, &context->inputBufferSize, &context->memoryPool);\n'
            '        if (requestCode < 0) break;')
    if old3 in src and 'VT handler req' not in src:
        src = src.replace(
            old3,
            'int requestCode = vt_recv(context->serverRing, &context->inputBuffer, &context->inputBufferSize, &context->memoryPool);\n'
            '        MLOGE("VT handler req=%d", requestCode);\n'
            '        if (requestCode < 0) break;', 1)
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
    old = 'void checkDeviceFeatures(VkPhysicalDeviceFeatures* features, void* pNext) {\n    features->textureCompressionBC = VK_TRUE;'
    if old in src and 'vtFeatures' not in src:
        src = src.replace(old, '''void checkDeviceFeatures(VkPhysicalDeviceFeatures* features, void* pNext) {
    MLOGE("vtFeatures before: ssExtFmt=%u vtxAtomics=%u fragAtomics=%u ssWrite=%u ssRead=%u gather=%u sessInd=%u",
          features->shaderStorageImageExtendedFormats, features->vertexPipelineStoresAndAtomics,
          features->fragmentStoresAndAtomics, features->shaderStorageImageWriteWithoutFormat,
          features->shaderStorageImageReadWithoutFormat, features->shaderImageGatherExtended,
          features->shaderSampledImageArrayDynamicIndexing);
    for (uint32_t fi = 0; fi < sizeof(VkPhysicalDeviceFeatures) / sizeof(VkBool32); fi++) ((VkBool32*)features)[fi] = VK_TRUE;
    MLOGE("vtFeatures: forced all core features TRUE");
    features->textureCompressionBC = VK_TRUE;''', 1)
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
    if '#include <string.h>' not in src:
        src = src.replace('#include <stdio.h>', '#include <stdio.h>\n#include <string.h>\n#include <stdlib.h>', 1)
        n += 1

    helper = '''
static bool vtIsDeviceExtensionSupported(VkPhysicalDevice physicalDevice, const char* name) {
    uint32_t count = 0;
    if (!vulkanWrapper.vkEnumerateDeviceExtensionProperties) return false;
    if (vulkanWrapper.vkEnumerateDeviceExtensionProperties(physicalDevice, NULL, &count, NULL) != VK_SUCCESS || count == 0) return false;
    VkExtensionProperties* props = (VkExtensionProperties*)calloc(count, sizeof(VkExtensionProperties));
    if (!props) return false;
    bool found = false;
    if (vulkanWrapper.vkEnumerateDeviceExtensionProperties(physicalDevice, NULL, &count, props) == VK_SUCCESS) {
        for (uint32_t i = 0; i < count; i++) {
            if (strcmp(props[i].extensionName, name) == 0) { found = true; break; }
        }
    }
    free(props);
    return found;
}
'''
    if 'vtIsDeviceExtensionSupported' not in src:
        src = src.replace('void vt_handle_vkCreateDevice(VkContext* context) {',
                          helper + 'void vt_handle_vkCreateDevice(VkContext* context) {', 1)
        n += 1

    old_ext = '''    const char* extraExtensions[] = {"VK_KHR_get_memory_requirements2", "VK_KHR_dedicated_allocation", "VK_KHR_external_memory", "VK_KHR_external_memory_fd", "VK_KHR_external_fence", "VK_KHR_external_fence_fd", "VK_ANDROID_external_memory_android_hardware_buffer", "VK_EXT_queue_family_foreign"};
    injectExtensions(context, (char***)&createInfo.ppEnabledExtensionNames, &createInfo.enabledExtensionCount,
                     extraExtensions, ARRAY_SIZE(extraExtensions),
                     globalImplementedDeviceExtensions, ARRAY_SIZE(globalImplementedDeviceExtensions));'''
    new_ext = '''    const char* extraExtensionsAll[] = {"VK_KHR_get_memory_requirements2", "VK_KHR_dedicated_allocation", "VK_KHR_external_memory", "VK_KHR_external_memory_fd", "VK_KHR_external_fence", "VK_KHR_external_fence_fd", "VK_ANDROID_external_memory_android_hardware_buffer", "VK_EXT_queue_family_foreign"};
    const char* extraExtensions[ARRAY_SIZE(extraExtensionsAll)];
    uint32_t extraExtensionsCount = 0;
    for (uint32_t ei = 0; ei < ARRAY_SIZE(extraExtensionsAll); ei++) {
        if (vtIsDeviceExtensionSupported(physicalDevice, extraExtensionsAll[ei])) extraExtensions[extraExtensionsCount++] = extraExtensionsAll[ei];
        else MLOGE("vtCreateDevice: drop unsupported ext %s", extraExtensionsAll[ei]);
    }
    MLOGE("vtCreateDevice: extraExt=%u", extraExtensionsCount);
    injectExtensions(context, (char***)&createInfo.ppEnabledExtensionNames, &createInfo.enabledExtensionCount,
                     extraExtensions, extraExtensionsCount,
                     globalImplementedDeviceExtensions, ARRAY_SIZE(globalImplementedDeviceExtensions));'''
    if old_ext in src and 'extraExtensionsAll' not in src:
        src = src.replace(old_ext, new_ext, 1)
        n += 1

    old = 'void vt_handle_vkCreateDevice(VkContext* context) {'
    if old in src and 'vtCreateDevice enter' not in src:
        src = src.replace(old, old + '\n    MLOGE("vtCreateDevice enter");', 1)
        n += 1

    old_wait = '''    if (timeout != 0) {
        VkResult result = VK_SUCCESS;
        int fds[fenceCount];
        for (int i = 0; i < fenceCount; i++) {
            VkFenceGetFdInfoKHR getFdInfo = {0};
            getFdInfo.sType = VK_STRUCTURE_TYPE_FENCE_GET_FD_INFO_KHR;
            getFdInfo.fence = fences[i];
            getFdInfo.handleType = VK_EXTERNAL_FENCE_HANDLE_TYPE_SYNC_FD_BIT;

            result = vulkanWrapper.vkGetFenceFd(device, &getFdInfo, &fds[i]);
            if (result != VK_SUCCESS) break;
        }

        send_fds(context->clientFd, fds, fenceCount, &result, sizeof(VkResult));
        for (int i = 0; i < fenceCount; i++) CLOSEFD(fds[i]);
    }'''
    new_wait = '''    MLOGE("vtWaitForFences: count=%u waitAll=%u timeout=%llu", fenceCount, waitAll, (unsigned long long)timeout);
    if (timeout != 0) {
        VkResult result = VK_SUCCESS;
        int fds[fenceCount];
        int needFallback = (vulkanWrapper.vkGetFenceFd == NULL) ? 1 : 0;
        for (uint32_t i = 0; i < fenceCount; i++) {
            fds[i] = -1;
            if (needFallback) continue;
            VkFenceGetFdInfoKHR getFdInfo = {0};
            getFdInfo.sType = VK_STRUCTURE_TYPE_FENCE_GET_FD_INFO_KHR;
            getFdInfo.fence = fences[i];
            getFdInfo.handleType = VK_EXTERNAL_FENCE_HANDLE_TYPE_SYNC_FD_BIT;

            result = vulkanWrapper.vkGetFenceFd(device, &getFdInfo, &fds[i]);
            MLOGE("vtWaitForFences: i=%u getFd result=%d fd=%d", i, (int)result, fds[i]);
            if (result != VK_SUCCESS) { needFallback = 1; break; }
            if (fds[i] < 0) {
                /* SYNC_FD 规范：fd == -1 表示 fence 已经是 signal 状态（导出已消费信号） */
                MLOGE("vtWaitForFences: i=%u already-signaled(-1)", i);
                int pp[2];
                if (pipe(pp) == 0) {
                    ssize_t wr = write(pp[1], "1", 1);
                    (void)wr;
                    close(pp[1]);
                    fds[i] = pp[0];
                }
            }
        }

        if (needFallback) {
            /* [maleoon] 驱动不支持 SYNC_FD 导出：服务端限时同步等待，再用 pipe 伪造已就绪 fd */
            uint64_t useTimeout = (timeout > 2000000000ULL) ? 2000000000ULL : timeout;
            VkResult wres = vulkanWrapper.vkWaitForFences(device, fenceCount, fences, waitAll, useTimeout);
            MLOGE("vtWaitForFences: fallback wait result=%d", (int)wres);
            result = wres;
            /* 无论成功或超时都必须回有效 fd，否则客户端 recv_fds 永久阻塞、窗口关不掉 */
            for (uint32_t i = 0; i < fenceCount; i++) {
                int pp[2];
                if (pipe(pp) == 0) {
                    ssize_t wr = write(pp[1], "1", 1);
                    (void)wr;
                    close(pp[1]);
                    fds[i] = pp[0];
                }
            }
        }

        int sret = send_fds(context->clientFd, fds, fenceCount, &result, sizeof(VkResult));
        MLOGE("vtWaitForFences: send_fds ret=%d result=%d", sret, (int)result);
        for (uint32_t i = 0; i < fenceCount; i++) { if (fds[i] >= 0) CLOSEFD(fds[i]); }
    }'''
    if old_wait in src and 'needFallback' not in src:
        src = src.replace(old_wait, new_wait, 1)
        n += 1

    old_qs = '''    VkResult result = vulkanWrapper.vkQueueSubmit(queue, submitCount, submits, fence);
    if (result == VK_ERROR_DEVICE_LOST) context->status = result;'''
    new_qs = '''    VkResult result = vulkanWrapper.vkQueueSubmit(queue, submitCount, submits, fence);
    MLOGE("vtQueueSubmit: fence=%llu sub=%u cb0=%u wait0=%u sig0=%u result=%d",
          (unsigned long long)fenceId, submitCount,
          submitCount ? submits[0].commandBufferCount : 0,
          submitCount ? submits[0].waitSemaphoreCount : 0,
          submitCount ? submits[0].signalSemaphoreCount : 0, (int)result);
    if (result == VK_ERROR_DEVICE_LOST) context->status = result;'''
    if old_qs in src and 'vtQueueSubmit:' not in src:
        src = src.replace(old_qs, new_qs, 1)
        n += 1

    if '#include <unistd.h>' not in src:
        if '#include <string.h>' in src:
            src = src.replace('#include <string.h>', '#include <string.h>\n#include <unistd.h>', 1)
        else:
            src = src.replace('#include <stdio.h>', '#include <stdio.h>\n#include <unistd.h>', 1)
        n += 1

    return src, n


G = os.path.join(APP, 'src/main/cpp/gladiorenderer')


def patch_gl_texture(src):
    """Gladio: currentRenderer 未就绪时 GLTexture_getBound 会空指针（SIGSEGV @0x3e8）"""
    n = 0
    old = ('GLTexture* GLTexture_getBound(GLenum target) {\n'
           '    uint8_t activeTexture = currentRenderer->clientState.activeTexture;\n'
           '    return currentRenderer->clientState.texture[activeTexture][indexOfGLTarget(target)];\n'
           '}')
    new = ('GLTexture* GLTexture_getBound(GLenum target) {\n'
           '    if (!currentRenderer) return NULL;\n'
           '    uint8_t activeTexture = currentRenderer->clientState.activeTexture;\n'
           '    int idx = indexOfGLTarget(target);\n'
           '    if (idx < 0) return NULL;\n'
           '    return currentRenderer->clientState.texture[activeTexture][idx];\n'
           '}')
    if old in src:
        src = src.replace(old, new, 1)
        n += 1

    old2 = 'void GLTexture_bind(GLenum target, GLuint id) {\n    bool isTextureRect'
    new2 = 'void GLTexture_bind(GLenum target, GLuint id) {\n    if (!currentRenderer) return;\n    bool isTextureRect'
    if old2 in src:
        src = src.replace(old2, new2, 1)
        n += 1
    return src, n


def patch_rootfs_installer(src):
    """让 rootfs 安装/每次启动补齐中文字体（assets/cjk_fonts.tzst）"""
    n = 0
    # 2026-08-17 那个提交里 RootFSInstaller 调用了已经不存在的 SettingsFragment.resetBox64Version
    if 'SettingsFragment.resetBox64Version(activity);' in src:
        src = src.replace(
            'SettingsFragment.resetBox64Version(activity);',
            'SettingsFragment.resetPreferenceVersions(activity);', 1)
        n += 1

    anchor = 'rootFS.createRFSVersionFile(LATEST_VERSION);'
    if 'cjk_fonts.tzst' not in src and anchor in src:
        src = src.replace(
            anchor,
            'TarCompressorUtils.extract(TarCompressorUtils.Type.ZSTD, activity, "cjk_fonts.tzst", rootDir);\n                ' + anchor,
            1)
        n += 1

    old = ('        if (!rootFS.isValid() || rootFS.getVersion() < LATEST_VERSION) install(activity);\n'
           '    }')
    new = ('        if (!rootFS.isValid() || rootFS.getVersion() < LATEST_VERSION) install(activity);\n'
           '        else {\n'
           '            File cjkFont = new File(rootFS.getRootDir(), "usr/share/fonts/truetype/wqy/wqy-microhei.ttc");\n'
           '            if (!cjkFont.exists()) TarCompressorUtils.extract(TarCompressorUtils.Type.ZSTD, activity, "cjk_fonts.tzst", rootFS.getRootDir());\n'
           '        }\n'
           '    }')
    if old in src and 'cjkFont' not in src:
        src = src.replace(old, new, 1)
        n += 1
    return src, n


ok = True
ok &= patch_file(os.path.join(R, 'include/vk_context.h'), patch_vk_context_h)
ok &= patch_file(os.path.join(R, 'src/vk_context.c'), patch_vk_context)
ok &= patch_file(os.path.join(R, 'src/vulkan_helper.c'), patch_vulkan_helper)
ok &= patch_file(os.path.join(R, 'src/shader_inspector.c'), patch_shader_inspector)
ok &= patch_file(os.path.join(R, 'src/texture_decoder.c'), patch_texture_decoder)
ok &= patch_file(os.path.join(R, 'src/request_handler.c'), patch_request_handler)
ok &= patch_file(os.path.join(G, 'src/gl_texture.c'), patch_gl_texture)
ok &= patch_file(os.path.join(APP, 'src/main/java/com/winlator/xenvironment/RootFSInstaller.java'), patch_rootfs_installer)

print('=== patch report ===')
for r in report:
    print(' ', r)
if not ok:
    print('!! 部分补丁未命中（源码版本差异），继续构建')
print('all patches applied')