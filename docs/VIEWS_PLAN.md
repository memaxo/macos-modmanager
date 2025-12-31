# Mod Manager Web App - Views & UI Structure

## Navigation Structure

```
┌─────────────────────────────────────────────────────────┐
│  Header Navigation                                      │
│  [Logo] [Mods] [Collections] [Profiles] [Settings]    │
│  [Profile Switcher ▼] [Notifications 🔔] [Help ?]     │
└─────────────────────────────────────────────────────────┘
```

## Main Views

### 1. Dashboard View (`/`)
**Purpose**: Overview and quick access to key information

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  Dashboard Overview                                      │
├─────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ Total    │ │ Enabled  │ │ Conflicts│ │ Updates  │ │
│  │ Mods: 45 │ │ Mods: 38 │ │ Found: 2 │ │ Avail: 5 │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
├─────────────────────────────────────────────────────────┤
│  Quick Actions                                          │
│  [Install Mod] [Import Collection] [Check Updates]     │
├─────────────────────────────────────────────────────────┤
│  Recent Activity                                        │
│  • Mod "X" installed 2 hours ago                       │
│  • Conflict detected between Mod A and Mod B           │
│  • Update available for Mod Y                           │
├─────────────────────────────────────────────────────────┤
│  System Health                                          │
│  ✓ Game detected: Cyberpunk 2077                        │
│  ✓ redscript installed                                  │
│  ⚠ 2 mods have missing dependencies                    │
└─────────────────────────────────────────────────────────┘
```

**Components**:
- Stats cards (4-6 cards)
- Quick action buttons
- Activity feed (scrollable)
- System health indicators
- Disk usage chart (optional)

---

### 2. Mods Browser View (`/mods`)
**Purpose**: Browse, search, and manage installed mods

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  Mods Browser                                           │
├─────────────────────────────────────────────────────────┤
│  [Search...] [Filters ▼] [Sort ▼] [Grid/List] [Refresh]│
├─────────────────────────────────────────────────────────┤
│  Filters Sidebar          │  Mod List/Grid              │
│  ┌─────────────────────┐ │  ┌──────────────────────┐  │
│  │ Type                │ │  │ [Thumb] Mod Name     │  │
│  │ ☑ redscript         │ │  │ Author • v1.2.3      │  │
│  │ ☐ archive           │ │  │ [✓ Enabled] [⋮]     │  │
│  │                     │ │  └──────────────────────┘  │
│  │ Compatibility       │ │  ┌──────────────────────┐  │
│  │ ☑ Compatible        │ │  │ [Thumb] Mod Name     │  │
│  │ ☐ Incompatible      │ │  │ Author • v2.0.1      │  │
│  │                     │ │  │ [✗ Disabled] [⋮]    │  │
│  │ Status              │ │  └──────────────────────┘  │
│  │ ☑ Enabled           │ │  ...                        │
│  │ ☐ Disabled          │ │                             │
│  │                     │ │                             │
│  │ Tags                │ │                             │
│  │ [tag1] [tag2]       │ │                             │
│  └─────────────────────┘ │                             │
└─────────────────────────────────────────────────────────┘
```

**Components**:
- Search bar with autocomplete
- Filter sidebar (collapsible)
- Sort dropdown
- View toggle (grid/list)
- Mod cards/tiles
- Bulk selection checkbox
- Bulk actions toolbar

**Grid View**:
- Thumbnail image
- Mod name
- Author
- Version badge
- Enable/disable toggle
- Quick actions menu

**List View**:
- Compact row layout
- More details visible
- Sortable columns

---

