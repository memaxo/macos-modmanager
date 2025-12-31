// Dashboard auto-refresh functionality

document.addEventListener('DOMContentLoaded', function() {
    // Auto-refresh activity feed every 30 seconds
    const activityFeed = document.getElementById('activity-feed');
    if (activityFeed) {
        // HTMX will handle the refresh via hx-trigger="every 30s"
        console.log('Activity feed auto-refresh enabled');
    }
    
    // Update stats periodically (every 5 minutes)
    setInterval(function() {
        // Trigger HTMX refresh for stats
        htmx.trigger('#stats-container', 'refresh');
    }, 300000); // 5 minutes
});
