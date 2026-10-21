// swift-tools-version: 5.9
// Test fixture for legal-kit evals. The shop, its owner and all requisites are fictitious.
import PackageDescription

let package = Package(
    name: "ShopApp",
    platforms: [.iOS(.v17)],
    dependencies: [
        .package(url: "https://github.com/appmetrica/appmetrica-sdk-ios", from: "5.9.0"),
        .package(url: "https://github.com/firebase/firebase-ios-sdk", from: "11.6.0"),
    ],
    targets: [
        .executableTarget(
            name: "ShopApp",
            dependencies: [
                .product(name: "AppMetricaCore", package: "appmetrica-sdk-ios"),
                .product(name: "FirebaseAnalytics", package: "firebase-ios-sdk"),
            ],
            path: "Sources/ShopApp"
        ),
    ]
)
