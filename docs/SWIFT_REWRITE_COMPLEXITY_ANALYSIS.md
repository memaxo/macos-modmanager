# Swift Rewrite Complexity Analysis

## Executive Summary

Rewriting the macOS Mod Manager from Python/FastAPI to Swift would be a **moderate to high complexity** undertaking, estimated at **3-6 months** of full-time development. The rewrite offers significant benefits (native macOS integration, better performance, App Store distribution potential) but requires careful consideration of several complex dependencies and architectural decisions.

**Complexity Score: 7/10**

---

## Current Architecture Overview

### Tech Stack
- **Backend**: FastAPI (Python async web framework)
- **Database**: SQLite with SQLAlchemy ORM
- **Frontend**: HTMX + Jinja2 templates (77 HTML templates)
- **Key Dependencies**:
  - Archive extraction: `py7zr`, `rarfile`, `zipfile`
  - HTTP client: `httpx` (async)
  - Frida Python bindings for GPU profiling
  - File watching: `watchdog`
  - Cryptography: `cryptography`, `passlib`

### Core Modules
1. **Mod Management** (`app/core/mod_manager.py` - ~1200 lines)
   - Archive extraction (ZIP, 7Z, RAR)
   - Mod structure detection
   - Installation/uninstallation with atomic operations
   - Backup/rollback system
   - FOMOD installer support

2. **Compatibility System** (`app/core/compatibility.py` - ~500 lines)
   - macOS compatibility checking
   - Framework detection (RED4ext, TweakXL, ArchiveXL)
   - Incompatible mod blocking

3. **Nexus API Integration** (`app/core/nexus_api.py` - ~800 lines)
   - REST API client
   - GraphQL queries
   - Rate limiting
   - Caching layer

4. **FOMOD Parser** (`app/core/fomod_parser.py` - ~650 lines)
   - XML parsing
   - Conditional logic evaluation
   - Wizard step management

5. **GPU Profiler** (`app/core/gpu_profiler.py` - ~1100 lines)
   - Frida instrumentation
   - Metal API hooking
   - Performance metrics collection

6. **Database Models** (10 models, ~500 lines)
   - Mod, ModFile, ModDependency, ModInstallation
   - Collection, Profile, Backup
   - Settings, Compatibility records

7. **API Routes** (18 route modules)
   - RESTful endpoints
   - File upload/download
   - WebSocket for real-time updates

8. **Frontend** (77 HTML templates)
   - HTMX-based SPA-like experience
   - Real-time updates
   - Complex UI components

---

## Complexity Breakdown by Component

### ✅ Low Complexity (1-2 weeks each)

#### 1. Database Layer
**Current**: SQLAlchemy ORM with async support  
**Swift Equivalent**: SwiftData or SQLite.swift

**Migration Effort**: Low
- SQLite schema is straightforward
- SwiftData provides similar ORM capabilities
- Async/await patterns translate well

**Considerations**:
- SwiftData is iOS 17+ / macOS 14+ only (may need SQLite.swift for older macOS)
- Migration scripts need rewriting (currently Alembic)

#### 2. Configuration Management
**Current**: Pydantic Settings  
**Swift Equivalent**: `UserDefaults`, `PropertyListDecoder`, or Swift Property Wrappers

**Migration Effort**: Low
- Simple key-value storage
- Swift has excellent property wrapper support

#### 3. File System Operations
**Current**: `pathlib`, `aiofiles`  
**Swift Equivalent**: `Foundation.FileManager`, `async/await` file operations

**Migration Effort**: Low
- Native Swift file APIs are robust
- Better integration with macOS security model

#### 4. Basic HTTP Client
**Current**: `httpx`  
**Swift Equivalent**: `URLSession` with async/await

**Migration Effort**: Low
- URLSession is mature and well-documented
- Async/await support since Swift 5.5

---

### ⚠️ Moderate Complexity (2-4 weeks each)

#### 5. Archive Extraction
**Current**: `py7zr`, `rarfile`, `zipfile`  
**Swift Equivalent**: Need to find or build libraries

