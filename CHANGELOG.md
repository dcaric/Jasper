# Changelog

All notable changes to the Jasper project will be documented in this file.

## [1.1.0] - 2026-01-08

### Added
- **Smart Bootstrapper**: Added `run.py` as the primary entry point which automatically handles environment setup (`.env`), missing AI models via Ollama, and initial index building.
- **Standardized Search Connectors**: Implemented `SearchConnector` ABC. Gmail, Outlook (Hybrid COM/IMAP), Files, and Semantic search are now modular plugins.
- **Environment Variable Support**: Added `python-dotenv` integration for secure credential management.
- **Index Management CLI**: `indexer.py` now supports `build`, `refresh`, `status`, and `prune` commands.
- **Gemma3 Support**: Integrated Gemma3 4B as the primary summarization and chat fallback specialist.
- **Variety Deduplication**: Improved semantic search results by filtering out redundant duplicate file matches.

### Changed
- **Modular Packaging**: Refactored the flat project structure into a proper `jasper/` Python package.
- **Relocated Assets**: Centralized automation scripts in `startup/` and web assets in `jasper/static/`.
- **Enhanced Refinement**: Standardized query cleaning across all search connectors to prevent AI hallucinations (stripping "find", "search", etc.).
- **Windows Integration**: Updated `setup_automation.bat` to work with the new package structure.

### Fixed
- **Gmail Date Filtering**: Fixed logic where exact single-day searches returned no results due to exclusive boundaries.
- **Frontend Crashes**: Resolved JavaScript errors caused by missing metadata in file search results.
- **Import Loops**: Fixed circular dependency issues during model initialization.

## [1.0.0] - 2026-01-05

### Added
- Initial release of Jasper AI Assistant.
- Basic Gmail and Outlook search capabilities.
- Local file search using Windows Indexer.
- FastAPI-based web dashboard.
- Dual-model intent routing (FunctionGemma + Gemini).
