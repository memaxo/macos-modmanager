# Design System - Grey & Dark Slate Blue UI

## Design Principles

1. **Professional Elegance** - Refined, polished desktop-inspired interface
2. **Slate & Grey Aesthetic** - Muted grey backgrounds with Dark Slate Blue accents
3. **Clarity** - Clear hierarchy and visual feedback
4. **Consistency** - Unified patterns across all views
5. **Accessibility** - High contrast, readable text
6. **Efficiency** - Quick access to common actions

## Color Palette (Slate & Grey)

### Primary Colors
```css
--bg-primary: #121212;        /* Deep Grey base */
--bg-secondary: #1e1e1e;      /* Apple-style dark grey for cards */
--bg-tertiary: #252525;       /* Elevated surfaces */
--bg-hover: #2c2c2c;          /* Hover states */
--bg-active: #333333;         /* Active/pressed states */

--border-primary: #333333;    /* Subtle borders */
--border-secondary: #444444;  /* Active borders */
--border-accent: #483d8b;     /* Dark Slate Blue borders */
```

### Accent Colors
```css
--accent-primary: #483d8b;    /* Dark Slate Blue - Primary actions */
--accent-hover: #5d54a4;      /* Lighter slate on hover */
--accent-active: #3a3270;     /* Darker slate state */

--accent-success: #81b88b;   /* Muted Green - Success states */
--accent-warning: #e2b85b;   /* Muted Yellow - Warnings */
--accent-error: #c35a5a;     /* Muted Red - Errors */
--accent-info: #483d8b;      /* Dark Slate Blue - Info */
```

### Text Colors
```css
--text-primary: #e0e0e0;      /* Primary text */
--text-secondary: #a0a0a0;    /* Secondary text */
--text-tertiary: #666666;     /* Muted text */
--text-disabled: #444444;     /* Disabled text */
```

### Status Colors
```css
--status-enabled: #81b88b;    /* Enabled mods (muted green) */
--status-disabled: #666666;   /* Disabled mods */
--status-conflict: #c35a5a;   /* Conflicts (muted red) */
--status-warning: #e2b85b;    /* Warnings (muted yellow) */
--status-info: #483d8b;       /* Information (slate blue) */
```

## Typography

### Font Stack
```css
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 
             'Helvetica Neue', Arial, sans-serif;
```

### Font Sizes
```css
--text-xs: 0.75rem;      /* 12px - Labels, captions */
--text-sm: 0.875rem;     /* 14px - Secondary text */
--text-base: 1rem;       /* 16px - Body text */
--text-lg: 1.125rem;     /* 18px - Subheadings */
--text-xl: 1.25rem;      /* 20px - Headings */
--text-2xl: 1.5rem;      /* 24px - Page titles */
--text-3xl: 1.875rem;    /* 30px - Hero text */
```

### Font Weights
```css
--font-light: 300;
--font-normal: 400;
--font-medium: 500;
--font-semibold: 600;
--font-bold: 700;
```

### Line Heights
```css
--leading-tight: 1.25;
--leading-normal: 1.5;
--leading-relaxed: 1.75;
```

## Spacing System

### Base Unit: 4px
```css
--space-1: 0.25rem;   /* 4px */
--space-2: 0.5rem;    /* 8px */
--space-3: 0.75rem;   /* 12px */
--space-4: 1rem;      /* 16px */
--space-5: 1.25rem;   /* 20px */
--space-6: 1.5rem;    /* 24px */
--space-8: 2rem;      /* 32px */
--space-10: 2.5rem;   /* 40px */
--space-12: 3rem;     /* 48px */
--space-16: 4rem;     /* 64px */
```

## Border Radius (Desktop-inspired)

```css
--radius-sm: 0.375rem;   /* 6px - Small elements */
--radius-md: 0.5rem;     /* 8px - Buttons, inputs */
--radius-lg: 0.75rem;    /* 12px - Cards */
--radius-xl: 1rem;       /* 16px - Modals */
--radius-2xl: 1.25rem;   /* 20px - Large cards */
--radius-full: 9999px;   /* Pills, badges */
```

## Shadows (Desktop-inspired depth)

