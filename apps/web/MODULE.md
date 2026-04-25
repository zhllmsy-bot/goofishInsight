# Web Assets Module

## Purpose

`apps/web` contains templates and static assets used by the internal dashboard.

## Current Scope

- dashboard shell, trend cards, and modals
- config pages
- buy opportunity page
- shared CSS and browser-side JS

## Boundary

The source of truth for business logic stays in Python services. Frontend assets should render and orchestrate, not redefine pricing or review rules.