### 3. Mod Details View (`/mods/{id}`)
**Purpose**: Detailed information about a specific mod

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  ← Back to Mods                    [Enable] [Uninstall]│
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐  Mod Name                            │
│  │              │  by Author                            │
│  │  Thumbnail   │  Version 1.2.3                       │
│  │              │  [Nexus Link] [Author Page]          │
│  └──────────────┘                                       │
├─────────────────────────────────────────────────────────┤
│  Tabs: [Overview] [Files] [Dependencies] [Conflicts]    │
│  [History] [Settings]                                   │
├─────────────────────────────────────────────────────────┤
│  Overview Tab                                           │
│  Description:                                            │
│  [Full mod description text...]                         │
│                                                          │
│  Compatibility: ✓ Compatible with macOS                 │
│  Type: redscript                                        │
│  Install Date: 2024-01-15                               │
│                                                          │
│  Dependency Tree:                                       │
│  └─ Requires: redscript (v0.5.29+)                      │
│                                                          │
│  Conflicts: None detected                               │
└─────────────────────────────────────────────────────────┘
```

**Components**:
- Mod header (thumbnail, name, author, version)
- Action buttons (enable/disable, uninstall, update)
- Tab navigation
- Description section
- Compatibility status
- Dependency tree visualization
- Conflict list
- File list
- Version history
- Related mods

---

### 4. Install Mod View (`/mods/install`)
**Purpose**: Install mods from file or Nexus Mods

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  Install Mod                                            │
├─────────────────────────────────────────────────────────┤
│  Tabs: [Upload File] [From Nexus] [From Collection]     │
├─────────────────────────────────────────────────────────┤
│  Upload File Tab                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │                                                   │  │
│  │        Drag and drop mod file here               │  │
│  │        or click to browse                        │  │
│  │                                                   │  │
│  │        Supports: .zip, .7z, .rar                 │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  Options:                                               │
│  ☑ Check compatibility before install                   │
│  ☐ Create backup before install                        │
│                                                          │
│  [Cancel] [Install]                                     │
├─────────────────────────────────────────────────────────┤
│  From Nexus Tab                                         │
│  Nexus Mod ID: [________] [Search]                     │
│                                                          │
│  Or paste Nexus URL:                                    │
│  [https://nexusmods.com/...] [Import]                   │
│                                                          │
│  Mod Preview:                                           │
│  [Thumbnail] Mod Name                                   │
│  by Author • Version                                    │
│  [Select File ▼] [Install]                             │
└─────────────────────────────────────────────────────────┘
```

**Components**:
- Drag-and-drop zone
- File upload input
- Nexus Mod ID input
- URL paste input
- Mod preview card
- Installation options
- Progress indicator
- Installation queue

---

### 5. Load Order Manager View (`/mods/load-order`)
**Purpose**: Manage mod load order and priorities

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  Load Order Manager                                     │
├─────────────────────────────────────────────────────────┤
│  Profile: [Default Profile ▼] [Save] [Reset]          │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────┐  │
│  │ Priority │ Mod Name        │ Conflicts │ Actions │  │
│  ├──────────┼─────────────────┼───────────┼─────────┤  │
│  │    1     │ Mod A           │           │ [⋮]     │  │
│  │    2     │ Mod B           │ ⚠ Mod A   │ [⋮]     │  │
│  │    3     │ Mod C           │           │ [⋮]     │  │
│  │    4     │ Mod D           │ ⚠ Mod C   │ [⋮]     │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  [Auto-sort by Dependencies] [Save Order]              │
└─────────────────────────────────────────────────────────┘
```

**Components**:
- Profile selector
- Sortable list (drag handles)
- Priority numbers
- Conflict indicators
- Auto-sort button
- Save/Reset buttons
- Visual conflict warnings

---

### 6. Conflict Resolution View (`/conflicts`)
**Purpose**: View and resolve mod conflicts

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  Conflict Resolution                                    │
├─────────────────────────────────────────────────────────┤
│  Filter: [All] [Critical] [Warning] [Info] [Resolved]  │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────┐  │
│  │ Conflict #1: file_overwrite                      │  │
│  │ Severity: ⚠ Warning                              │  │
│  │                                                   │  │
│  │ File: r6/scripts/somefile.reds                   │  │
│  │                                                   │  │
│  │ Mod A (Priority 2)        │ Mod B (Priority 3)   │  │
│  │ ┌─────────────────────┐  │ ┌──────────────────┐ │  │
│  │ │ function test() {   │  │ │ function test() { │ │  │
│  │ │   return 1;        │  │ │   return 2;      │ │  │
│  │ │ }                   │  │ │ }                 │ │  │
│  │ └─────────────────────┘  │ └──────────────────┘ │  │
│  │                                                   │  │
│  │ Resolution:                                       │  │
│  │ ○ Use Mod A (current)                           │  │
│  │ ○ Use Mod B                                      │  │
│  │ ○ Create merge patch                             │  │
│  │ ○ Disable Mod B                                  │  │
│  │                                                   │  │
│  │ [Resolve] [Skip]                                 │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**Components**:
- Conflict list with filters
- Side-by-side file comparison
- Diff viewer
- Resolution options
- Conflict severity badges
- Resolution history

---

### 7. Dependency Manager View (`/dependencies`)
**Purpose**: Manage and resolve mod dependencies

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  Dependency Manager                                     │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────┐  │
│  │ Dependency Tree                                  │  │
│  │                                                   │  │
│  │ Mod A                                             │  │
│  │ ├─ ✓ redscript (v0.5.29+)                        │  │
│  │ └─ ✗ ArchiveXL (missing) [Install]               │  │
│  │                                                   │  │
│  │ Mod B                                             │  │
│  │ ├─ ✓ redscript (v0.5.29+)                        │  │
│  │ └─ ⚠ Codeware (incompatible with macOS)          │  │
│  │                                                   │  │
│  │ Mod C                                             │  │
│  │ └─ ✓ redscript (v0.5.29+)                        │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  Summary:                                               │
│  • 2 missing dependencies                              │
│  • 1 incompatible dependency                           │
│                                                          │
│  [Install Missing] [View All]                          │
└─────────────────────────────────────────────────────────┘
```

