// swift-tools-version: 5.7
import PackageDescription

// DO NOT MODIFY THIS FILE - managed by Capacitor CLI commands
// NOTE: CapacitorSplashScreen removed -- its Package.swift ships as 5.9 which
// Xcode 14 (max 5.7) cannot resolve. Splash screen handled via JS/CSS instead.
let package = Package(
    name: "CapApp-SPM",
    platforms: [.iOS(.v13)],
    products: [
        .library(
            name: "CapApp-SPM",
            targets: ["CapApp-SPM"])
    ],
    dependencies: [
        .package(url: "https://github.com/ionic-team/capacitor-swift-pm.git", exact: "8.2.0")
    ],
    targets: [
        .target(
            name: "CapApp-SPM",
            dependencies: [
                .product(name: "Capacitor", package: "capacitor-swift-pm"),
                .product(name: "Cordova", package: "capacitor-swift-pm")
            ]
        )
    ]
)
