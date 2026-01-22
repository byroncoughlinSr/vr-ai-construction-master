#pragma once
#include <string>
#include <vector>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

class NetworkClient {
public:
    NetworkClient(const std::string& baseUrl);
    ~NetworkClient();

    // Send audio data for transcription
    void PostAudio(const std::vector<int16_t>& audioData, int sampleRate);

    // Sync current project state
    void SyncProject(const json& projectData);

private:
    std::string baseUrl;
    // Future: CURL* handle if using libcurl
};
