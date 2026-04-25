# Infra Module

## Purpose

`infra/` stores deployment and runtime bootstrap assets.

## Current Scope

- local `launchd` service definitions
- PostgreSQL bootstrap files
- legacy or secondary `systemd` assets

## Current Reality

The primary day-to-day runtime on this machine is local macOS `launchd`, not only remote Docker deployment.