**Components**:
- Dependency tree visualization
- Status indicators (✓/✗/⚠)
- Install buttons for missing deps
- Incompatibility warnings
- Summary statistics
- Graph view toggle

---

### 8. Collections Browser View (`/collections`)
**Purpose**: Browse and manage mod collections

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  Collections                                            │
├─────────────────────────────────────────────────────────┤
│  [Search...] [My Collections] [Browse Nexus] [Create] │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────┐  │
│  │ [Thumb] Collection Name                          │  │
│  │ by Author • 45 mods • Updated 2 days ago        │  │
│  │ [Preview] [Install]                              │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │ [Thumb] Collection Name                          │  │
│  │ by Author • 32 mods • Updated 1 week ago         │  │
│  │ [Preview] [Install]                              │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**Components**:
- Collection grid/list
- Collection cards
- Search and filter
- Import from URL
- Create collection button
- Collection preview modal

---

### 9. Collection Details View (`/collections/{id}`)
**Purpose**: View collection details and install

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  ← Back to Collections                                  │
├─────────────────────────────────────────────────────────┤
│  Collection Name                                        │
│  by Author • 45 mods • Version 1.2.3                   │
│  [Nexus Link]                                           │
│                                                          │
│  Description:                                           │
│  [Full collection description...]                      │
│                                                          │
│  Compatibility Check:                                   │
│  ✓ 43 compatible                                        │
│  ⚠ 2 incompatible (ArchiveXL required)                │
│                                                          │
│  Mods in Collection:                                    │
│  ┌──────────────────────────────────────────────────┐  │
│  │ ☑ Mod A (required)                              │  │
│  │ ☑ Mod B (required)                              │  │
│  │ ☐ Mod C (optional)                              │  │
│  │ ...                                              │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  [Install All] [Install Selected] [Cancel]             │
└─────────────────────────────────────────────────────────┘
```

**Components**:
- Collection header
- Description
- Compatibility summary
- Mod list with checkboxes
- Required/optional indicators
- Install options
- Progress indicator

---

### 10. Profiles Manager View (`/profiles`)
**Purpose**: Manage mod profiles

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  Mod Profiles                                           │
├─────────────────────────────────────────────────────────┤
│  [Create New Profile]                                   │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────┐  │
│  │ Default Profile                    [Default]     │  │
│  │ 38 mods enabled • Last used: 2 hours ago        │  │
│  │ [Activate] [Edit] [Duplicate] [Delete]          │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Combat Build                      [Edit]         │  │
│  │ 25 mods enabled • Last used: 1 day ago           │  │
│  │ [Activate] [Edit] [Duplicate] [Delete]          │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**Components**:
- Profile cards
- Create profile button
- Profile actions (activate, edit, duplicate, delete)
- Profile comparison view
- Profile templates

---

### 11. Profile Editor View (`/profiles/{id}/edit`)
**Purpose**: Edit profile configuration

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  Edit Profile: Combat Build                             │
├─────────────────────────────────────────────────────────┤
│  Profile Name: [Combat Build____________]               │
│  Description: [_________________________]               │
│                                                          │
│  Mods in Profile:                                       │
│  ┌──────────────────────────────────────────────────┐  │
│  │ ☑ Mod A                    [Remove]            │  │
│  │ ☐ Mod B                    [Remove]            │  │
│  │ ☑ Mod C                    [Remove]            │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  [Add Mods] [Set Load Order] [Save] [Cancel]           │
└─────────────────────────────────────────────────────────┘
```

