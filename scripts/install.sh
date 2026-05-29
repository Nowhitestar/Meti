#!/usr/bin/env bash
set -euo pipefail

REPO="${METI_RELEASE_REPO:-Nowhitestar/meti}"
VERSION=""
LATEST=1
TARGET="$(pwd)"
YES=0
DRY_RUN=0
VERSION_RE='^v[0-9]+\.[0-9]+\.[0-9]+$'

usage() {
  cat <<'EOF'
Usage: scripts/install.sh [options]

Options:
  --version vX.Y.Z   Install an explicit GitHub Release version.
  --latest          Install the latest stable GitHub Release (default).
  --target DIR      Install into DIR (default: current directory).
  --yes             Skip confirmation.
  --dry-run         Print the plan without downloading or modifying files.
  --help            Show this help.

Normal reinstall/update preserves:
  ~/.config/meti
  ~/.config/meti/credentials.json.age
  ~/.config/meti/age-key.txt
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --version)
      VERSION="${2:-}"
      LATEST=0
      shift 2
      ;;
    --latest)
      VERSION=""
      LATEST=1
      shift
      ;;
    --target)
      TARGET="${2:-}"
      shift 2
      ;;
    --yes)
      YES=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -z "$TARGET" ]; then
  echo "ERROR: --target requires a directory" >&2
  exit 2
fi

TARGET="$(python3 -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]).expanduser().resolve(strict=False))' "$TARGET")"
HOME_DIR="$(python3 -c 'import pathlib; print(pathlib.Path.home().resolve(strict=False))')"
case "$TARGET" in
  "/"|"${HOME_DIR}"|"${HOME_DIR}/.config"|"${HOME_DIR}/.config/meti")
    echo "ERROR: refusing unsafe install target: ${TARGET}" >&2
    exit 2
    ;;
esac

resolve_latest() {
  curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" |
    python3 -c 'import json, sys; print(json.load(sys.stdin)["tag_name"])'
}

if [ "$LATEST" -eq 1 ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    TARGET_VERSION="latest stable"
    RELEASE_URL="https://github.com/${REPO}/releases/latest/download"
    ASSET="meti-openclaw-skill-vX.Y.Z.zip"
  else
    TARGET_VERSION="$(resolve_latest)"
    RELEASE_URL="https://github.com/${REPO}/releases/download/${TARGET_VERSION}"
    ASSET="meti-openclaw-skill-${TARGET_VERSION}.zip"
  fi
else
  TARGET_VERSION="$VERSION"
  if ! printf '%s\n' "$TARGET_VERSION" | grep -Eq "$VERSION_RE"; then
    echo "ERROR: --version must be vX.Y.Z, got: ${TARGET_VERSION}" >&2
    exit 2
  fi
  RELEASE_URL="https://github.com/${REPO}/releases/download/${TARGET_VERSION}"
  ASSET="meti-openclaw-skill-${TARGET_VERSION}.zip"
fi

echo "Meti installer"
echo "target version: ${TARGET_VERSION}"
echo "install target: ${TARGET}"
echo "release asset: ${RELEASE_URL}/${ASSET}"
echo "checksums: ${RELEASE_URL}/SHA256SUMS"
echo "release manifest: ${RELEASE_URL}/release.json"
echo "preserve user config: ~/.config/meti, ~/.config/meti/credentials.json.age, ~/.config/meti/age-key.txt"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry-run: no files will be downloaded or modified"
  exit 0
fi

if [ "$YES" -ne 1 ]; then
  printf "Install Meti %s into %s? Type 'yes' to continue: " "$TARGET_VERSION" "$TARGET"
  read -r ANSWER
  if [ "$ANSWER" != "yes" ]; then
    echo "Install cancelled."
    exit 1
  fi
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cd "$TMP_DIR"
curl -fsSLO "${RELEASE_URL}/SHA256SUMS"
curl -fsSLO "${RELEASE_URL}/release.json"
curl -fsSLO "${RELEASE_URL}/${ASSET}"
grep "  ${ASSET}$" SHA256SUMS | shasum -a 256 -c -

STAGING="${TMP_DIR}/staging"
mkdir -p "$STAGING"
unzip -q "$ASSET" -d "$STAGING"

mkdir -p "$TARGET"
for item in core providers scripts docs examples .claude-plugin SKILL.md README.md CHANGELOG.md release.json; do
  rm -rf "${TARGET:?}/${item}"
  if [ -e "${STAGING}/${item}" ]; then
    cp -R "${STAGING}/${item}" "${TARGET}/${item}"
  fi
done

echo "OK: installed Meti ${TARGET_VERSION} into ${TARGET}"
echo "User config preserved under ~/.config/meti"
