#include "voice_bridge.h"
#include <android/log.h>

#define LOG_TAG "VRVoiceBridge"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

VoiceBridge::VoiceBridge() {
    LOGI("VoiceBridge initialized");
}

VoiceBridge::~VoiceBridge() {}

void VoiceBridge::ProcessAudioData(const int16_t* data, size_t size) {
    // Append incoming PCM data to our buffer
    audioBuffer.insert(audioBuffer.end(), data, data + size);
}

std::vector<int16_t> VoiceBridge::FinishRecording() {
    LOGI("Finishing recording with %zu samples", audioBuffer.size());
    std::vector<int16_t> result = std::move(audioBuffer);
    audioBuffer.clear(); // Ensure it's ready for next recording
    return result;
}

void VoiceBridge::SetTranscriptionCallback(std::function<void(const std::string&)> callback) {
    onTranscriptionReceived = callback;
}
