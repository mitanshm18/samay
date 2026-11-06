# Storage budget

Target machine: MacBook Air M4, 16 GB RAM, 256 GB SSD, about 29 GB free at the start.

**Guardrail: stop if free space falls below 20 GB.** `make doctor` fails below 20 GB
and warns below 25 GB.

| Stage | Estimated additional space |
| --- | --- |
| Milestone 1 (repo, Python env, npm packages, empty database) | about 0.8 GB |
| Whole project, including Playwright headless shell and reports | about 1.5 to 2.5 GB |

What keeps it small:

- No new Docker images: the existing PostgreSQL 16 image is reused (`pull_policy: never`).
- uv uses the Python already installed (`UV_PYTHON_DOWNLOADS=never`).
- Only the Playwright Chromium headless shell, not full browsers.
- No pandas, OR-Tools, WeasyPrint or large datasets.

Cleaning up SAMAY later only ever targets SAMAY's own resources
(`samay-db`, `samay_pgdata`, this folder). See [docker-safety.md](docker-safety.md).
