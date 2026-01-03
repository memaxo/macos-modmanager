/**
 * Activity/Command Center JavaScript
 * Handles log streaming, auto-refresh, and real-time updates
 */

(function() {
    'use strict';
    
    let logEventSource = null;
    let gameLogEventSource = null;
    let autoScrollEnabled = true;
    
    // Initialize on page load
    document.addEventListener('DOMContentLoaded', function() {
        initializeLogViewer();
        initializeAutoRefresh();
        initializeLogFilters();
    });
    
    /**
     * Initialize log viewer with SSE streaming
     */
    function initializeLogViewer() {
        const logViewer = document.getElementById('launch-logs-viewer');
        if (!logViewer) return;
        
        // Load initial logs
        loadLaunchLogs();
        
        // Set up auto-scroll
        logViewer.addEventListener('scroll', function() {
            const isAtBottom = logViewer.scrollHeight - logViewer.clientHeight <= logViewer.scrollTop + 50;
            autoScrollEnabled = isAtBottom;
        });
        
        // Connect to launch logs SSE
        connectLaunchLogsSSE();
        
        // Connect to game logs SSE
        connectGameLogsSSE();
    }
    
    /**
     * Load launch logs via API
     */
    function loadLaunchLogs() {
        const logViewer = document.getElementById('launch-logs-viewer');
        if (!logViewer) return;
        
        fetch('/api/launcher/logs?limit=500')
            .then(response => response.json())
            .then(data => {
                renderLogs(data.logs || []);
            })
            .catch(error => {
                console.error('Error loading logs:', error);
                logViewer.innerHTML = '<div style="color: var(--accent-error);">Error loading logs</div>';
            });
    }
    
    /**
     * Connect to launch logs SSE stream
     */
    function connectLaunchLogsSSE() {
        // Close existing connection
        if (logEventSource) {
            logEventSource.close();
        }
        
        // Create new SSE connection
        const eventSource = new EventSource('/api/launcher/logs/stream');
        
        eventSource.onmessage = function(event) {
            const logLine = JSON.parse(event.data);
            appendLogLine(logLine);
        };
        
        eventSource.onerror = function(error) {
            console.error('SSE error:', error);
            // Reconnect after delay
            setTimeout(connectLaunchLogsSSE, 5000);
        };
        
        logEventSource = eventSource;
    }
    
    /**
     * Connect to game logs SSE stream
     */
    function connectGameLogsSSE() {
        // Close existing connection
        if (gameLogEventSource) {
            gameLogEventSource.close();
        }
        
        // Create new SSE connection for game logs
        const eventSource = new EventSource('/api/logs/stream');
        
        eventSource.onmessage = function(event) {
            const logLine = JSON.parse(event.data);
            appendLogLine(logLine);
        };
        
        eventSource.onerror = function(error) {
            console.error('Game logs SSE error:', error);
            // Reconnect after delay
            setTimeout(connectGameLogsSSE, 5000);
        };
        
        gameLogEventSource = eventSource;
    }
    
    /**
     * Append a single log line to the viewer
     */
    function appendLogLine(logLine) {
        const logViewer = document.getElementById('launch-logs-viewer');
        if (!logViewer) return;
        
        const logElement = createLogElement(logLine);
        logViewer.appendChild(logElement);
        
        // Auto-scroll if enabled
        if (autoScrollEnabled) {
            logViewer.scrollTop = logViewer.scrollHeight;
        }
        
        // Limit log viewer size (keep last 1000 lines)
        const lines = logViewer.querySelectorAll('.log-line');
        if (lines.length > 1000) {
            lines[0].remove();
        }
    }
    
    /**
     * Render multiple logs
     */
    function renderLogs(logs) {
        const logViewer = document.getElementById('launch-logs-viewer');
        if (!logViewer) return;
        
        if (logs.length === 0) {
            logViewer.innerHTML = '<div style="color: var(--text-secondary); text-align: center; padding: var(--space-4);">No logs available</div>';
            return;
        }
        
        logViewer.innerHTML = '';
        logs.forEach(log => {
            const logElement = createLogElement(log);
            logViewer.appendChild(logElement);
        });
        
        // Scroll to bottom
        logViewer.scrollTop = logViewer.scrollHeight;
    }
    
    /**
     * Create a log line element
     */
    function createLogElement(log) {
        const div = document.createElement('div');
        div.className = 'log-line';
        div.style.cssText = 'padding: var(--space-1) 0; border-bottom: 1px solid var(--border-primary); display: flex; gap: var(--space-2); align-items: start;';
        
        // Timestamp
        const timestamp = new Date(log.timestamp).toLocaleTimeString();
        const timeSpan = document.createElement('span');
        timeSpan.style.cssText = 'color: var(--text-tertiary); min-width: 80px; font-size: 10px;';
        timeSpan.textContent = timestamp;
        
        // Level badge
        const levelSpan = document.createElement('span');
        levelSpan.style.cssText = 'min-width: 60px; font-size: 10px; text-transform: uppercase;';
        const levelColors = {
            'error': 'var(--accent-error)',
            'warning': 'var(--accent-warning)',
            'info': 'var(--accent-info)',
            'debug': 'var(--text-tertiary)'
        };
        levelSpan.style.color = levelColors[log.level] || 'var(--text-secondary)';
        levelSpan.textContent = `[${log.level}]`;
        
        // Source badge
        const sourceSpan = document.createElement('span');
        sourceSpan.style.cssText = 'min-width: 80px; font-size: 10px; color: var(--text-secondary);';
        sourceSpan.textContent = `[${log.source}]`;
        
        // Message
        const messageSpan = document.createElement('span');
        messageSpan.style.cssText = 'flex: 1; color: var(--text-primary); word-break: break-word;';
        messageSpan.textContent = log.message;
        
        div.appendChild(timeSpan);
        div.appendChild(levelSpan);
        div.appendChild(sourceSpan);
        div.appendChild(messageSpan);
        
        return div;
    }
    
    /**
     * Initialize auto-refresh for metrics and status
     */
    function initializeAutoRefresh() {
        // Metrics and status are handled by HTMX polling
        // This function can be extended for additional refresh logic
    }
    
    /**
     * Initialize log filters
     */
    function initializeLogFilters() {
        // Filters are handled by the filterLogs() function in activity.html
        // This function can be extended for additional filter logic
    }
    
    /**
     * Cleanup on page unload
     */
    window.addEventListener('beforeunload', function() {
        if (logEventSource) {
            logEventSource.close();
        }
        if (gameLogEventSource) {
            gameLogEventSource.close();
        }
    });
    
    // Export functions for global access
    window.activityJS = {
        loadLaunchLogs: loadLaunchLogs,
        connectLaunchLogsSSE: connectLaunchLogsSSE,
        connectGameLogsSSE: connectGameLogsSSE,
        renderLogs: renderLogs
    };
})();