**Components**:
- Profile name/description inputs
- Mod list with enable/disable
- Add mods button
- Load order link
- Save/Cancel buttons

---

### 12. Updates View (`/updates`)
**Purpose**: Check and manage mod updates

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  Update Manager                                         │
├─────────────────────────────────────────────────────────┤
│  [Check for Updates] Last checked: 2 hours ago         │
├─────────────────────────────────────────────────────────┤
│  Updates Available (5)                                  │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Mod A                                            │  │
│  │ Current: v1.2.3 → Available: v1.3.0            │  │
│  │ Changelog: [View] [Update] [Skip]                │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Mod B                                            │  │
│  │ Current: v2.0.1 → Available: v2.1.0            │  │
│  │ Changelog: [View] [Update] [Skip]                │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  [Update All] [Update Selected]                        │
└─────────────────────────────────────────────────────────┘
```

**Components**:
- Check updates button
- Update list
- Version comparison
- Changelog preview
- Update/Skip buttons
- Batch update options

---

### 13. Settings View (`/settings`)
**Purpose**: Application settings and preferences

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  Settings                                               │
├─────────────────────────────────────────────────────────┤
│  Tabs: [General] [Game] [Compatibility] [Notifications] │
│  [API] [Appearance]                                     │
├─────────────────────────────────────────────────────────┤
│  General Tab                                            │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Auto-check for updates:        [Toggle]          │  │
│  │ Backup before install:         [Toggle]          │  │
│  │ Auto-remove quarantine:       [Toggle]          │  │
│  │ Default mod path:              [r6/scripts]      │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  Game Tab                                                │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Game Installation Path:                          │  │
│  │ [/path/to/game] [Browse] [Auto-detect]           │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  Compatibility Tab                                       │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Strict compatibility mode:    [Toggle]          │  │
│  │ Allow override warnings:      [Toggle]          │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  [Save] [Reset to Defaults]                            │
└─────────────────────────────────────────────────────────┘
```

**Components**:
- Tab navigation
- Toggle switches
- Input fields
- File path browsers
- Save/Reset buttons
- Theme selector

---

### 14. Activity Log View (`/activity`)
**Purpose**: View application activity history

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  Activity Log                                           │
├─────────────────────────────────────────────────────────┤
│  Filter: [All] [Install] [Uninstall] [Update] [Error]  │
│  Search: [________] [Export]                            │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────┐  │
│  │ 2024-01-15 14:30:22                              │  │
│  │ ✓ Mod "X" installed successfully                 │  │
│  │ [Details] [Undo]                                 │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 2024-01-15 13:15:10                              │  │
│  │ ⚠ Conflict detected: Mod A ↔ Mod B              │  │
│  │ [View] [Resolve]                                 │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 2024-01-15 12:00:05                              │  │
│  │ ✗ Mod "Y" installation failed: Incompatible     │  │
│  │ [Details]                                        │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**Components**:
- Filter buttons
- Search bar
- Timeline view
- Activity entries
- Action buttons (details, undo)
- Export button

---

### 15. File Manager View (`/mods/{id}/files`)
**Purpose**: Browse mod files

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  ← Back to Mod Details                                  │
├─────────────────────────────────────────────────────────┤
│  Files in Mod: Mod Name                                │
├─────────────────────────────────────────────────────────┤
│  Search: [________]                                     │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 📁 r6/                                           │  │
│  │   📁 scripts/                                    │  │
│  │     📄 mod.reds (2.3 KB)                        │  │
│  │     📄 utils.reds (1.1 KB)                       │  │
│  │   📄 readme.txt (0.5 KB)                         │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  Selected: mod.reds                                     │
│  Size: 2.3 KB                                           │
│  Path: r6/scripts/mod.reds                             │
│  [View Contents] [Delete]                              │
└─────────────────────────────────────────────────────────┘
```

**Components**:
- File tree browser
- File details panel
- Search
- View file contents modal
- Delete file button

---

### 16. Analytics View (`/analytics`)
**Purpose**: Performance and usage statistics

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  Analytics & Performance                                │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────┐  │
│  │ Disk Usage                                       │  │
│  │ [Pie Chart]                                      │  │
│  │ Mods: 2.3 GB                                     │  │
│  │ Backups: 500 MB                                  │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Mod Size Breakdown                               │  │
│  │ [Bar Chart]                                      │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  Statistics:                                             │
│  • Total mods: 45                                       │
│  • Enabled: 38                                          │
│  • Average install time: 12s                            │
│  • Compatibility rate: 95%                              │
└─────────────────────────────────────────────────────────┘
```

