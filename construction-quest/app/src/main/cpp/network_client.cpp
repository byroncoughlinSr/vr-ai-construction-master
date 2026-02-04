#include "network_client.h"
#include <android/log.h>
#include <jni.h>

#define LOG_TAG "VRNetworkClient"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

// External JNI environment references
extern JavaVM* g_javaVM;
extern jobject g_activityObj;

NetworkClient::NetworkClient(const std::string& baseUrl) : baseUrl(baseUrl) {
    LOGI("NetworkClient initialized with base URL: %s", baseUrl.c_str());
}

NetworkClient::~NetworkClient() {}

void NetworkClient::PostAudio(JNIEnv* env, const std::vector<int16_t>& audioData, int sampleRate) {
    LOGI("PostAudio called with %zu samples", audioData.size());

    if (!env) {
        LOGI("PostAudio: No JNIEnv provided, skipping");
        return;
    }

    jclass activityClass = env->GetObjectClass(g_activityObj);
    jmethodID postAudioMethod = env->GetMethodID(activityClass, "onNativePostAudio", "([SI)V");

    if (postAudioMethod) {
        jshortArray jAudioData = env->NewShortArray(audioData.size());
        env->SetShortArrayRegion(jAudioData, 0, audioData.size(), reinterpret_cast<const jshort*>(audioData.data()));

        env->CallVoidMethod(g_activityObj, postAudioMethod, jAudioData, sampleRate);

        env->DeleteLocalRef(jAudioData);
    }

    // DO NOT call DetachCurrentThread() here - the JNI runtime manages this thread!
}

void NetworkClient::SyncProject(JNIEnv* env, const json& projectData) {
    std::string jsonStr = projectData.dump();
    LOGI("SyncProject called with data: %s", jsonStr.c_str());

    if (!env) {
        LOGI("SyncProject: No JNIEnv provided, skipping");
        return;
    }

    jclass activityClass = env->GetObjectClass(g_activityObj);
    jmethodID syncProjectMethod = env->GetMethodID(activityClass, "onNativeSyncProject", "(Ljava/lang/String;)V");

    if (syncProjectMethod) {
        jstring jJsonStr = env->NewStringUTF(jsonStr.c_str());
        env->CallVoidMethod(g_activityObj, syncProjectMethod, jJsonStr);
        env->DeleteLocalRef(jJsonStr);
    }

    // DO NOT call DetachCurrentThread() here - the JNI runtime manages this thread!
}
