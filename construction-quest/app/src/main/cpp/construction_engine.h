#pragma once
#include <vector>
#include <string>
#include <cmath>
#include <optional>

struct Vec3 {
    float x, y, z;

    Vec3 operator+(const Vec3& other) const { return {x + other.x, y + other.y, z + other.z}; }
    Vec3 operator-(const Vec3& other) const { return {x - other.x, y - other.y, z - other.z}; }
    Vec3 operator*(float s) const { return {x * s, y * s, z * s}; }
};

struct Ray {
    Vec3 origin;
    Vec3 direction;
};

enum class ElementType {
    WALL = 0,
    FLOOR = 1,
    DOOR = 2,
    WINDOW = 3
};

struct ConstructionElement {
    int id;
    ElementType type;
    Vec3 position;
    Vec3 dimensions;

    bool Intersect(const Ray& ray, float& t) const;
};

class ConstructionEngine {
public:
    ConstructionEngine();
    ~ConstructionEngine();

    int AddElement(ElementType type, Vec3 pos, Vec3 dim);
    bool UpdateElement(int id, Vec3 pos, Vec3 dim);
    bool RemoveElement(int id);
    const std::vector<ConstructionElement>& GetElements() const;
    std::optional<ConstructionElement> GetElement(int id) const;

    // Phase 2: Grid & Interaction
    Vec3 SnapToGrid(Vec3 pos, float gridSize);
    std::optional<int> Raycast(const Ray& ray, float& outDistance);

private:
    std::vector<ConstructionElement> elements;
    int nextId;
};
