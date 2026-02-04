#ifndef NETWORK_CLIENT_H
#define NETWORK_CLIENT_H

#include <string>
#include <vector>
#include <jni.h>
#include "nlohmann/json.hpp"

using json = nlohmann::json;

class NetworkClient {
public:
    NetworkClient(const std::string& baseUrl);
    ~NetworkClient();

    // ✅ Updated: Now accepts JNIEnv* instead of attaching/detaching internally
    void PostAudio(JNIEnv* env, const std::vector<int16_t>& audioData, int sampleRate);
    
    // ✅ Updated: Now accepts JNIEnv* instead of attaching/detaching internally
    void SyncProject(JNIEnv* env, const json& projectData);

private:
    std::string baseUrl;
};

#endif // NETWORK_CLIENT_H
