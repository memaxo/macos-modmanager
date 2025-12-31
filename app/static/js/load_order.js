// Load Order JavaScript

let sortableInstance = null;

document.addEventListener('DOMContentLoaded', function() {
    initializeSortable();
});

function initializeSortable() {
    const list = document.getElementById('load-order-list');
    if (!list) return;
    
    sortableInstance = new Sortable(list, {
        handle: '.drag-handle',
        animation: 150,
        onEnd: function() {
            updatePriorityNumbers();
        }
    });
}

function updatePriorityNumbers() {
    const items = document.querySelectorAll('.load-order-item');
    items.forEach((item, index) => {
        const priority = item.querySelector('.priority-number');
        if (priority) {
            priority.textContent = index + 1;
        }
    });
}

function autoSort() {
    fetch('/api/mods/load-order/auto-sort', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        htmx.trigger('#load-order-list', 'refresh');
    })
    .catch(error => {
        showNotification('Error: ' + error.message, 'error');
    });
}

function saveLoadOrder() {
    const items = document.querySelectorAll('.load-order-item');
    const order = Array.from(items).map((item, index) => ({
        mod_id: parseInt(item.dataset.modId),
        order: index + 1
    }));
    
    fetch('/api/mods/load-order', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ order: order })
    })
    .then(response => response.json())
    .then(data => {
        showNotification('Load order saved', 'success');
    })
    .catch(error => {
        showNotification('Error: ' + error.message, 'error');
    });
}

function loadProfileLoadOrder() {
    const profileId = document.getElementById('profile-select').value;
    if (profileId) {
        htmx.ajax('GET', `/api/mods/load-order?profile_id=${profileId}`, {
            target: '#load-order-list',
            swap: 'innerHTML'
        });
    } else {
        htmx.trigger('#load-order-list', 'refresh');
    }
}

function showNotification(message, type) {
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
