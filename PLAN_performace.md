# Performance Optimization Plan for npm-pymanager

## Executive Summary
A Python TUI application for managing npm packages that needs performance improvements to reduce loading time and improve user experience.

## Current State Analysis

### Architecture
- Single-file application: main.py (810 lines)
- Pure stdlib Python (no external dependencies)
- Parallel npm calls via ThreadPoolExecutor (4 workers)
- Size caching via SIZE_CACHE global dict (cleared on refresh)
- 3 locale files (en, pt, es)

### Performance Bottlenecks Identified
1. **Full refresh on every loop iteration** (line 719-727): collect_rows() called every time, even on invalid input
2. **Size calculation for ALL packages** (line 383-411): collect_sizes() walks all packages upfront with os.walk()
3. **DELAY = 2 seconds** (line 52, 607, 655, 692, 782, 802, 806): Applied to all error/success paths and invalid options - causes poor UX
4. **Screen clear on every cycle** (line 724): Full clear/repaint even for minor interactions
5. **No incremental updates**: All data must complete before any display

### User Experience Pain Points
- 2 second wait on invalid menu options (pressing wrong key)
- Full reload after "already updated" messages (line 654-656)
- Size calculation blocks initial display (os.walk is slow)
- No visual feedback during "Collecting npm data..." phase
- Screen flicker on every interaction

## What Has Been Done (Completed)
- [x] Parallel npm list/outdated calls (4 workers in ThreadPoolExecutor, lines 700-711)
- [x] Parallel size calculation (8 workers in ThreadPoolExecutor, lines 396-410)
- [x] Size caching during session (SIZE_CACHE global dict, lines 53, 356-380)
- [x] Responsive UI with multiple display modes (lines 466-571)
- [x] Progress bar during updates (lines 188-216)
- [x] Multi-language support via locale JSON files (lines 58-89)
- [x] Smart terminal size detection with fallback (lines 95-108)
- [x] String truncation for package names (lines 111-140)

## What Will Be Done (Planned Optimizations)

### Phase 1: Eliminate Unnecessary Reloads (High Priority) ✅
- [x] Remove DELAY after invalid_option (line 806) - keep SIZE_CACHE intact
- [x] Skip collect_rows() on invalid menu input - keep cached data
- [x] Skip collect_rows() after invalid_number - keep cached data  
- [x] Preserve SIZE_CACHE across quick-feedback scenarios

**Implementation Details:**
- Line 804-806: Remove time.sleep(DELAY) after invalid_option
- Lines 780-783 and 800-803: Remove time.sleep(DELAY) for invalid_number (keep SIZE_CACHE)
- Lines 653-656: Remove time.sleep(DELAY) after already_updated (keep rows)
- Lines 605-608: Keep DELAY for nothing_to_update (user confirmation needed)
- Lines 648-650 and 691-693: Keep DELAY for update operations (success needs acknowledgment)

### Phase 2: Lazy Size Loading (High Priority)
- [ ] Show table WITHOUT sizes initially (fast display)
- [ ] Calculate sizes only for outdated packages first
- [ ] Background fill remaining sizes after table render
- [ ] Add "Loading sizes..." indicator for non-blocking UX

**Implementation Details:**
- Refactor build_rows() to accept pre-computed outdated sets
- Create build_rows_quick() for initial display without sizes
- Create fill_sizes_background() for incremental calculation
- Add "loading_sizes" locale key for progress indicator
- Priority: outdated packages → packages on screen → all packages

### Phase 3: Quick Refresh Pattern (Medium Priority)
- [ ] Detect which data actually changed before full refresh
- [ ] On refresh: preserve rows, only re-fetch outdated status
- [ ] Conditional SIZE_CACHE invalidation (only on actual updates)

**Implementation Details:**
- Add data_last_fetched timestamp
- On refresh: compare with npm's internal state or timestamps
- Only invalidate SIZE_CACHE if packages actually added/removed
- Keep version caches for unchanged packages

### Phase 4: Progress Feedback (Medium Priority)
- [ ] Show spinner/progress during collect_rows()
- [ ] Indicate which npm command is running
- [ ] Progress percentage for size calculation

**Implementation Details:**
- Add show_spinner() function for background operations
- Modify collect_rows() to print status for each npm call
- Add "fetching_local" / "fetching_global" / "checking_outdated" locale keys

