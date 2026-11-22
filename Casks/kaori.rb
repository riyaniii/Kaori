cask "kaori" do
  arch arm: "arm64", intel: "x86_64"

  version "1.0.0"
  sha256 :no_check

  url "https://github.com/riyaniii/Kaori/releases/download/#{version}/Kaori-#{version}-#{arch}.dmg"
  name "Kaori"
  desc "Discover, download and read comics"
  homepage "https://github.com/riyaniii/Kaori"

  livecheck do
    url :url
    strategy :github_latest
  end

  depends_on macos: ">= :monterey"

  app "Kaori.app"

  zap trash: [
    "~/Library/Application Support/Tachidesk",
    "~/Library/Caches/kaori",
  ]

  caveats <<~EOS
    Kaori is not signed by Apple. If macOS refuses to open it, install with:
      brew install --cask --no-quarantine kaori
  EOS
end