**Migration Effort**: Moderate-High

**Challenges**:
- **7Z extraction**: No mature Swift library. Options:
  - Use `lib7z` via C interop (complex)
  - Shell out to `7z` command-line tool (requires external dependency)
  - Port `py7zr` logic (significant effort)

- **RAR extraction**: No native Swift support. Options:
  - Use `unrar` command-line tool (requires external dependency)
  - Port `rarfile` logic (significant effort)

- **ZIP extraction**: Native support via `Foundation.ZipArchive` ✅

**Recommendation**: 
- Use command-line tools (`7z`, `unrar`) wrapped in Swift
- Consider making 7Z/RAR optional features

#### 6. FOMOD Parser
**Current**: XML parsing with complex conditional logic  
**Swift Equivalent**: `XMLParser` or `XMLCoder`

**Migration Effort**: Moderate

**Challenges**:
- XML parsing in Swift is more verbose than Python
- Conditional logic evaluation needs careful porting
- FOMOD spec compliance testing required

**Recommendation**: 
- Use `XMLCoder` for structured parsing
- Port condition evaluation logic carefully
- Maintain test suite for FOMOD compliance

#### 7. Nexus API Integration
**Current**: REST + GraphQL with caching  
**Swift Equivalent**: `URLSession` + custom GraphQL client

**Migration Effort**: Moderate

**Challenges**:
- GraphQL client libraries in Swift are less mature
- Caching layer needs redesign
- Rate limiting logic needs porting

**Recommendation**:
- Use `Apollo iOS` for GraphQL (mature, well-maintained)
- Or build simple GraphQL client with `URLSession`
- Implement file-based caching similar to current system

#### 8. Database Migrations
**Current**: Alembic  
**Swift Equivalent**: Custom migration system

**Migration Effort**: Moderate

**Challenges**:
- Need to build migration system from scratch
- Existing Alembic migrations need conversion
- Version tracking and rollback support

**Recommendation**:
- Use SwiftData migrations (if using SwiftData)
- Or build simple versioned migration system
- Maintain migration scripts in Swift

---

### 🔴 High Complexity (4-8 weeks each)

#### 9. Frida Integration
**Current**: Python Frida bindings (`frida>=16.0.0,<17`)  
**Swift Equivalent**: Frida Swift bindings or C interop

**Migration Effort**: High

**Challenges**:
- **No official Swift bindings** for Frida
- Frida is primarily Python/JavaScript focused
- GPU profiler depends heavily on Frida

**Options**:
1. **Use Frida Python via Process** (Easiest)
   - Keep Frida scripts in JavaScript
   - Launch Python subprocess to run Frida
   - Communicate via IPC (JSON, pipes)
   - **Pros**: Minimal changes, proven approach
   - **Cons**: External dependency, process overhead

2. **Use Frida C API via Swift C Interop** (Complex)
   - Frida has C API (`frida-core`)
   - Wrap in Swift via C interop
   - **Pros**: Native integration
   - **Cons**: Significant development effort, maintenance burden

3. **Replace Frida with Native macOS Tools** (Major Rewrite)
   - Use Instruments, DTrace, or Metal Performance Shaders
   - **Pros**: Native, no external dependencies
   - **Cons**: Complete rewrite of profiler, different capabilities

**Recommendation**: 
- **Option 1** (Python subprocess) for initial rewrite
- Consider Option 3 for long-term if profiler is critical

#### 10. Frontend Rewrite
**Current**: HTMX + Jinja2 templates (77 templates)  
**Swift Equivalent**: SwiftUI or AppKit

**Migration Effort**: High

**Challenges**:
- Complete UI rewrite required
- HTMX provides SPA-like experience without JavaScript
- Need to choose: SwiftUI (modern) vs AppKit (mature)

**Options**:
1. **SwiftUI** (Recommended for new app)
   - Modern, declarative UI
   - Better macOS integration
   - Requires macOS 11+
   - **Pros**: Native feel, modern APIs
   - **Cons**: Learning curve, some limitations

