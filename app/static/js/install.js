// Installation JavaScript

function showInstallTab(tabName, evt) {
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
    
    // Activate button - use evt parameter if available
    let button;
    if (evt && evt.target) {
        button = evt.target.closest('.tab-button') || evt.target;
    } else if (typeof event !== 'undefined' && event.target) {
        // Fallback to global event if evt not provided
        button = event.target.closest('.tab-button') || event.target;
    } else {
        // Fallback: find button by checking which one should be active
        button = document.querySelector(`.tab-button[onclick*="${tabName}"]`);
    }
    
    if (button) {
        button.classList.add('active');
        button.style.borderBottomColor = 'var(--accent-primary)';
        button.style.color = 'var(--accent-primary)';
    }
}

function searchNexusMod() {
    const modIdInput = document.getElementById('nexus-mod-id');
    const urlInput = document.getElementById('nexus-url');
    const preview = document.getElementById('nexus-preview');
    
    if (!preview) {
        console.error('Nexus preview element not found');
        return;
    }
    
    let modId = modIdInput?.value;
    
    // Extract mod ID from URL if provided
    if (!modId && urlInput?.value) {
        const match = urlInput.value.match(/mods\/(\d+)/);
        if (match) {
            modId = match[1];
        }
    }
    
    if (!modId) {
        showNotification('Please enter a Nexus Mod ID or URL', 'error');
        return;
    }
    
    preview.innerHTML = '<div style="text-align: center; padding: var(--space-4); color: var(--text-secondary);"><i data-lucide="loader-2" class="animate-spin" style="width: 1rem; height: 1rem;"></i> Loading mod information...</div>';
    
    // Initialize Lucide icons for loading spinner
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    
    // Fetch mod info from API
    fetch(`/api/mods/nexus/${modId}/info`)
        .then(async response => {
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: response.statusText }));
                throw new Error(errorData.detail?.error || errorData.detail || `HTTP ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            const author = data.author || data.uploaded_by?.username || 'Unknown';
            const summary = data.summary || '';
            const version = data.version || '';
            const downloads = data.downloads || 0;
            const endorsements = data.endorsements || 0;
            
            preview.innerHTML = `
                <div class="card" style="padding: var(--space-4);">
                    <h4 style="font-size: var(--text-lg); font-weight: var(--font-semibold); color: var(--text-primary); margin-bottom: var(--space-2);">
                        ${escapeHtml(data.name || 'Unknown Mod')}
                    </h4>
                    <div style="color: var(--text-secondary); margin-bottom: var(--space-3);">
                        <div style="margin-bottom: var(--space-1);">by ${escapeHtml(author)}</div>
                        ${version ? `<div style="font-size: var(--text-sm);">Version: ${escapeHtml(version)}</div>` : ''}
                        <div style="font-size: var(--text-sm); margin-top: var(--space-2);">
                            <span>${downloads.toLocaleString()} downloads</span>
                            <span style="margin-left: var(--space-3);">${endorsements.toLocaleString()} endorsements</span>
                        </div>
                    </div>
                    ${summary ? `<p style="color: var(--text-secondary); font-size: var(--text-sm); margin-bottom: var(--space-4);">${escapeHtml(summary.substring(0, 200))}${summary.length > 200 ? '...' : ''}</p>` : ''}
                    <div style="display: flex; gap: var(--space-2); flex-wrap: wrap;">
                        <button 
                            class="btn btn-primary"
                            onclick="showFileSelectionModal(${modId})">
                            <i data-lucide="download" style="width: 1rem; height: 1rem;"></i>
                            Install Mod
                        </button>
                        <button 
                            class="btn btn-secondary"
                            onclick="inspectModDetails(${modId})">
                            <i data-lucide="info" style="width: 1rem; height: 1rem;"></i>
                            Inspect Details
                        </button>
                        <a 
                            href="https://www.nexusmods.com/cyberpunk2077/mods/${modId}" 
                            target="_blank"
                            class="btn btn-secondary">
                            <i data-lucide="external-link" style="width: 1rem; height: 1rem;"></i>
                            View on Nexus
                        </a>
                    </div>
                </div>
            `;
            
            // Initialize Lucide icons
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
        })
        .catch(error => {
            console.error('Error fetching mod info:', error);
            preview.innerHTML = `
                <div class="card" style="padding: var(--space-4); border-color: var(--danger-border);">
                    <div style="color: var(--danger-text); display: flex; align-items: center; gap: var(--space-2);">
                        <i data-lucide="alert-circle" style="width: 1.2rem; height: 1.2rem;"></i>
                        <div>
                            <div style="font-weight: var(--font-semibold); margin-bottom: var(--space-1);">Error loading mod</div>
                            <div style="font-size: var(--text-sm);">${escapeHtml(error.message)}</div>
                        </div>
                    </div>
                </div>
            `;
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
        });
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function inspectModDetails(modId) {
    // Show loading state
    const url = `https://www.nexusmods.com/cyberpunk2077/mods/${modId}`;
    
    // Get or create modal container
    let modalContainer = document.getElementById('mod-preview-modal-container');
    if (!modalContainer) {
        // Create modal container if it doesn't exist
        modalContainer = document.createElement('div');
        modalContainer.id = 'mod-preview-modal-container';
        document.body.appendChild(modalContainer);
    }
    
    // Show loading
    const loadingHtml = `
        <div class="modal-overlay" onclick="if(event.target == this) this.remove()">
            <div class="modal" onclick="event.stopPropagation()" style="max-width: 800px; padding: var(--space-6);">
                <div style="text-align: center; padding: var(--space-8);">
                    <i data-lucide="loader-2" class="animate-spin" style="width: 2rem; height: 2rem; color: var(--accent-primary);"></i>
                    <div style="margin-top: var(--space-4); color: var(--text-secondary);">Loading mod details...</div>
                </div>
            </div>
        </div>
    `;
    modalContainer.innerHTML = loadingHtml;
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    
    // Fetch preview
    fetch(`/api/mods/preview-by-url?url=${encodeURIComponent(url)}`)
        .then(response => response.text())
        .then(html => {
            modalContainer.innerHTML = html;
            // Re-initialize Lucide icons after content is loaded
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
        })
        .catch(error => {
            console.error('Error loading mod details:', error);
            modalContainer.innerHTML = `
                <div class="modal-overlay" onclick="if(event.target == this) this.remove()">
                    <div class="modal" onclick="event.stopPropagation()" style="max-width: 500px; padding: var(--space-6);">
                        <div style="text-align: center;">
                            <i data-lucide="alert-circle" style="width: 3rem; height: 3rem; color: var(--error-text); margin-bottom: var(--space-4);"></i>
                            <h3 style="font-size: var(--text-lg); font-weight: var(--font-semibold); margin-bottom: var(--space-2);">Error Loading Details</h3>
                            <p style="color: var(--text-secondary); margin-bottom: var(--space-4);">${escapeHtml(error.message)}</p>
                            <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">Close</button>
                        </div>
                    </div>
                </div>
            `;
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
        });
}