**Components**:
- Charts (pie, bar, line)
- Statistics cards
- Usage metrics
- Performance graphs

---

### 17. Help View (`/help`)
**Purpose**: Documentation and help

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  Help & Documentation                                    │
├─────────────────────────────────────────────────────────┤
│  [Search help...]                                       │
├─────────────────────────────────────────────────────────┤
│  Quick Links:                                           │
│  • Getting Started                                      │
│  • Installing Mods                                     │
│  • Managing Conflicts                                   │
│  • Troubleshooting                                      │
│                                                          │
│  FAQ:                                                   │
│  Q: How do I install a mod?                             │
│  A: [Answer...]                                         │
│                                                          │
│  Keyboard Shortcuts:                                    │
│  Ctrl+I - Install mod                                   │
│  Ctrl+S - Search                                        │
│  ...                                                    │
└─────────────────────────────────────────────────────────┘
```

**Components**:
- Search bar
- FAQ section
- Tutorial links
- Keyboard shortcuts
- Troubleshooting wizard

---

## Component Library

### Reusable Components

1. **ModCard** - Display mod in grid/list
2. **ModToggle** - Enable/disable switch
3. **ConflictBadge** - Conflict indicator
4. **DependencyTree** - Visual dependency graph
5. **FileDiffViewer** - Side-by-side comparison
6. **ProgressBar** - Installation progress
7. **NotificationToast** - Toast notifications
8. **FilterSidebar** - Filter panel
9. **SearchBar** - Search with autocomplete
10. **StatsCard** - Dashboard stat card
11. **ActivityEntry** - Activity log item
12. **ProfileCard** - Profile display card
13. **CollectionCard** - Collection display card
14. **LoadOrderItem** - Sortable load order row
15. **SettingsToggle** - Settings toggle switch

## User Flows

### Flow 1: Install Mod from File
1. Dashboard → Click "Install Mod"
2. Install View → Drag file or browse
3. Compatibility check → Show results
4. Confirm → Install
5. Progress → Success notification
6. Redirect → Mod Details

### Flow 2: Resolve Conflict
1. Dashboard → See conflict notification
2. Conflicts View → View conflict details
3. Compare files → Choose resolution
4. Apply resolution → Save
5. Update → Conflict resolved

### Flow 3: Import Collection
1. Collections View → Click "Import"
2. Paste URL → Parse collection
3. Compatibility check → Show results
4. Select mods → Install
5. Progress → Complete
6. Redirect → Collection Details

### Flow 4: Create Profile
1. Profiles View → Click "Create"
2. Profile Editor → Name and description
3. Add mods → Select from list
4. Set load order → Drag to order
5. Save → Profile created
6. Activate → Mods enabled/disabled

## Responsive Breakpoints

- **Desktop**: > 1024px - Full layout
- **Tablet**: 768px - 1024px - Collapsible sidebar
- **Mobile**: < 768px - Stacked layout, bottom nav

## Navigation Structure

```
Header (always visible)
├── Logo (link to dashboard)
├── Mods (dropdown: Browse, Install, Load Order)
├── Collections (link to collections)
├── Profiles (dropdown: Manage, Create)
├── Settings (link to settings)
└── Right side:
    ├── Profile Switcher
    ├── Notifications
    └── Help

Sidebar (collapsible on mobile)
├── Dashboard
├── Mods
│   ├── All Mods
│   ├── Enabled
│   ├── Disabled
│   └── By Category
├── Collections
├── Profiles
├── Conflicts
├── Dependencies
├── Updates
├── Activity
└── Settings
```
