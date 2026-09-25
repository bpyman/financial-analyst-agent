# 08 — Containerize the analysis API

**What to build:** The Python API ships as a Docker image that runs anywhere a container runs:
- installs from the lockfile with uv;
- runs as a non-root user;
- listens on `$PORT` on all interfaces;
- starts in the recorded runtime unless configured otherwise;
- has a health check.

CI builds the image and smoke-tests the health check and one recorded-runtime turn inside the container, so a broken image never reaches a deploy.

Spec: ADR 0006 ("Hosting").

**Blocked by:** 07

**Status:** ready-for-agent

- [ ] `docker build` succeeds and the running container answers the health check and the "Verify a quarterly fact" turn
- [ ] The image excludes dev tooling, tests, `.git`, caches, and `web/`
- [ ] CI builds and smoke-tests the image