function showFileSelectionModal(modId) {
    // Get or create modal container
    let modalContainer = document.getElementById('file-selection-modal-container');
    if (!modalContainer) {
        modalContainer = document.createElement('div');
        modalContainer.id = 'file-selection-modal-container';
        document.body.appendChild(modalContainer);
    }
    
    // Show loading
    modalContainer.innerHTML = `
        <div class="modal-overlay" onclick="if(event.target == this) this.remove()">
            <div class="modal" onclick="event.stopPropagation()" style="max-width: 600px; padding: var(--space-6);">
                <div style="text-align: center; padding: var(--space-8);">
                    <i data-lucide="loader-2" class="animate-spin" style="width: 2rem; height: 2rem; color: var(--accent-primary);"></i>
                    <div style="margin-top: var(--space-4); color: var(--text-secondary);">Loading available versions...</div>
                </div>
            </div>
        </div>
    `;
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    
    // Fetch files
    fetch(`/api/mods/nexus/${modId}/files`)
        .then(async response => {
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: response.statusText }));
                throw new Error(errorData.detail?.error || errorData.detail || `HTTP ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            const files = data.files || [];
            
            if (files.length === 0) {
                modalContainer.innerHTML = `
                    <div class="modal-overlay" onclick="if(event.target == this) this.remove()">
                        <div class="modal" onclick="event.stopPropagation()" style="max-width: 500px; padding: var(--space-6);">
                            <div style="text-align: center;">
                                <i data-lucide="alert-circle" style="width: 3rem; height: 3rem; color: var(--error-text); margin-bottom: var(--space-4);"></i>
                                <h3 style="font-size: var(--text-lg); font-weight: var(--font-semibold); margin-bottom: var(--space-2);">No Files Available</h3>
                                <p style="color: var(--text-secondary); margin-bottom: var(--space-4);">No files found for this mod.</p>
                                <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">Close</button>
                            </div>
                        </div>
                    </div>
                `;
                if (typeof lucide !== 'undefined') {
                    lucide.createIcons();
                }
                return;
            }
            
            // Build file list HTML
            const filesHtml = files.map((file, index) => {
                const sizeMB = file.size ? (file.size / 1024 / 1024).toFixed(1) : 'Unknown';
                const uploadDate = file.uploaded_at ? new Date(file.uploaded_at).toLocaleDateString() : '';
                const isPrimary = file.is_primary ? '<span class="badge" style="background: var(--info-bg); color: var(--info-text); font-size: 10px; padding: 2px 6px; margin-left: var(--space-2);">Main</span>' : '';
                
                return `
                    <div class="file-option" 
                         onclick="selectFile(${modId}, ${file.file_id}, '${escapeHtml(file.name)}', event)"
                         style="padding: var(--space-3); border: 1px solid var(--border-primary); border-radius: var(--radius-md); margin-bottom: var(--space-2); cursor: pointer; transition: all 0.2s; background: var(--bg-secondary);"
                         onmouseover="this.style.borderColor='var(--accent-primary)'; this.style.background='var(--bg-tertiary)'"
                         onmouseout="this.style.borderColor='var(--border-primary)'; this.style.background='var(--bg-secondary)'">
                        <div style="display: flex; justify-content: space-between; align-items: start;">
                            <div style="flex: 1;">
                                <div style="display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-1);">
                                    <strong style="color: var(--text-primary);">${escapeHtml(file.name)}</strong>
                                    ${isPrimary}
                                </div>
                                <div style="font-size: var(--text-sm); color: var(--text-secondary); display: flex; gap: var(--space-3); flex-wrap: wrap;">
                                    <span>Version: ${escapeHtml(file.version)}</span>
                                    <span>Size: ${sizeMB} MB</span>
                                    ${uploadDate ? `<span>Uploaded: ${uploadDate}</span>` : ''}
                                    ${file.download_count > 0 ? `<span>Downloads: ${file.download_count.toLocaleString()}</span>` : ''}
                                </div>
                                ${file.category_name ? `<div style="font-size: var(--text-xs); color: var(--text-tertiary); margin-top: var(--space-1);">${escapeHtml(file.category_name)}</div>` : ''}
                            </div>
                            <i data-lucide="chevron-right" style="width: 1rem; height: 1rem; color: var(--text-tertiary); flex-shrink: 0;"></i>
                        </div>
                    </div>
                `;
            }).join('');
            
            modalContainer.innerHTML = `
                <div class="modal-overlay" onclick="if(event.target == this) this.remove()">
                    <div class="modal" onclick="event.stopPropagation()" style="max-width: 700px; max-height: 90vh; overflow-y: auto;">
                        <div style="padding: var(--space-4); border-bottom: 1px solid var(--border-primary); display: flex; justify-content: space-between; align-items: center;">
                            <h2 style="font-size: var(--text-xl); font-weight: var(--font-bold); margin: 0;">Select Version to Install</h2>
                            <button class="btn btn-ghost" onclick="this.closest('.modal-overlay').remove()" style="padding: var(--space-1);">
                                <i data-lucide="x" style="width: 1.25rem; height: 1.25rem;"></i>
                            </button>
                        </div>
                        <div style="padding: var(--space-4);">
                            <p style="color: var(--text-secondary); margin-bottom: var(--space-4);">Choose which version/file you want to install:</p>
                            <div id="files-list">
                                ${filesHtml}
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
        })
        .catch(error => {
            console.error('Error loading files:', error);
            modalContainer.innerHTML = `
                <div class="modal-overlay" onclick="if(event.target == this) this.remove()">
                    <div class="modal" onclick="event.stopPropagation()" style="max-width: 500px; padding: var(--space-6);">
                        <div style="text-align: center;">
                            <i data-lucide="alert-circle" style="width: 3rem; height: 3rem; color: var(--error-text); margin-bottom: var(--space-4);"></i>
                            <h3 style="font-size: var(--text-lg); font-weight: var(--font-semibold); margin-bottom: var(--space-2);">Error Loading Files</h3>
                            <p style="color: var(--text-secondary); margin-bottom: var(--space-4);">${escapeHtml(error.message)}</p>
                            <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">Close</button>
                        </div>
                    </div>
                </div>
            `;
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
        });
}

