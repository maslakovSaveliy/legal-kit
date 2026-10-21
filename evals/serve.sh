#!/bin/sh
# Serve one fixture on 127.0.0.1 so the URL-only evals can scan it like a live site.
#
# Usage: evals/serve.sh <fixture-name> [port]      (default port 8731)
#
# The fixture is copied to a temporary directory first, without the skill's
# working folder (.legal/) and server-side handlers (send.php), so a URL-only
# run cannot read the owner's answers or the source of the form handler.
# Stop the server with Ctrl-C or by killing this script; the copy is removed.
set -eu

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "usage: $0 <fixture-name> [port]" >&2
  exit 2
fi

name=$1
port=${2:-8731}
here=$(cd "$(dirname "$0")" && pwd)
src="$here/fixtures/$name"

if [ ! -d "$src" ]; then
  echo "no such fixture: $name (looked in $here/fixtures)" >&2
  exit 2
fi
case "$port" in
  ''|*[!0-9]*) echo "bad port: $port" >&2; exit 2 ;;
esac

stage=$(mktemp -d)
(cd "$src" && tar cf - --exclude=.legal --exclude=send.php .) | (cd "$stage" && tar xf -)

python3 -m http.server "$port" --bind 127.0.0.1 --directory "$stage" &
server=$!
trap 'kill "$server" 2>/dev/null; rm -rf "$stage"' EXIT INT TERM

echo "serving $name on http://127.0.0.1:$port/"
wait "$server"
