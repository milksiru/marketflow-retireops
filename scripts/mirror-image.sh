#!/usr/bin/env bash
set -euo pipefail

source_image="${1:-}"
target_image="${2:-}"
registry="192.168.55.148:5000"

if [ -z "$source_image" ]; then
  echo "usage: $0 <external-image> [internal-image]" >&2
  exit 2
fi

if [ -z "$target_image" ]; then
  target_image="${registry}/mirror/${source_image}"
fi

podman pull "$source_image"
podman tag "$source_image" "$target_image"
podman push --tls-verify=false "$target_image"

echo "$target_image"