function selectFile(modId, fileId, fileName, evt) {
    // Close modal
    const modal = evt.target.closest('.modal-overlay');
    if (modal) {
        modal.remove();
    }
    
    // Install with selected file
    installFromNexus(modId, fileId, fileName);
}

function installFromNexus(modId, fileId = null, fileName = null) {
    const checkCompatibility = document.querySelector('input[name="check_compatibility"]')?.checked !== false;
    
    // Generate job ID (matches format used by ModManager)
    const jobId = `nexus_${modId}`;
    
    // Show installation progress modal
    if (typeof window.showInstallProgress === 'function') {
        window.showInstallProgress(fileName || `Mod ${modId}`, null, jobId);
    }
    
    const payload = {
        check_compatibility: checkCompatibility
    };
    
    if (fileId) {
        payload.file_id = fileId;
    }
    
    fetch(`/api/mods/nexus/${modId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload)
    })
    .then(async response => {
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(errorData.detail?.error || errorData.detail || `HTTP ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        // Success will be handled by progress polling
        if (typeof window.addLogEntry === 'function') {
            window.addLogEntry('success', 'Installation request accepted');
        }
    })
    .catch(error => {
        console.error('Installation error:', error);
        if (typeof window.showInstallError === 'function') {
            window.showInstallError(error.message);
        } else {
            showNotification('Installation failed: ' + error.message, 'error');
        }
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
    if (!notificationArea) {
        console.error('Notification area not found');
        alert(message);
        return;
    }
    
    const notification = document.createElement('div');
    notification.className = `toast toast-${type}`;
    
    // Set background color based on type
    const bgColor = type === 'success' ? 'var(--success-bg)' : 
                   type === 'error' ? 'var(--danger-bg)' : 
                   'var(--bg-secondary)';
    const borderColor = type === 'success' ? 'var(--success-border)' : 
                       type === 'error' ? 'var(--danger-border)' : 
                       'var(--border-primary)';
    const textColor = type === 'success' ? 'var(--success-text)' : 
                     type === 'error' ? 'var(--danger-text)' : 
                     'var(--text-primary)';
    
    // Add icon
    const icon = type === 'success' ? 'check-circle' : 
                type === 'error' ? 'x-circle' : 
                'info';
    notification.innerHTML = `
        <i data-lucide="${icon}" style="width: 1rem; height: 1rem;"></i>
        <span>${escapeHtml(message)}</span>
    `;
    
    notification.style.cssText = `
        background: ${bgColor};
        border: 1px solid ${borderColor};
        border-radius: var(--radius-lg);
        padding: var(--space-3);
        margin-bottom: var(--space-2);
        box-shadow: var(--shadow-lg);
        color: ${textColor};
        animation: slideUp 0.3s ease;
        display: flex;
        align-items: center;
        gap: var(--space-2);
    `;
    
    notificationArea.appendChild(notification);
    
    // Initialize Lucide icons
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transition = 'opacity 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}
