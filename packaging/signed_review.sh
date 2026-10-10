#!/usr/bin/env bash
# For an ephemeral GitHub-hosted Mac runner. This uploads no release.
set -euo pipefail
for task_secret in APPLE_CERTIFICATE_P12_BASE64 APPLE_CERTIFICATE_PASSWORD MUSIC_ANALYZER_CODESIGN_IDENTITY APPLE_NOTARY_KEY_P8_BASE64 APPLE_NOTARY_KEY_ID APPLE_NOTARY_ISSUER_ID; do
  if [ -z "${!task_secret:-}" ]; then
    echo "Missing configured Apple signing secret: $task_secret" >&2
    exit 1
  fi
done
task_private=$(mktemp -d "$RUNNER_TEMP/music-analyzer-signing.XXXXXX")
task_keychain="$task_private/build.keychain-db"
task_password=$(openssl rand -hex 24)
cleanup() {
  security list-keychains -d user -s "$HOME/Library/Keychains/login.keychain-db" || true
  security delete-keychain "$task_keychain" >/dev/null 2>&1 || true
  rm -rf "$task_private"
}
trap cleanup EXIT
printf '%s' "$APPLE_CERTIFICATE_P12_BASE64" | base64 --decode > "$task_private/certificate.p12"
printf '%s' "$APPLE_NOTARY_KEY_P8_BASE64" | base64 --decode > "$task_private/notary.p8"
security create-keychain -p "$task_password" "$task_keychain"
security set-keychain-settings -lut 21600 "$task_keychain"
security unlock-keychain -p "$task_password" "$task_keychain"
security import "$task_private/certificate.p12" -P "$APPLE_CERTIFICATE_PASSWORD" -A -t cert -f pkcs12 -k "$task_keychain"
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$task_password" "$task_keychain" >/dev/null
security list-keychains -d user -s "$task_keychain" "$HOME/Library/Keychains/login.keychain-db"
python -m PyInstaller --clean --noconfirm packaging/desktop.spec
task_app='dist/Music Analyzer.app'
mkdir -p artifacts
codesign --verify --deep --strict --verbose=2 "$task_app"
ditto -c -k --sequesterRsrc --keepParent "$task_app" "$task_private/submission.zip"
xcrun notarytool submit "$task_private/submission.zip" --key "$task_private/notary.p8" --key-id "$APPLE_NOTARY_KEY_ID" --issuer "$APPLE_NOTARY_ISSUER_ID" --wait --output-format json > artifacts/notarization.json
python -c 'import json; assert json.load(open("artifacts/notarization.json"))["status"] == "Accepted", "Apple notarization was not accepted"'
xcrun stapler staple "$task_app"
xcrun stapler validate "$task_app"
codesign --verify --deep --strict --verbose=2 "$task_app"
spctl --assess --type execute --verbose=2 "$task_app"
ditto -c -k --sequesterRsrc --keepParent "$task_app" artifacts/Music-Analyzer-macos-arm64-signed-review.zip
shasum -a 256 artifacts/Music-Analyzer-macos-arm64-signed-review.zip > artifacts/SHA256SUMS
cp -R build/third-party-notices artifacts/third-party-notices
python -m pip freeze --exclude-editable > artifacts/macos-arm64-build-requirements.txt
