cmake_minimum_required(VERSION 3.22.1)
project("vr_construction_quest")

set(CMAKE_CXX_STANDARD 17)

add_library(${CMAKE_PROJECT_NAME} SHARED
        native-lib.cpp
        construction_engine.cpp)

target_link_libraries(${CMAKE_PROJECT_NAME}
        android
        log)