```css
--shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.4), 0 1px 3px 0 rgba(0, 0, 0, 0.3);
--shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.5), 0 2px 4px -1px rgba(0, 0, 0, 0.4);
--shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.6), 0 4px 6px -2px rgba(0, 0, 0, 0.5);
--shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.7), 0 10px 10px -5px rgba(0, 0, 0, 0.6);
--shadow-2xl: 0 25px 50px -12px rgba(0, 0, 0, 0.8);
--shadow-inner: inset 0 2px 4px 0 rgba(0, 0, 0, 0.4);
--shadow-glow: 0 0 20px rgba(72, 61, 139, 0.3); /* Dark Slate Blue glow for focus */
```

## Component Styles

### Buttons

**Primary Button**
```css
background: var(--accent-primary);
color: var(--bg-primary);
padding: 0.625rem 1.25rem;
border-radius: var(--radius-md);
font-weight: var(--font-medium);
transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
box-shadow: var(--shadow-sm);

:hover {
  background: var(--accent-hover);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

:active {
  background: var(--accent-active);
  transform: translateY(0);
  box-shadow: var(--shadow-sm);
}
```

**Secondary Button**
```css
background: transparent;
color: var(--text-secondary);
border: 1px solid var(--border-primary);
padding: 0.625rem 1.25rem;
border-radius: var(--radius-md);

:hover {
  background: var(--bg-hover);
  border-color: var(--border-secondary);
  color: var(--text-primary);
}
```

**Ghost Button**
```css
background: transparent;
color: var(--text-secondary);
padding: 0.625rem 1.25rem;
border-radius: var(--radius-md);

:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
```

**Danger Button**
```css
background: var(--accent-error);
color: var(--text-primary);

:hover {
  background: #e63950;
}
```

### Cards (Desktop-inspired)

```css
background: var(--bg-secondary);
border: 1px solid var(--border-primary);
border-radius: var(--radius-lg);
padding: var(--space-6);
transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
box-shadow: var(--shadow-sm);
backdrop-filter: blur(10px);

:hover {
  border-color: var(--border-secondary);
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
  background: var(--bg-tertiary);
}
```

### Inputs (Desktop-inspired)

```css
background: var(--bg-tertiary);
border: 1px solid var(--border-primary);
border-radius: var(--radius-md);
padding: 0.625rem 0.875rem;
color: var(--text-primary);
font-size: var(--text-base);
transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
box-shadow: var(--shadow-inner);

:focus {
  outline: none;
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 3px rgba(72, 61, 139, 0.15), var(--shadow-inner);
  background: var(--bg-hover);
}

::placeholder {
  color: var(--text-tertiary);
}
```

### Toggles/Switches

```css
/* Enabled */
background: var(--accent-success);
width: 2.5rem;
height: 1.5rem;
border-radius: var(--radius-full);

/* Disabled */
background: var(--bg-tertiary);
```

### Badges (Desktop-inspired)

```css
display: inline-flex;
align-items: center;
padding: 0.25rem 0.75rem;
border-radius: var(--radius-full);
font-size: var(--text-xs);
font-weight: var(--font-medium);
backdrop-filter: blur(10px);
border: 1px solid transparent;

/* Status variants */
.success { 
  background: rgba(173, 219, 103, 0.15); 
  color: var(--accent-success);
  border-color: rgba(173, 219, 103, 0.2);
}
.warning { 
  background: rgba(255, 203, 107, 0.15); 
  color: var(--accent-warning);
  border-color: rgba(255, 203, 107, 0.2);
}
.error { 
  background: rgba(255, 88, 116, 0.15); 
  color: var(--accent-error);
  border-color: rgba(255, 88, 116, 0.2);
}
.info { 
  background: rgba(72, 61, 139, 0.15); 
  color: var(--accent-info);
  border-color: rgba(72, 61, 139, 0.2);
}
```

### Modals (Desktop-inspired)

```css
background: var(--bg-secondary);
border: 1px solid var(--border-primary);
border-radius: var(--radius-xl);
box-shadow: var(--shadow-2xl);
padding: var(--space-6);
max-width: 32rem;
backdrop-filter: blur(20px);
border: 1px solid rgba(72, 61, 139, 0.1);
```

### Navigation