2. **AppKit** (More control)
   - Mature, full-featured
   - More complex but powerful
   - **Pros**: Complete control, mature ecosystem
   - **Cons**: More verbose, older patterns

3. **Hybrid Web UI** (Keep current approach)
   - Embed WebView with Swift backend
   - Keep HTMX templates
   - **Pros**: Minimal UI changes
   - **Cons**: Less native feel, WebView overhead

**Recommendation**:
- **SwiftUI** for native macOS app
- Port templates incrementally
- Consider keeping web UI for remote access option

#### 11. Async Architecture
**Current**: FastAPI async/await throughout  
**Swift Equivalent**: Swift async/await + Swift concurrency

**Migration Effort**: Moderate-High

**Challenges**:
- Python's async model differs from Swift's
- Need to redesign concurrent operations
- Actor model considerations

**Recommendation**:
- Swift's async/await is mature (since Swift 5.5)
- Use `async let` for parallel operations
- Consider `Actor` for shared mutable state

---

## Critical Dependencies Analysis

### Archive Extraction Libraries

| Format | Python Library | Swift Alternative | Status |
|--------|---------------|-------------------|--------|
| ZIP | `zipfile` (stdlib) | `Foundation.ZipArchive` | ✅ Native |
| 7Z | `py7zr` | Command-line `7z` or C interop | ⚠️ External |
| RAR | `rarfile` | Command-line `unrar` or C interop | ⚠️ External |

**Impact**: 7Z and RAR support requires external tools or significant C interop work.

### Frida Integration

| Component | Python | Swift | Migration Path |
|-----------|--------|-------|----------------|
| Frida bindings | `frida` package | None (use Python subprocess) | Keep Python wrapper |
| JavaScript scripts | Direct execution | Via Frida Python | No change needed |
| GPU profiler | Python + Frida | Swift + Python subprocess | Moderate rewrite |

**Impact**: GPU profiler needs architectural changes but can leverage existing Frida scripts.

---

## Architecture Options

### Option A: Pure Swift Native App (Recommended)

**Stack**:
- **UI**: SwiftUI
- **Backend**: Swift async/await
- **Database**: SwiftData or SQLite.swift
- **HTTP**: URLSession
- **Archive**: Native ZIP + command-line tools for 7Z/RAR
- **Frida**: Python subprocess wrapper

**Pros**:
- Native macOS app
- Better performance
- App Store distribution possible
- Modern Swift patterns

**Cons**:
- Complete rewrite required
- 7Z/RAR requires external tools
- Frida integration via subprocess

**Estimated Time**: 4-6 months

---

### Option B: Hybrid Swift + Python

**Stack**:
- **UI**: SwiftUI
- **Core Logic**: Swift
- **Archive Extraction**: Python subprocess (`py7zr`, `rarfile`)
- **Frida**: Python subprocess
- **Database**: Swift (SwiftData)

**Pros**:
- Leverage existing Python libraries
- Faster development
- Keep proven archive extraction

**Cons**:
- Python runtime dependency
- More complex deployment
- Two language maintenance

**Estimated Time**: 3-4 months

---

### Option C: Swift Backend + Web UI

**Stack**:
- **Backend**: Swift (Vapor or custom HTTP server)
- **Frontend**: Keep HTMX templates
- **Database**: SwiftData
- **Archive**: Hybrid approach

**Pros**:
- Minimal UI changes
- Keep web-based access
- Faster backend migration

**Cons**:
- Less native feel
- WebView overhead
- Still need UI updates

**Estimated Time**: 2-3 months

---

## Migration Strategy

### Phase 1: Foundation (Weeks 1-4)
- [ ] Set up Swift project structure
- [ ] Database models migration (SwiftData)
- [ ] Basic file operations
- [ ] Configuration management
- [ ] HTTP client setup

### Phase 2: Core Features (Weeks 5-10)
- [ ] Mod installation/uninstallation
- [ ] Archive extraction (ZIP native, 7Z/RAR via tools)
- [ ] Compatibility checking
- [ ] Database operations
- [ ] Basic API endpoints

