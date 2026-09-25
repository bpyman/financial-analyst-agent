#!/bin/sh
# Vercel "Ignored Build Step" (web/vercel.json ignoreCommand). Vercel runs it
# from the project's Root Directory, web/: exit 0 skips the build, exit 1 builds.
#
# Skip only when nothing under web/ changed since this branch's last successful
# deployment, so Python-only commits do not rebuild the window. When that is
# unknown (a branch's first deploy, or a commit outside the shallow clone),
# build.

previous="${VERCEL_GIT_PREVIOUS_SHA:-}"

if [ -z "$previous" ]; then
  echo "No previous deployment on this branch: building."
  exit 1
fi

if ! git cat-file -e "${previous}^{commit}" 2>/dev/null; then
  echo "Previous deployment ${previous} is not in the clone: building."
  exit 1
fi

if git diff --quiet "$previous" HEAD -- .; then
  echo "Nothing under web/ changed since ${previous}: skipping the build."
  exit 0
fi

echo "web/ changed since ${previous}: building."
exit 1
