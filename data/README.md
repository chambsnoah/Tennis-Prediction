# Data Directory

This directory contains runtime state files, cached data, and other persistent application data.

## Files

- `rate_limiter_state.json` - Rate limiter runtime state and usage tracking
- Other runtime data files will be stored here as the application evolves

## Note

Files in this directory are typically generated at runtime and may change frequently. Most should be included in `.gitignore` for cleaner version control.