**Header**
```css
background: var(--bg-primary);
border-bottom: 1px solid var(--border-primary);
height: 4rem;
padding: 0 var(--space-6);
backdrop-filter: blur(20px);
```

**Sidebar**
```css
background: var(--bg-secondary);
border-right: 1px solid var(--border-primary);
width: 16rem;
padding: var(--space-4);
```

**Nav Item**
```css
padding: 0.5rem 0.75rem;
border-radius: var(--radius-md);
color: var(--text-secondary);
transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
position: relative;

:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.active {
  background: var(--bg-tertiary);
  color: var(--accent-primary);
}

.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 60%;
  background: var(--accent-primary);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}
```

## Layout

### Container
```css
max-width: 1280px;
margin: 0 auto;
padding: 0 var(--space-6);
```

### Grid System
```css
/* 12-column grid */
grid-template-columns: repeat(12, minmax(0, 1fr));
gap: var(--space-6);
```

## Animations

### Transitions
```css
--transition-fast: 0.15s cubic-bezier(0.4, 0, 0.2, 1);
--transition-base: 0.2s cubic-bezier(0.4, 0, 0.2, 1);
--transition-slow: 0.3s cubic-bezier(0.4, 0, 0.2, 1);
```

### Keyframes
```css
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from { 
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
```

## Icons

- **Size**: 16px, 20px, 24px
- **Style**: Outline (default), filled (active)
- **Library**: Heroicons or similar
- **Color**: Inherit text color

## Focus States

```css
:focus-visible {
  outline: 2px solid var(--accent-primary);
  outline-offset: 2px;
  border-radius: var(--radius-md);
}
```

## Scrollbar

```css
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: var(--bg-primary);
}

::-webkit-scrollbar-thumb {
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
}

::-webkit-scrollbar-thumb:hover {
  background: var(--border-secondary);
}
```

## Z-Index Scale

```css
--z-dropdown: 1000;
--z-sticky: 1020;
--z-fixed: 1030;
--z-modal-backdrop: 1040;
--z-modal: 1050;
--z-popover: 1060;
--z-tooltip: 1070;
```

## Responsive Breakpoints

```css
--breakpoint-sm: 640px;
--breakpoint-md: 768px;
--breakpoint-lg: 1024px;
--breakpoint-xl: 1280px;
--breakpoint-2xl: 1536px;
```

## Example Component: Mod Card

```html
<div class="mod-card">
  <div class="mod-card-thumbnail">
    <img src="..." alt="Mod thumbnail" />
  </div>
  <div class="mod-card-content">
    <h3 class="mod-card-title">Mod Name</h3>
    <p class="mod-card-author">by Author</p>
    <div class="mod-card-meta">
      <span class="badge success">v1.2.3</span>
      <span class="badge info">redscript</span>
    </div>
    <div class="mod-card-actions">
      <toggle-switch enabled />
      <button class="btn-ghost">⋮</button>
    </div>
  </div>
</div>
```

```css
.mod-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  transition: all var(--transition-slow);
  box-shadow: var(--shadow-sm);
  backdrop-filter: blur(10px);
}

.mod-card:hover {
  border-color: var(--border-secondary);
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
  background: var(--bg-tertiary);
}

.mod-card-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--space-1);
}

.mod-card-author {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--space-3);
}
```

## Example Component: Stats Card

```css
.stats-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  text-align: center;
  box-shadow: var(--shadow-sm);
  backdrop-filter: blur(10px);
}

.stats-card-value {
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  color: var(--accent-primary);
  margin-bottom: var(--space-2);
}

.stats-card-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
```

## Accessibility

- **Contrast Ratio**: Minimum 4.5:1 for text
- **Focus Indicators**: Visible on all interactive elements
- **Keyboard Navigation**: Full keyboard support
- **Screen Readers**: Proper ARIA labels
- **Motion**: Respect `prefers-reduced-motion`

## Implementation Notes

- Use CSS custom properties for theming
- Desktop-inspired rounded corners (6px-20px)
- Layered shadows for depth
- Backdrop blur for glassmorphism effect
- Smooth cubic-bezier transitions
- Dark Slate Blue accent color with grey backgrounds
- Professional, refined aesthetic
