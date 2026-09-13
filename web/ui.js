// LazerMCP UI Utilities
(function() {
  // --- Dark Mode Toggle ---
  function setupTheme() {
    let saved = null;
    try { saved = localStorage.getItem("lmcp_theme"); } catch (_) {}
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    let isDark = saved === 'dark' || (!saved && prefersDark);
    
    function applyTheme() {
      if (isDark) {
        document.body.classList.add('dark-mode');
        document.body.classList.remove('light-mode');
      } else {
        document.body.classList.add('light-mode');
        document.body.classList.remove('dark-mode');
      }
      const themeMeta = document.querySelector('meta[name="theme-color"]');
      if (themeMeta) themeMeta.setAttribute('content', isDark ? '#111111' : '#fafafa');
      try { localStorage.setItem("lmcp_theme", isDark ? 'dark' : 'light'); } catch (_) {}
    }
    
    applyTheme();

    // Create Toggle Button in Nav
    const navLinks = document.querySelector('nav .links') || document.querySelector('nav');
    if (navLinks) {
      const toggleBtn = document.createElement('button');
      toggleBtn.className = 'theme-toggle';
      toggleBtn.title = 'Tema Değiştir';
      toggleBtn.setAttribute('aria-label', 'Tema değiştir');
      toggleBtn.setAttribute('aria-pressed', String(isDark));
      toggleBtn.style.cssText = 'background:transparent; border:none; color:inherit; cursor:pointer; font-size:16px; margin-left:12px;';
      toggleBtn.innerHTML = isDark ? '☀️' : '🌙';
      
      toggleBtn.addEventListener('click', function() {
        isDark = !isDark;
        toggleBtn.innerHTML = isDark ? '☀️' : '🌙';
        toggleBtn.setAttribute('aria-pressed', String(isDark));
        applyTheme();
      });
      
      navLinks.appendChild(toggleBtn);
    }
  }

  // --- Toast Notification System ---
  function setupToast() {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      document.body.appendChild(container);
    }
    
    window.showToast = function(message, type = 'info') {
      const toast = document.createElement('div');
      toast.className = 'toast ' + type;
      
      let icon = 'ℹ️';
      if (type === 'success') icon = '✅';
      if (type === 'error') icon = '❌';
      
      toast.innerHTML = '<span>' + icon + '</span> <span>' + message + '</span>';
      container.appendChild(toast);
      
      setTimeout(function() {
        toast.classList.add('fade-out');
        setTimeout(function() {
          if (toast.parentNode) {
            toast.parentNode.removeChild(toast);
          }
        }, 300);
      }, 3000);
    }
  }

  document.addEventListener('DOMContentLoaded', function() {
    setupTheme();
    setupToast();
  });
})();
