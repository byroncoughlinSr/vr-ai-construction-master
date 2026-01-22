#include <jni.h>
#include <string>
#include <android/log.h>
#include "construction_engine.h"
#include "voice_bridge.h"
#include "network_client.h"

#define LOG_TAG "VRConstructionNative"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

static ConstructionEngine* g_engine = nullptr;
static VoiceBridge* g_voiceBridge = nullptr;
static NetworkClient* g_networkClient = nullptr;

// Global references for JNI callbacks
JavaVM* g_javaVM = nullptr;
jobject g_activityObj = nullptr;

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM* vm, void* reserved) {
    g_javaVM = vm;
    return JNI_VERSION_1_6;
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_stringFromJNI(
        JNIEnv* env,
        jobject /* this */) {
    std::string hello = "Hello from C++ Construction Engine";
    return env->NewStringUTF(hello.c_str());
}

extern "C" JNIEXPORT void JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_initNative(
        JNIEnv* env,
        jobject obj) {
    g_activityObj = env->NewGlobalRef(obj);

    if (g_engine == nullptr) {
        g_engine = new ConstructionEngine();
        LOGI("Native construction engine initialized");
    }
    if (g_voiceBridge == nullptr) {
        g_voiceBridge = new VoiceBridge();
        LOGI("Native voice bridge initialized");
    }
    if (g_networkClient == nullptr) {
        // Replace with your actual local IP or domain
        g_networkClient = new NetworkClient("http://192.168.1.50:8000");
        LOGI("Native network client initialized");
    }
}

// --- Construction Engine JNI ---

extern "C" JNIEXPORT jint JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeAddElement(
        JNIEnv* env,
        jobject /* this */,
        jint type,
        jfloat x, jfloat y, jfloat z,
        jfloat dx, jfloat dy, jfloat dz) {

    if (g_engine == nullptr) return -1;

    Vec3 pos = {x, y, z};
    Vec3 dim = {dx, dy, dz};

    int id = g_engine->AddElement(static_cast<ElementType>(type), pos, dim);
    LOGI("Added element id: %d, type: %d at (%.2f, %.2f, %.2f)", id, type, x, y, z);
    return id;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeUpdateElement(
        JNIEnv* env,
        jobject /* this */,
        jint id,
        jfloat x, jfloat y, jfloat z,
        jfloat dx, jfloat dy, jfloat dz) {

    if (g_engine == nullptr) return false;

    Vec3 pos = {x, y, z};
    Vec3 dim = {dx, dy, dz};

    return g_engine->UpdateElement(id, pos, dim);
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeRemoveElement(
        JNIEnv* env,
        jobject /* this */,
        jint id) {
    if (g_engine == nullptr) return false;
    return g_engine->RemoveElement(id);
}

extern "C" JNIEXPORT jint JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeGetElementCount(
        JNIEnv* env,
        jobject /* this */) {
    if (g_engine == nullptr) return 0;
    return static_cast<jint>(g_engine->GetElements().size());
}

extern "C" JNIEXPORT jint JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeRaycast(
        JNIEnv* env,
        jobject /* this */,
        jfloat ox, jfloat oy, jfloat oz,
        jfloat dx, jfloat dy, jfloat dz) {

    if (g_engine == nullptr) return -1;

    Ray ray = {{ox, oy, oz}, {dx, dy, dz}};
    float distance;
    auto hitId = g_engine->Raycast(ray, distance);

    return hitId.value_or(-1);
}

extern "C" JNIEXPORT jfloatArray JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeSnapToGrid(
        JNIEnv* env,
        jobject /* this */,
        jfloat x, jfloat y, jfloat z,
        jfloat gridSize) {

    if (g_engine == nullptr) return nullptr;

    Vec3 snapped = g_engine->SnapToGrid({x, y, z}, gridSize);
    jfloatArray result = env->NewFloatArray(3);
    float buf[3] = {snapped.x, snapped.y, snapped.z};
    env->SetFloatArrayRegion(result, 0, 3, buf);
    return result;
}

// --- Voice Bridge JNI ---

extern "C" JNIEXPORT void JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativePushAudio(
        JNIEnv* env,
        jobject /* this */,
        jshortArray audioData,
        jint size) {

    if (g_voiceBridge == nullptr) return;

    jshort* samples = env->GetShortArrayElements(audioData, nullptr);
    if (samples != nullptr) {
        g_voiceBridge->ProcessAudioData(reinterpret_cast<int16_t*>(samples), static_cast<size_t>(size));
        env->ReleaseShortArrayElements(audioData, samples, JNI_ABORT);
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeFinishRecording(
        JNIEnv* env,
        jobject /* this */) {

    if (g_voiceBridge == nullptr || g_networkClient == nullptr) return;

    std::vector<int16_t> fullBuffer = g_voiceBridge->FinishRecording();
    LOGI("Native finish recording called. Buffer size: %zu", fullBuffer.size());

    // Trigger asynchronous network upload
    g_networkClient->PostAudio(fullBuffer, 16000);
}

extern "C"
JNIEXPORT jfloatArray JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeGetElementData(JNIEnv *env,
                                                                                      jobject thiz,
                                                                                      jint id) {
    // TODO: implement nativeGetElementData()
}