## What this changes

## Why

## How it was checked

- [ ] `make check` passes
- [ ] `make check-docker-scope` passes (if `compose.yaml` changed)
- [ ] CI is green

## Safety

- [ ] No command touches Docker resources outside the `samay` project
- [ ] No synthetic number is presented as real; provenance is shown
- [ ] No secrets or real bills committed