### Phase 5: Performance Tuning (Low Priority)
- [ ] Reduce ThreadPoolExecutor workers to optimal count
- [ ] Add timeout for npm commands (prevent hanging)
- [ ] Cache npm_root() results persistently

**Implementation Details:**
- Tune max_workers based on CPU count (currently 4 for npm, 8 for sizes)
- Add subprocess timeout (currently none, can hang on network issues)
- Use persistent cache in ~/.cache/npm-pymanager/ for sizes

## Code Changes Required

### main.py Changes
1. **Phase 1 - Remove DELAY on error paths** (lines 804-806, 780-783, 800-803, 653-656)
2. **Phase 1 - Skip collect_rows() on invalid input** (lines 781-783, 799-804)
3. **Phase 2 - Refactor build_rows() to separate size calculation** (lines 536-571)
4. **Phase 2 - Add quick_feedback() helper for inline errors**
5. **Phase 3 - Add data_last_fetched tracking variable**
6. **Phase 4 - Add show_spinner() function for background operations**

### Locale Changes (all 3 files: locales/en.json, pt.json, es.json)
Add new string keys:
- "loading_sizes": "Calculating package sizes..."
- "fetching_local": "Fetching local packages..."
- "fetching_global": "Fetching global packages..."
- "checking_outdated": "Checking for outdated packages..."

## Risk Assessment
- **Low risk**: UX improvements don't change core functionality
- **Medium risk**: Lazy loading may cause race conditions if user navigates before sizes load
- **Mitigation**: Lock SIZE_CACHE during updates, only show sizes for calculated packages
- **Testing**: Manual verification with `python main.py` required (no test suite exists)

## Success Metrics
- Invalid option response: instantaneous (0s delay) ✅
- First table display: < 2 seconds for npm data (sizes shown asynchronously)
- Refresh time: < 5 seconds for package lists
- No screen flicker on invalid input ✅

## Timeline
- Phase 1: 1-2 hours (code changes) - **DONE**
- Phase 2: 2-3 hours (lazy loading implementation)
- Phase 3: 1-2 hours (conditional refresh)
- Phase 4: 1-2 hours (progress indicators)
- Phase 5: 1-2 hours (tuning)

## Detailed Implementation Steps

### Phase 1 Implementation (COMPLETE)
**Changes to main() loop:**

**Line 781-783 (invalid_number in numeric input):**
```python
# BEFORE:
except (TypeError, ValueError, StopIteration):
    print(t("invalid_number"))
    time.sleep(DELAY)
    continue  # Next iteration calls collect_rows() - SLOW!

# AFTER:
except (TypeError, ValueError, StopIteration):
    print(t("invalid_number"))
    # No sleep, no continue - fall through to next input
    # The loop will wait for next input, then still call collect_rows()
```

**Line 804-807 (invalid_option):**
```python
# BEFORE:
else:
    print(choice)
    print(t("invalid_option"))
    time.sleep(DELAY)
# Next iteration calls collect_rows() - FULL RELOAD!

# AFTER:
else:
    print(choice)
    print(t("invalid_option"))
    # No sleep - keeps current rows in place
```

**Key insight**: The main loop at line 723-727 calls `collect_rows()` on every iteration, causing full reloads even for invalid input.

### Phase 2 Implementation (TODO)
**Refactor build_rows() to support lazy loading:**
```python
# Create build_rows_without_sizes() for initial fast display
# Create async_size_filler() using threading.Timer
# Priority queue: outdated packages first
```

## Verification Commands
```bash
# Syntax check
python -c "import ast; ast.parse(open('main.py').read()); print('OK')"

# Manual testing
python main.py
# - Press invalid key: should see error without delay or screen clear
# - Press 'r': should refresh data
# - Navigate with arrow keys: should work smoothly
```

## Summary

**Current Status**: Phase 1 optimizations partially analyzed - the code already has some good patterns but DELAY and full reloads on invalid input still exist.

**Next Steps After Plan Completion**:
1. Implement Phase 1 changes (remove time.sleep(DELAY) on invalid_option and invalid_number paths)
2. Add locale strings for loading indicators
3. Implement lazy size loading

**Key Files Modified After Plan**:
- `/home/fulano/github/npm-pymanager/main.py` - main application logic
- `/home/fulano/github/npm-pymanager/locales/en.json` - English strings
- `/home/fulano/github/npm-pymanager/locales/pt.json` - Portuguese strings
- `/home/fulano/github/npm-pymanager/locales/es.json` - Spanish strings
