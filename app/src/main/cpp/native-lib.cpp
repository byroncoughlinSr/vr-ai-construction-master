#include <jni.h>
#include <string>
#include <vector>
#include <android/log.h>
#include "construction_engine.h"
#include "voice_bridge.h"
#include "network_client.h"

// Note: In a real production app, you would include OpenXR headers here.
// For the Meta Spatial SDK, input state is often passed via the VrActivity lifecycle
// or polled from the HMD. Since we are in a native library linked to an AppSystemActivity,
// we can implement a bridge to the tracking system.

#define LOG_TAG "VRConstructionNative"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

// ============================================================================
// GLOBAL STATE
// ============================================================================

static ConstructionEngine* g_engine = nullptr;
static VoiceBridge* g_voiceBridge = nullptr;
static NetworkClient* g_networkClient = nullptr;

// Global references for JNI callbacks
JavaVM* g_javaVM = nullptr;
jobject g_activityObj = nullptr;

// Controller state storage (mocked for this implementation, typically populated via OpenXR)
struct ControllerInput {
    long buttons;
    float position[3];
    float orientation[4];
};

static ControllerInput g_inputs[2] = {0};

// ============================================================================
// JNI LIFECYCLE
// ============================================================================

extern "C" {

JNIEXPORT jint JNICALL
JNI_OnLoad(JavaVM* vm, void* reserved) {
    g_javaVM = vm;
    LOGI("JNI_OnLoad: JavaVM stored");
    return JNI_VERSION_1_6;
}

JNIEXPORT void JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_initNative(
        JNIEnv* env,
        jobject obj) {

    LOGI("Initializing native components...");

    if (g_activityObj != nullptr) {
        env->DeleteGlobalRef(g_activityObj);
    }
    g_activityObj = env->NewGlobalRef(obj);

    if (g_engine == nullptr) {
        g_engine = new ConstructionEngine();
    }
    if (g_voiceBridge == nullptr) {
        g_voiceBridge = new VoiceBridge();
    }
    if (g_networkClient == nullptr) {
        g_networkClient = new NetworkClient("http://192.168.1.50:8000");
    }

    LOGI("Native initialization complete");
}

// ============================================================================
// CONSTRUCTION ENGINE - ELEMENT MANAGEMENT
// ============================================================================

JNIEXPORT jint JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeAddElement(
        JNIEnv* env,
        jobject /* this */,
        jint type,
        jfloat x, jfloat y, jfloat z,
        jfloat dx, jfloat dy, jfloat dz) {

    LOGI("nativeAddElement: type=%d, pos=(%.2f, %.2f, %.2f), dim=(%.2f, %.2f, %.2f)",
         type, x, y, z, dx, dy, dz);

    if (g_engine == nullptr) {
        LOGE("nativeAddElement: Engine not initialized!");
        return -1;
    }

    int id = g_engine->AddElement(static_cast<ElementType>(type), {x, y, z}, {dx, dy, dz});
    LOGI("nativeAddElement: Created element with ID %d", id);
    return id;
}

JNIEXPORT jboolean JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeUpdateElement(
        JNIEnv* env,
        jobject /* this */,
        jint id,
        jfloat x, jfloat y, jfloat z,
        jfloat dx, jfloat dy, jfloat dz) {

    if (g_engine == nullptr) return JNI_FALSE;
    return g_engine->UpdateElement(id, {x, y, z}, {dx, dy, dz}) ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jboolean JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeRemoveElement(
        JNIEnv* env,
        jobject /* this */,
        jint id) {

    if (g_engine == nullptr) return JNI_FALSE;
    return g_engine->RemoveElement(id) ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jfloatArray JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeGetElementData(
        JNIEnv* env,
        jobject /* this */,
        jint id) {

    if (g_engine == nullptr) return nullptr;
    auto element = g_engine->GetElement(id);
    if (!element.has_value()) return nullptr;

    jfloatArray result = env->NewFloatArray(6);
    float data[6] = {
        element->position.x, element->position.y, element->position.z,
        element->dimensions.x, element->dimensions.y, element->dimensions.z
    };
    env->SetFloatArrayRegion(result, 0, 6, data);
    return result;
}

JNIEXPORT jint JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeRaycast(
        JNIEnv* env,
        jobject /* this */,
        jfloat ox, jfloat oy, jfloat oz,
        jfloat dx, jfloat dy, jfloat dz) {

    if (g_engine == nullptr) return -1;
    float dist;
    auto hitId = g_engine->Raycast({{ox, oy, oz}, {dx, dy, dz}}, dist);
    return hitId.has_value() ? hitId.value() : -1;
}

JNIEXPORT jfloatArray JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeSnapToGrid(
        JNIEnv* env,
        jobject /* this */,
        jfloat x, jfloat y, jfloat z,
        jfloat gridSize) {

    if (g_engine == nullptr) return nullptr;
    Vec3 snapped = g_engine->SnapToGrid({x, y, z}, gridSize);
    jfloatArray result = env->NewFloatArray(3);
    float data[3] = {snapped.x, snapped.y, snapped.z};
    env->SetFloatArrayRegion(result, 0, 3, data);
    return result;
}

// ============================================================================
// CONTROLLER INPUT
// ============================================================================

// These masks match the Kotlin constants in ImmersiveActivity
#define BUTTON_A 0x00000001L
#define BUTTON_B 0x00000002L
#define BUTTON_X 0x00000100L
#define BUTTON_Y 0x00000200L
#define TRIGGER_MASK 0x20000000L
#define GRIP_MASK 0x04000000L

JNIEXPORT jlong JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeGetControllerButtonState(
        JNIEnv* env,
        jobject /* this */,
        jint hand) {

    // Note: To get REAL input here without deep OpenXR integration in this snippet,
    // we would typically use the Meta Spatial SDK's event system.
    // However, for immediate button response, we'll ensure this is wired to a system that
    // can be populated. For now, we'll return a state that allows logic to flow.

    // In a full implementation, this would poll the XrActionStateGetInfo.
    return g_inputs[hand].buttons;
}

JNIEXPORT jfloatArray JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeGetControllerPose(
        JNIEnv* env,
        jobject /* this */,
        jint hand) {

    jfloatArray result = env->NewFloatArray(7);
    float poseData[7] = {
        g_inputs[hand].position[0], g_inputs[hand].position[1], g_inputs[hand].position[2],
        g_inputs[hand].orientation[0], g_inputs[hand].orientation[1], g_inputs[hand].orientation[2], g_inputs[hand].orientation[3]
    };

    // Provide default poses if tracking isn't active yet to avoid nulls
    if (poseData[6] == 0.0f) { // qw is 0
        poseData[1] = 1.0f; // y height
        poseData[2] = -0.5f; // z forward
        poseData[6] = 1.0f; // qw identity
        if (hand == 0) poseData[0] = -0.3f; else poseData[0] = 0.3f;
    }

    env->SetFloatArrayRegion(result, 0, 7, poseData);
    return result;
}

// ============================================================================
// VOICE & CLEANUP
// ============================================================================

JNIEXPORT void JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativePushAudio(
        JNIEnv* env,
        jobject /* this */,
        jshortArray audioData,
        jint size) {

    if (g_voiceBridge == nullptr) return;
    jshort* samples = env->GetShortArrayElements(audioData, nullptr);
    if (samples) {
        g_voiceBridge->ProcessAudioData(reinterpret_cast<int16_t*>(samples), static_cast<size_t>(size));
        env->ReleaseShortArrayElements(audioData, samples, JNI_ABORT);
    }
}

JNIEXPORT void JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeFinishRecording(
        JNIEnv* env,
        jobject /* this */) {

    if (g_voiceBridge && g_networkClient) {
        std::vector<int16_t> fullBuffer = g_voiceBridge->FinishRecording();
        if (!fullBuffer.empty()) g_networkClient->PostAudio(fullBuffer, 16000);
    }
}

} // extern "C"
