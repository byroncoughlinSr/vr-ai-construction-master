# Quest VR Construction - C++ Implementation Plan

This plan outlines the transition to or integration of a C++ core for the VR Construction Quest application, leveraging the **Meta XR SDK** and **OpenXR** for maximum performance and low-level control.

## 1. Technical Architecture

### Core Components (C++)
- **XR Runtime Wrapper:** OpenXR integration for head tracking, controller input, and frame loop management.
- **Rendering Engine:** OpenGL ES 3.0+ or Vulkan backend for high-fidelity construction visualizations.
- **Mesh Engine:** Procedural mesh generation for walls, floors, and custom architectural elements.
- **Physics Engine:** Collision detection for placement and interaction (e.g., using PhysX or a lightweight custom solution).
- **Network Layer:** C++ `libcurl` or `uWebSockets` for communicating with the Python/AI backend.

### Integration Layer (JNI)
- **Android Activity:** A thin Kotlin/Java wrapper to handle Android lifecycle and permissions.
- **JNI Bridge:** Passing events (voice, network status) between the Android UI and C++ engine.

---

## 2. Development Phases

### Phase 1: NDK Environment Setup
1.  **Configure CMake:** Add `CMakeLists.txt` to the `app/` module.
2.  **Meta XR SDK Integration:** Link against the `ovr` and OpenXR loader libraries.
3.  **Basic App:** Render a "Hello VR" cube in C++ using the Quest's compositor.

### Phase 2: OpenXR & Input Handling
1.  **Controller Integration:** Map Meta Quest Touch controller buttons and triggers to construction actions (Select, Place, Move).
2.  **Hand Tracking:** (Optional) Implement Meta's Hand Tracking API for natural interaction.

### Phase 3: Construction Logic (The "Engine")
1.  **Coordinate System:** Establish a 1:1 scale metric system for construction accuracy.
2.  **Snapping System:** Implement a grid and vertex snapping engine in C++ for precise wall alignment.
3.  **Procedural Meshing:** Develop a C++ class that generates 3D geometry from 2D floorplan data.

### Phase 4: Backend & AI Integration
1.  **Binary Serialization:** Use `Protocol Buffers` or `FlatBuffers` for efficient design data exchange between C++ and the Python backend.
2.  **Voice Upload:** Use C++ to stream microphone input to the backend for Whisper STT.

---

## 3. Recommended Technology Stack

| Component | Technology |
| :--- | :--- |
| **Language** | C++17 or C++20 |
| **Graphics API** | OpenGL ES 3.2 |
| **VR SDK** | Meta XR SDK (OpenXR) |
| **Math Library** | GLM (OpenGL Mathematics) |
| **JSON Library** | nlohmann/json |
| **Networking** | libcurl |
| **Build System** | CMake |

---

## 4. Immediate Next Steps
1.  **Initialize C++ Directory:** Create `app/src/main/cpp`.
2.  **Create CMakeLists.txt:** Configure the build to include the Meta XR libraries.
3.  **Modify `build.gradle.kts`:** Add `externalNativeBuild` block to enable C++ compilation.
4.  **Implement JNI Entry Point:** Create a `native-lib.cpp` to start the OpenXR loop.
