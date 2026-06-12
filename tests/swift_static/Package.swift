// swift-tools-version: 6.0
import PackageDescription

// This package hosts static-runtime unit tests for the Swift target. It points
// its library target at ../../static/swift (the hand-written runtime that the
// generator will copy into user projects). Tests live in Tests/MyAirtableStaticTests.
//
// Invoked from myairtable/checks.sh via: cd tests/swift_static && swift test

let package = Package(
    name: "MyAirtableStatic",
    platforms: [
        .iOS(.v17),
        .macOS(.v14),
        .watchOS(.v10),
        .tvOS(.v17),
        .visionOS(.v1),
    ],
    products: [
        .library(name: "MyAirtableStatic", targets: ["MyAirtableStatic"])
    ],
    targets: [
        .target(
            // Symlink: Sources/MyAirtableStatic -> ../../../static/swift
            // (SPM requires sources inside the package root, so we symlink
            // the real static runtime directory into this package's tree.)
            name: "MyAirtableStatic",
            path: "Sources/MyAirtableStatic"
        ),
        .testTarget(
            name: "MyAirtableStaticTests",
            dependencies: ["MyAirtableStatic"],
            path: "Tests/MyAirtableStaticTests"
        ),
    ]
)
