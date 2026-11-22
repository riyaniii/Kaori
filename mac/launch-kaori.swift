import Foundation

// Minimal .app launcher. macOS runs Contents/MacOS/Kaori (this binary); it sets
// the working directory to Contents/Resources and hands over to the PyInstaller
// executable there. This mirrors the layout Varia uses.

let bundleURL = Bundle.main.bundleURL
let resourcesdir = bundleURL.appendingPathComponent("Contents/Resources")

FileManager.default.changeCurrentDirectoryPath(resourcesdir.path)

let execPath = resourcesdir.appendingPathComponent("Kaori").path

let args: [UnsafeMutablePointer<CChar>?] = [
    strdup("Kaori"),
    nil,
]

execv(execPath, args)
