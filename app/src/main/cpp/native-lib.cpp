#include <jni.h>
#include <string>
#include <android/log.h>
#include "construction_engine.h"
#include "voice_bridge.h"
#include "network_client.h"

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

// ============================================================================
// JNI LIFECYCLE
// ============================================================================

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM* vm, void* reserved) {
    g_javaVM = vm;
    LOGI("JNI_OnLoad: JavaVM stored");
    return JNI_VERSION_1_6;
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_stringFromJNI(
        JNIEnv* env,
        jobject /* this */) {
    std::string hello = "VR Construction Engine v1.0 - Ready";
    return env->NewStringUTF(hello.c_str());
}

extern "C" JNIEXPORT void JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_initNative(
        JNIEnv* env,
        jobject obj) {

    LOGI("Initializing native components...");

    // Store global reference to activity
    if (g_activityObj != nullptr) {
        env->DeleteGlobalRef(g_activityObj);
    }
    g_activityObj = env->NewGlobalRef(obj);

    // Initialize construction engine
    if (g_engine == nullptr) {
        g_engine = new ConstructionEngine();
        LOGI("✓ Construction engine initialized");
    }

    // Initialize voice bridge
    if (g_voiceBridge == nullptr) {
        g_voiceBridge = new VoiceBridge();
        LOGI("✓ Voice bridge initialized");
    }

    // Initialize network client
    if (g_networkClient == nullptr) {
        g_networkClient = new NetworkClient("http://192.168.1.50:8000");
        LOGI("✓ Network client initialized");
    }

    LOGI("Native initialization complete");
}

// ============================================================================
// CONSTRUCTION ENGINE - ELEMENT MANAGEMENT
// ============================================================================

extern "C" JNIEXPORT jint JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeAddElement(
        JNIEnv* env,
        jobject /* this */,
        jint type,
        jfloat x, jfloat y, jfloat z,
        jfloat dx, jfloat dy, jfloat dz) {

    if (g_engine == nullptr) {
        LOGE("nativeAddElement: Engine not initialized");
        return -1;
    }

    Vec3 pos = {x, y, z};
    Vec3 dim = {dx, dy, dz};

    int id = g_engine->AddElement(static_cast<ElementType>(type), pos, dim);
    LOGI("Added element: id=%d, type=%d, pos=(%.2f,%.2f,%.2f), dim=(%.2f,%.2f,%.2f)",
         id, type, x, y, z, dx, dy, dz);

    return id;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeUpdateElement(
        JNIEnv* env,
        jobject /* this */,
        jint id,
        jfloat x, jfloat y, jfloat z,
        jfloat dx, jfloat dy, jfloat dz) {

    if (g_engine == nullptr) {
        LOGE("nativeUpdateElement: Engine not initialized");
        return JNI_FALSE;
    }

    Vec3 pos = {x, y, z};
    Vec3 dim = {dx, dy, dz};

    bool success = g_engine->UpdateElement(id, pos, dim);

    if (success) {
        LOGI("Updated element: id=%d, pos=(%.2f,%.2f,%.2f)", id, x, y, z);
    } else {
        LOGE("Failed to update element: id=%d", id);
    }

    return success ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeRemoveElement(
        JNIEnv* env,
        jobject /* this */,
        jint id) {

    if (g_engine == nullptr) {
        LOGE("nativeRemoveElement: Engine not initialized");
        return JNI_FALSE;
    }

    bool success = g_engine->RemoveElement(id);

    if (success) {
        LOGI("Removed element: id=%d", id);
    } else {
        LOGE("Failed to remove element: id=%d", id);
    }

    return success ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jfloatArray JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeGetElementData(
        JNIEnv* env,
        jobject /* this */,
        jint id) {

    if (g_engine == nullptr) {
        LOGE("nativeGetElementData: Engine not initialized");
        return nullptr;
    }

    auto element = g_engine->GetElement(id);
    if (!element.has_value()) {
        LOGE("Element not found: id=%d", id);
        return nullptr;
    }

    // Return array: [x, y, z, dx, dy, dz]
    jfloatArray result = env->NewFloatArray(6);
    if (result == nullptr) {
        LOGE("Failed to allocate float array");
        return nullptr;
    }

    float data[6] = {
            element->position.x,
            element->position.y,
            element->position.z,
            element->dimensions.x,
            element->dimensions.y,
            element->dimensions.z
    };

    env->SetFloatArrayRegion(result, 0, 6, data);
    return result;
}

extern "C" JNIEXPORT jint JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeGetElementCount(
        JNIEnv* env,
        jobject /* this */) {

    if (g_engine == nullptr) {
        return 0;
    }

    return static_cast<jint>(g_engine->GetElements().size());
}

// ============================================================================
// CONSTRUCTION ENGINE - RAYCASTING
// ============================================================================

extern "C" JNIEXPORT jint JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeRaycast(
        JNIEnv* env,
        jobject /* this */,
        jfloat ox, jfloat oy, jfloat oz,
        jfloat dx, jfloat dy, jfloat dz) {

    if (g_engine == nullptr) {
        return -1;
    }

    Ray ray = {{ox, oy, oz}, {dx, dy, dz}};
    float distance;
    auto hitId = g_engine->Raycast(ray, distance);

    if (hitId.has_value()) {
        LOGI("Raycast hit: id=%d, distance=%.2f", hitId.value(), distance);
        return hitId.value();
    }

    return -1;
}

// ============================================================================
// CONSTRUCTION ENGINE - GRID SNAPPING
// ============================================================================

extern "C" JNIEXPORT jfloatArray JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeSnapToGrid(
        JNIEnv* env,
        jobject /* this */,
        jfloat x, jfloat y, jfloat z,
        jfloat gridSize) {

    if (g_engine == nullptr) {
        return nullptr;
    }

    Vec3 snapped = g_engine->SnapToGrid({x, y, z}, gridSize);

    jfloatArray result = env->NewFloatArray(3);
    if (result == nullptr) {
        LOGE("Failed to allocate float array for grid snap");
        return nullptr;
    }

    float data[3] = {snapped.x, snapped.y, snapped.z};
    env->SetFloatArrayRegion(result, 0, 3, data);

    return result;
}

// ============================================================================
// CONTROLLER INPUT - BUTTON STATE
// ============================================================================

extern "C" JNIEXPORT jlong JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeGetControllerButtonState(
        JNIEnv* env,
        jobject /* this */,
        jint hand) {

    // TODO: Integrate with Meta XR SDK for real controller input
    // For now, return 0 (no buttons pressed)
    // This allows the app to compile and run

    // When VR tracking is ready, this will return actual button states:
    // - BUTTON_A, BUTTON_B, BUTTON_X, BUTTON_Y
    // - TRIGGER_MASK, GRIP_MASK

    return 0L;
}

// ============================================================================
// CONTROLLER INPUT - POSE TRACKING
// ============================================================================

extern "C" JNIEXPORT jfloatArray JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeGetControllerPose(
        JNIEnv* env,
        jobject /* this */,
        jint hand) {

    // Create float array for pose data: [x, y, z, qx, qy, qz, qw]
    jfloatArray result = env->NewFloatArray(7);
    if (result == nullptr) {
        LOGE("Failed to allocate float array for controller pose");
        return nullptr;
    }

    float poseData[7];

    // TODO: Replace with real VR tracking when Meta XR SDK is integrated
    // For now, return default controller positions for testing

    if (hand == 0) {
        // Left hand default position
        poseData[0] = -0.3f;  // x (left of center)
        poseData[1] = 1.0f;   // y (chest/hand height)
        poseData[2] = -0.3f;  // z (slightly forward)
    } else {
        // Right hand default position
        poseData[0] = 0.3f;   // x (right of center)
        poseData[1] = 1.0f;   // y (chest/hand height)
        poseData[2] = -0.3f;  // z (slightly forward)
    }

    // Identity quaternion (no rotation)
    poseData[3] = 0.0f;  // qx
    poseData[4] = 0.0f;  // qy
    poseData[5] = 0.0f;  // qz
    poseData[6] = 1.0f;  // qw

    env->SetFloatArrayRegion(result, 0, 7, poseData);

    LOGI("Controller pose (hand %d): pos=(%.2f, %.2f, %.2f)",
         hand, poseData[0], poseData[1], poseData[2]);

    return result;
}

// ============================================================================
// VOICE RECORDING - AUDIO PROCESSING
// ============================================================================

extern "C" JNIEXPORT void JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativePushAudio(
        JNIEnv* env,
        jobject /* this */,
        jshortArray audioData,
        jint size) {

    if (g_voiceBridge == nullptr) {
        LOGE("nativePushAudio: Voice bridge not initialized");
        return;
    }

    jshort* samples = env->GetShortArrayElements(audioData, nullptr);
    if (samples == nullptr) {
        LOGE("Failed to get audio samples");
        return;
    }

    // Process audio data
    g_voiceBridge->ProcessAudioData(
            reinterpret_cast<int16_t*>(samples),
            static_cast<size_t>(size)
    );

    env->ReleaseShortArrayElements(audioData, samples, JNI_ABORT);

    // Log periodically (every 100 chunks to avoid spam)
    static int chunkCount = 0;
    if (++chunkCount % 100 == 0) {
        LOGI("Audio chunks processed: %d", chunkCount);
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeFinishRecording(
        JNIEnv* env,
        jobject /* this */) {

    if (g_voiceBridge == nullptr) {
        LOGE("nativeFinishRecording: Voice bridge not initialized");
        return;
    }

    if (g_networkClient == nullptr) {
        LOGE("nativeFinishRecording: Network client not initialized");
        return;
    }

    // Get complete audio buffer
    std::vector<int16_t> fullBuffer = g_voiceBridge->FinishRecording();
    LOGI("Finished recording: %zu samples (%.2f seconds)",
         fullBuffer.size(),
         fullBuffer.size() / 16000.0f);

    if (fullBuffer.empty()) {
        LOGE("Audio buffer is empty, nothing to send");
        return;
    }

    // Post audio to backend for transcription
    g_networkClient->PostAudio(fullBuffer, 16000);
    LOGI("Audio posted to backend for transcription");
}

// ============================================================================
// CLEANUP
// ============================================================================

extern "C" JNIEXPORT void JNICALL
Java_com_byroncoughlin_vr_1construction_1quest_ImmersiveActivity_nativeShutdown(
        JNIEnv* env,
        jobject /* this */) {

    LOGI("Shutting down native components...");

    // Clean up global reference
    if (g_activityObj != nullptr) {
        env->DeleteGlobalRef(g_activityObj);
        g_activityObj = nullptr;
    }

    // Clean up engines
    if (g_engine != nullptr) {
        delete g_engine;
        g_engine = nullptr;
        LOGI("✓ Construction engine destroyed");
    }

    if (g_voiceBridge != nullptr) {
        delete g_voiceBridge;
        g_voiceBridge = nullptr;
        LOGI("✓ Voice bridge destroyed");
    }

    if (g_networkClient != nullptr) {
        delete g_networkClient;
        g_networkClient = nullptr;
        LOGI("✓ Network client destroyed");
    }

    LOGI("Native shutdown complete");
}