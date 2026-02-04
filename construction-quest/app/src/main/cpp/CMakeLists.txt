cmake_minimum_required(VERSION 3.22.1)
project("vr_construction_quest")

set(CMAKE_CXX_STANDARD 17)

# Include nlohmann/json
include(FetchContent)
FetchContent_Declare(
    json
    URL https://github.com/nlohmann/json/releases/download/v3.11.2/json.tar.xz
)
FetchContent_MakeAvailable(json)

add_library(${CMAKE_PROJECT_NAME} SHARED
        native-lib.cpp
        construction_engine.cpp
        voice_bridge.cpp
        network_client.cpp)

target_link_libraries(${CMAKE_PROJECT_NAME}
        android
        log
        nlohmann_json::nlohmann_json)