### Phase 3: Advanced Features (Weeks 11-14)
- [ ] FOMOD parser
- [ ] Nexus API integration
- [ ] Dependency resolution
- [ ] Backup/rollback system
- [ ] Profile management

### Phase 4: UI & Integration (Weeks 15-18)
- [ ] SwiftUI interface
- [ ] Template migration
- [ ] Frida integration (Python wrapper)
- [ ] GPU profiler port
- [ ] Testing & polish

### Phase 5: Deployment (Weeks 19-20)
- [ ] App packaging
- [ ] Code signing
- [ ] Documentation
- [ ] Migration tools for existing data

---

## Risk Assessment

### High Risk Areas

1. **Archive Extraction**
   - **Risk**: 7Z/RAR support may be incomplete
   - **Mitigation**: Use command-line tools, make optional

2. **Frida Integration**
   - **Risk**: Profiler functionality may degrade
   - **Mitigation**: Keep Python wrapper, test thoroughly

3. **FOMOD Parser**
   - **Risk**: Edge cases in conditional logic
   - **Mitigation**: Comprehensive test suite, gradual migration

4. **UI Migration**
   - **Risk**: Feature parity issues
   - **Mitigation**: Incremental port, user testing

### Medium Risk Areas

1. **Database Migration**
   - **Risk**: Data loss during migration
   - **Mitigation**: Migration scripts, backup tools

2. **Nexus API Integration**
   - **Risk**: GraphQL client complexity
   - **Mitigation**: Use Apollo or simple client

3. **Async Architecture**
   - **Risk**: Concurrency bugs
   - **Mitigation**: Careful design, testing

---

## Benefits of Swift Rewrite

### ✅ Advantages

1. **Native macOS Integration**
   - Better file system access
   - Native security model
   - System integration (menu bar, notifications)

2. **Performance**
   - Faster startup time
   - Better memory management
   - Native async/await performance

3. **Distribution**
   - App Store distribution possible
   - Code signing simplified
   - Better update mechanism

4. **Developer Experience**
   - Strong typing
   - Better IDE support
   - Modern language features

5. **Maintenance**
   - Single language codebase (if pure Swift)
   - Better tooling
   - Easier onboarding

### ❌ Disadvantages

1. **Development Time**
   - 3-6 months of development
   - Learning curve for SwiftUI (if new)

2. **Dependencies**
   - 7Z/RAR require external tools
   - Frida integration complexity

3. **Ecosystem**
   - Less mature libraries than Python
   - Smaller community for mod manager use case

---

## Recommendations

### Recommended Approach: **Option A (Pure Swift) with Hybrid Archive Extraction**

1. **Use SwiftUI** for native macOS app
2. **Keep Python wrapper** for Frida (minimal change)
3. **Use command-line tools** for 7Z/RAR extraction
4. **Migrate incrementally** - start with core features
5. **Maintain compatibility** - support data migration from Python version

### Timeline Estimate

- **Minimum Viable Product**: 3 months
- **Feature Complete**: 5-6 months
- **Production Ready**: 6-8 months

### Success Criteria

- [ ] All core mod management features working
- [ ] Archive extraction (ZIP, 7Z, RAR) functional
- [ ] FOMOD installer support
- [ ] Nexus API integration
- [ ] GPU profiler functional (via Frida wrapper)
- [ ] Native macOS UI
- [ ] Data migration from Python version
- [ ] Comprehensive test coverage

---

## Conclusion

Rewriting the mod manager in Swift is **feasible but non-trivial**. The main challenges are:

1. **Archive extraction** (7Z/RAR) - requires external tools or significant C interop
2. **Frida integration** - best handled via Python subprocess wrapper
3. **UI rewrite** - complete SwiftUI implementation needed
4. **FOMOD parser** - careful porting required

The benefits (native macOS app, better performance, App Store distribution) justify the effort if:
- Long-term maintenance is a priority
- Native macOS integration is desired
- App Store distribution is a goal

**Recommendation**: Proceed with Swift rewrite if you have 4-6 months of development time and want a native macOS application. Consider the hybrid approach (Option B) if you need faster delivery and can accept Python runtime dependency.
