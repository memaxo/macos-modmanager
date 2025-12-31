// Installation JavaScript

function showInstallTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.install-tab').forEach(tab => {
        tab.style.display = 'none';
    });
    
    // Remove active class from all buttons
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
        btn.style.borderBottomColor = 'transparent';
        btn.style.color = 'var(--text-secondary)';
    });
    
    // Show selected tab
    const tab = document.getElementById(`tab-${tabName}`);
    if (tab) {
        tab.style.display = 'block';
    }
    
    // Activate button
    const button = event.target;
    button.classList.add('active');
    button.style.borderBottomColor = 'var(--accent-primary)';
    button.style.color = 'var(--accent-primary)';
}

function searchNexusMod() {
    const modIdInput = document.getElementById('nexus-mod-id');
    const urlInput = document.getElementById('nexus-url');
    const preview = document.getElementById('nexus-preview');
    
    let modId = modIdInput.value;
    
    // Extract mod ID from URL if provided
    if (!modId && urlInput.value) {
        const match = urlInput.value.match(/mods\/(\d+)/);
        if (match) {
            modId = match[1];
        }
    }
    
    if (!modId) {
        alert('Please enter a Nexus Mod ID or URL');
        return;
    }
    
    preview.innerHTML = '<div style="text-align: center; padding: var(--space-4); color: var(--text-secondary);">Loading mod information...</div>';
    
    // Fetch mod info from API
    fetch(`/api/mods/nexus/${modId}/info`)
        .then(response => response.json())
        .then(data => {
            preview.innerHTML = `
                <div class="card">
                    <h4 style="font-size: var(--text-lg); font-weight: var(--font-semibold); color: var(--text-primary); margin-bottom: var(--space-2);">
                        ${data.name}
                    </h4>
                    <p style="color: var(--text-secondary); margin-bottom: var(--space-4);">
                        by ${data.author || 'Unknown'}
                    </p>
                    <button 
                        class="btn btn-primary"
                        onclick="installFromNexus(${modId})">
                        Install Mod
                    </button>
                </div>
            `;
        })
        .catch(error => {
            preview.innerHTML = `<div style="color: var(--accent-error);">Error: ${error.message}</div>`;
        });
}

function installFromNexus(modId) {
    const checkCompatibility = document.querySelector('input[name="check_compatibility"]')?.checked || true;
    
    fetch(`/api/mods/nexus/${modId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            check_compatibility: checkCompatibility
        })
    })
    .then(response => response.json())
    .then(data => {
        showNotification('Mod installation started', 'success');
        // Poll for installation status
        pollInstallStatus(data.job_id);
    })
    .catch(error => {
        showNotification('Installation failed: ' + error.message, 'error');
    });
}

function importCollection() {
    const urlInput = document.getElementById('collection-url');
    const url = urlInput.value;
    
    if (!url) {
        alert('Please enter a collection URL');
        return;
    }
    
    // Extract collection ID from URL
    const match = url.match(/collections\/(\w+)/);
    if (!match) {
        alert('Invalid collection URL');
        return;
    }
    
    const collectionId = match[1];
    
    // Redirect to collection import page
    window.location.href = `/collections/import?url=${encodeURIComponent(url)}`;
}

function pollInstallStatus(jobId) {
    const queue = document.getElementById('install-queue');
    if (!queue) return;
    
    const interval = setInterval(() => {
        fetch(`/api/mods/install-status/${jobId}`)
            .then(response => response.json())
            .then(data => {
                if (data.status === 'completed') {
                    clearInterval(interval);
                    showNotification('Installation completed!', 'success');
                    setTimeout(() => {
                        window.location.href = '/mods';
                    }, 1500);
                } else if (data.status === 'failed') {
                    clearInterval(interval);
                    showNotification('Installation failed: ' + data.error, 'error');
                } else {
                    // Update progress
                    queue.innerHTML = `
                        <div class="card">
                            <div style="color: var(--text-primary); margin-bottom: var(--space-2);">
                                Installing mod...
                            </div>
                            <div class="progress-bar">
                                <div style="width: ${data.progress || 0}%; height: 100%; background: var(--accent-primary); border-radius: var(--radius-full);"></div>
                            </div>
                        </div>
                    `;
                }
            })
            .catch(error => {
                clearInterval(interval);
                showNotification('Error checking status: ' + error.message, 'error');
            });
    }, 1000);
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
