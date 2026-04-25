# Catalog Domain

## Purpose

`domain/catalog` defines the reusable contracts behind categories, templates, attributes, and model-catalog structure.

## Current Reality

This domain supports the canonical category-driven architecture:

- `category`
- `category_attr_template`
- `category_attr_template_item`
- `attribute_definition` and `attribute_option`
- `category_model_catalog` and aliases

## Boundary

This layer should describe catalog rules and payload shapes, not dashboard or runtime behavior.
