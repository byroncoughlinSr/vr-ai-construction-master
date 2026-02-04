#include "construction_engine.h"
#include <algorithm>
#include <limits>
#include <cmath>

ConstructionEngine::ConstructionEngine() : nextId(1) {}

ConstructionEngine::~ConstructionEngine() {}

int ConstructionEngine::AddElement(ElementType type, Vec3 pos, Vec3 dim) {
    ConstructionElement element;
    element.id = nextId++;
    element.type = type;
    element.position = pos;
    element.dimensions = dim;
    elements.push_back(element);
    return element.id;
}

bool ConstructionEngine::UpdateElement(int id, Vec3 pos, Vec3 dim) {
    for (auto& element : elements) {
        if (element.id == id) {
            element.position = pos;
            element.dimensions = dim;
            return true;
        }
    }
    return false;
}

bool ConstructionEngine::RemoveElement(int id) {
    auto it = std::remove_if(elements.begin(), elements.end(),
                             [id](const ConstructionElement& e) { return e.id == id; });
    if (it != elements.end()) {
        elements.erase(it, elements.end());
        return true;
    }
    return false;
}

const std::vector<ConstructionElement>& ConstructionEngine::GetElements() const {
    return elements;
}

std::optional<ConstructionElement> ConstructionEngine::GetElement(int id) const {
    for (const auto& element : elements) {
        if (element.id == id) {
            return element;
        }
    }
    return std::nullopt;
}

Vec3 ConstructionEngine::SnapToGrid(Vec3 pos, float gridSize) {
    if (gridSize <= 0.0f) return pos;
    return {
        std::round(pos.x / gridSize) * gridSize,
        std::round(pos.y / gridSize) * gridSize,
        std::round(pos.z / gridSize) * gridSize
    };
}

bool ConstructionElement::Intersect(const Ray& ray, float& t) const {
    Vec3 minV = {position.x - dimensions.x / 2.0f, position.y - dimensions.y / 2.0f, position.z - dimensions.z / 2.0f};
    Vec3 maxV = {position.x + dimensions.x / 2.0f, position.y + dimensions.y / 2.0f, position.z + dimensions.z / 2.0f};

    float t1 = (minV.x - ray.origin.x) / ray.direction.x;
    float t2 = (maxV.x - ray.origin.x) / ray.direction.x;
    float tmin = std::min(t1, t2);
    float tmax = std::max(t1, t2);

    t1 = (minV.y - ray.origin.y) / ray.direction.y;
    t2 = (maxV.y - ray.origin.y) / ray.direction.y;
    tmin = std::max(tmin, std::min(t1, t2));
    tmax = std::min(tmax, std::max(t1, t2));

    t1 = (minV.z - ray.origin.z) / ray.direction.z;
    t2 = (maxV.z - ray.origin.z) / ray.direction.z;
    tmin = std::max(tmin, std::min(t1, t2));
    tmax = std::min(tmax, std::max(t1, t2));

    t = tmin;
    return tmax >= std::max(0.0f, tmin);
}

std::optional<int> ConstructionEngine::Raycast(const Ray& ray, float& outDistance) {
    std::optional<int> hitId = std::nullopt;
    float minT = std::numeric_limits<float>::infinity();

    for (const auto& element : elements) {
        float t;
        if (element.Intersect(ray, t)) {
            if (t < minT) {
                minT = t;
                hitId = element.id;
            }
        }
    }

    if (hitId) {
        outDistance = minT;
    }
    return hitId;
}
