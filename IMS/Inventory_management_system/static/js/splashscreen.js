/**
 * PageSplash - System-wide Feature Guide / Splashscreen
 * Shows contextual help based on current page
 */

const PageSplash = (function() {
    'use strict';
    
    const STORAGE_PREFIX = 'splash_dismissed_';
    let currentConfig = null;
    let overlayEl = null;
    let helpBtnEl = null;
    
    /**
     * Initialize splashscreen for a page
     * @param {Object} config - Configuration object
     * @param {string} config.pageId - Unique identifier for the page
     * @param {string} config.title - Page title
     * @param {string} config.subtitle - Optional subtitle
     * @param {string} config.icon - Emoji or icon for the page
     * @param {Array} config.features - Array of feature objects {icon, title, desc}
     * @param {Array} config.tips - Optional array of tip strings
     * @param {boolean} config.forceShow - Force show even if dismissed
     */
    function init(config) {
        if (!config || !config.pageId) {
            console.warn('PageSplash: Missing required config.pageId');
            return;
        }
        
        currentConfig = config;
        
        // Create overlay if it doesn't exist
        createOverlay();
        createHelpButton();
        
        // Check if should show
        const storageKey = STORAGE_PREFIX + config.pageId;
        const isDismissed = localStorage.getItem(storageKey) === 'true';
        
        if (!isDismissed || config.forceShow) {
            // Small delay for page load
            setTimeout(() => show(), 300);
        }
    }
    
    /**
     * Create the overlay element
     */
    function createOverlay() {
        // Remove existing if any
        const existing = document.getElementById('page-splash-overlay');
        if (existing) existing.remove();
        
        overlayEl = document.createElement('div');
        overlayEl.id = 'page-splash-overlay';
        overlayEl.className = 'page-splash-overlay';
        overlayEl.innerHTML = `
            <div class="page-splash-container">
                <div class="page-splash-header">
                    <span class="page-splash-icon">${currentConfig.icon || '📖'}</span>
                    <h2 class="page-splash-title">${escapeHtml(currentConfig.title || 'Welcome')}</h2>
                    ${currentConfig.subtitle ? `<p class="page-splash-subtitle">${escapeHtml(currentConfig.subtitle)}</p>` : ''}
                </div>
                
                ${currentConfig.tips && currentConfig.tips.length > 0 ? `
                <div class="page-splash-tips">
                    <div class="page-splash-tips-title">💡 Quick Tips</div>
                    <ul class="page-splash-tips-list">
                        ${currentConfig.tips.map(tip => `<li>${escapeHtml(tip)}</li>`).join('')}
                    </ul>
                </div>
                ` : ''}
                
                <div class="page-splash-features" id="splash-features">
                    ${renderFeatures()}
                </div>
                
                <div class="page-splash-footer">
                    <button type="button" class="page-splash-btn" id="splash-got-it">
                        Got it, let's go! →
                    </button>
                    <label class="page-splash-dont-show">
                        <input type="checkbox" id="splash-dont-show-check">
                        Don't show this again
                    </label>
                </div>
            </div>
        `;
        
        document.body.appendChild(overlayEl);
        
        // Bind events
        document.getElementById('splash-got-it').addEventListener('click', dismiss);
        overlayEl.addEventListener('click', function(e) {
            if (e.target === overlayEl) dismiss();
        });
        
        // ESC key to close
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && overlayEl.classList.contains('show')) {
                dismiss();
            }
        });
    }
    
    /**
     * Create floating help button
     */
    function createHelpButton() {
        const existing = document.getElementById('page-splash-help-btn');
        if (existing) existing.remove();
        
        helpBtnEl = document.createElement('button');
        helpBtnEl.id = 'page-splash-help-btn';
        helpBtnEl.className = 'page-splash-help-btn hidden';
        helpBtnEl.type = 'button';
        helpBtnEl.innerHTML = '❓';
        helpBtnEl.title = 'Show page guide';
        helpBtnEl.addEventListener('click', () => show(true));
        
        document.body.appendChild(helpBtnEl);
    }
    
    /**
     * Render feature cards HTML
     */
    function renderFeatures() {
        if (!currentConfig.features || currentConfig.features.length === 0) {
            return '<p style="color: #64748b; text-align: center;">Explore this page to discover its features!</p>';
        }
        
        return currentConfig.features.map(f => `
            <div class="page-splash-feature">
                <span class="page-splash-feature-icon">${f.icon || '✨'}</span>
                <div class="page-splash-feature-title">${escapeHtml(f.title || '')}</div>
                <p class="page-splash-feature-desc">${escapeHtml(f.desc || '')}</p>
            </div>
        `).join('');
    }
    
    /**
     * Show the splashscreen
     */
    function show(forceReset = false) {
        if (!overlayEl) return;
        
        if (forceReset) {
            // Re-render features for animation restart
            const featuresEl = document.getElementById('splash-features');
            if (featuresEl) {
                featuresEl.innerHTML = renderFeatures();
            }
        }
        
        overlayEl.classList.add('show');
        document.body.style.overflow = 'hidden';
        
        // Hide help button while splash is showing
        if (helpBtnEl) helpBtnEl.classList.add('hidden');
    }
    
    /**
     * Dismiss the splashscreen
     */
    function dismiss() {
        if (!overlayEl) return;
        
        // Check if "don't show again" is checked
        const checkbox = document.getElementById('splash-dont-show-check');
        if (checkbox && checkbox.checked && currentConfig) {
            localStorage.setItem(STORAGE_PREFIX + currentConfig.pageId, 'true');
        }
        
        overlayEl.classList.remove('show');
        document.body.style.overflow = '';
        
        // Show help button after dismissing
        setTimeout(() => {
            if (helpBtnEl) helpBtnEl.classList.remove('hidden');
        }, 300);
    }
    
    /**
     * Reset dismissal for a page (for testing)
     */
    function reset(pageId) {
        localStorage.removeItem(STORAGE_PREFIX + (pageId || currentConfig?.pageId));
    }
    
    /**
     * Reset all dismissals
     */
    function resetAll() {
        Object.keys(localStorage).forEach(key => {
            if (key.startsWith(STORAGE_PREFIX)) {
                localStorage.removeItem(key);
            }
        });
    }
    
    /**
     * Escape HTML to prevent XSS
     */
    function escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
    
    // Public API
    return {
        init: init,
        show: show,
        dismiss: dismiss,
        reset: reset,
        resetAll: resetAll
    };
})();

// Make globally available
window.PageSplash = PageSplash;
