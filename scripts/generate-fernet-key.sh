#!/usr/bin/env bash
#
# Print a new Fernet key on stdout.
#
# A Fernet key is 32 random bytes in url-safe base64, which openssl can produce
# on its own. The obvious alternative, python3 -c "... Fernet.generate_key()",
# needs the cryptography package on the host: that package lives in the API
# image, not on the machine running make, so on most hosts it raises
# ModuleNotFoundError. Docker is the only prerequisite this project asks for.
#
# Usage: ./scripts/generate-fernet-key.sh
#
# Exit codes: 1 if openssl is missing or produced something unusable.

set -euo pipefail

KEY_LENGTH=44

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl not found; it is needed to generate FERNET_KEY." >&2
  exit 1
fi

# tr rewrites the two characters where base64 and its url-safe variant differ,
# so the key matches what Fernet.generate_key() emits. Fernet decodes plain
# base64 as well, but a key holding + or / is easy to mangle on its way through
# a URL, a shell or a sed expression.
key=$(openssl rand -base64 32 | tr '+/' '-_')

if [ "${#key}" -ne "$KEY_LENGTH" ]; then
  echo "Expected a $KEY_LENGTH-character key from openssl, got ${#key}." >&2
  exit 1
fi

echo "$key"
