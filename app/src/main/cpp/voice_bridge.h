#pragma once
#include <vector>
#include <string>
#include <functional>

class VoiceBridge {
public:
    VoiceBridge();
    ~VoiceBridge();

    // Buffer audio data from Android
    void ProcessAudioData(const int16_t* data, size_t size);

    // Finalize recording and return the full buffer for the AI backend
    std::vector<int16_t> FinishRecording();

    // Future: Add callback for when transcription is received
    void SetTranscriptionCallback(std::function<void(const std::string&)> callback);

private:
    std::vector<int16_t> audioBuffer;
    std::function<void(const std::string&)> onTranscriptionReceived;
};
