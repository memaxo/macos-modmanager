// Mod Browser JavaScript

let currentView = localStorage.getItem('mod-view') || 'grid';
let selectedMods = new Set();

function setView(view) {
    currentView = view;
    localStorage.setItem('mod-view', view);
    
    // Update button states
    document.getElementById('view-grid').classList.toggle('active', view === 'grid');
    document.getElementById('view-list').classList.toggle('active', view === 'list');
    
    // Update mod list view
    const modList = document.getElementById('mod-list');
    if (modList) {
        modList.setAttribute('data-view', view);
        // Trigger HTMX refresh with view parameter
        htmx.trigger(modList, 'refresh');
    }
}

function updateFilter(filterType, checkbox) {
    const filterInput = document.getElementById(`filter-${filterType}`);
    if (!filterInput) return;
    
    const checkboxes = document.querySelectorAll(`input[name^="${filterType}-"]:checked`);
    const values = Array.from(checkboxes).map(cb => cb.value);
    filterInput.value = values.join(',');
    
    // Trigger HTMX refresh
    htmx.trigger('#mod-list', 'refresh');
}

function clearFilters() {
    document.querySelectorAll('#filter-sidebar input[type="checkbox"]').forEach(cb => {
        cb.checked = false;
    });
    document.getElementById('filter-type').value = '';
    document.getElementById('filter-status').value = '';
    document.getElementById('filter-compatibility').value = '';
    htmx.trigger('#mod-list', 'refresh');
}

function updateBulkSelection() {
    const checkboxes = document.querySelectorAll('.mod-checkbox:checked');
    selectedMods = new Set(Array.from(checkboxes).map(cb => cb.value));
    
    const bulkActions = document.getElementById('bulk-actions');
    const selectedCount = document.getElementById('selected-count');
    
    if (selectedMods.size > 0) {
        bulkActions.style.display = 'block';
        selectedCount.textContent = `${selectedMods.size} mod${selectedMods.size > 1 ? 's' : ''} selected`;
    } else {
        bulkActions.style.display = 'none';
    }
}

function bulkAction(action) {
    if (selectedMods.size === 0) return;
    
    const modIds = Array.from(selectedMods).map(Number);
    
    if (action === 'delete') {
        if (!confirm(`Are you sure you want to delete ${modIds.length} mod(s)?`)) {
            return;
        }
    }
    
    // Send bulk action request
    fetch(`/api/mods/bulk`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            action: action,
            mod_ids: modIds
        })
    })
    .then(async response => {
        const text = await response.text();
        // Check if response is HTML (toast) or JSON
        if (text.trim().startsWith('<')) {
            const notificationArea = document.getElementById('notification-area');
            if (notificationArea) {
                notificationArea.insertAdjacentHTML('beforeend', text);
            }
        }
        
        // Refresh mod list
        htmx.trigger('#mod-list', 'refresh');
        
        // Clear selection
        selectedMods.clear();
        document.querySelectorAll('.mod-checkbox').forEach(cb => cb.checked = false);
        updateBulkSelection();
    })
    .catch(error => {
        showNotification(`Error: ${error.message}`, 'error');
    });
}

function showNotification(message, type = 'success') {
    const notificationArea = document.getElementById('notification-area');
    if (!notificationArea) return;
    
    const notification = document.createElement('div');
    notification.className = `toast toast-${type}`;
    notification.textContent = message;
    notification.style.cssText = `
        background: var(--bg-secondary);
        border: 1px solid var(--border-primary);
        border-radius: var(--radius-lg);
        padding: var(--space-3);
        margin-bottom: var(--space-2);
        box-shadow: var(--shadow-lg);
        animation: slideUp 0.3s ease;
    `;
    
    notificationArea.appendChild(notification);
    
    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Initialize view on load
document.addEventListener('DOMContentLoaded', function() {
    setView(currentView);
});
