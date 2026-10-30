plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.jetbrains.kotlin.android)
    alias(libs.plugins.jetbrains.kotlin.plugin.compose)
}

android {
    namespace = "com.byroncoughlin.vr_construction_quest"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.byroncoughlin.vr_construction_quest"
        minSdk = 29  // Quest 2
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"

        externalNativeBuild {
            cmake {
                cppFlags("-std=c++17")
                arguments("-DANDROID_STL=c++_shared")
            }
        }

        ndk {
            abiFilters += "arm64-v8a"
        }

        // Network endpoints, from gradle.properties (serverHost, collabToken).
        val serverHost = (project.findProperty("serverHost") as String?) ?: "192.168.4.249"
        val collabToken = (project.findProperty("collabToken") as String?) ?: ""
        buildConfigField("String", "SERVER_URL", "\"http://$serverHost:8000\"")
        buildConfigField("String", "WS_URL", "\"ws://$serverHost:8000/api/v1/ws\"")
        // The built dashboard behind Apache (deploy/apache/vr-construction.conf).
        buildConfigField("String", "DASHBOARD_URL", "\"http://$serverHost:8081\"")
        buildConfigField("String", "COLLAB_TOKEN", "\"$collabToken\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        viewBinding = true
        compose = true
        buildConfig = true
    }
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    // Meta Spatial SDK
    implementation(libs.meta.spatial.sdk.base)
    implementation(libs.meta.spatial.sdk.vr)
    implementation(libs.meta.spatial.sdk.toolkit)
    implementation(libs.meta.spatial.sdk.castinputforward)
    implementation(libs.meta.spatial.sdk.ovrmetrics)
    implementation(libs.meta.spatial.sdk.physics)
    implementation(libs.meta.spatial.sdk.compose)

    // Kotlin / AndroidX
    implementation(libs.androidx.core.ktx)
    implementation("androidx.appcompat:appcompat:1.6.1")

    // Compose
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.compose.foundation)
    implementation(libs.androidx.compose.material3)

    // Networking
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
    implementation(libs.androidx.scenecore)

    // Unit tests (app/src/test)
    testImplementation("junit:junit:4.13.2")
}
