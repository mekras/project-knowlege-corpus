# Changelog

All notable changes to this project will be documented in this file.

## 0.5.0

- Added the `external_reference` retrieval mode for sources that cannot or
  should not be copied into the corpus: direct, on-demand access to the
  primary source with locator, copy policy, and access checks instead of a
  local copy.
- Documented copy policies and retrieval modes across the inventory,
  source-add, and pipeline skills and references.
- Added trigger and result-scenario coverage for direct source access.
- Clarified agent instructions: changes are confined to the project folder and
  Git rules.

## 0.4.0

- Added `index_only` and `on_demand` source handling across the inventory,
  source-add, and pipeline skills.
- Documented storage strategies for large, expensive, and license-restricted
  sources.
- Added trigger and result-scenario coverage for the new source handling mode.
