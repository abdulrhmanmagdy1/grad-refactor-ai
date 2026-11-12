/**
 * Applies the persisted theme before the first paint.
 *
 * Kept as a tiny standalone file (no bundler, no inline script) so the page
 * never flashes the wrong theme and the Content-Security-Policy can stay at
 * `script-src 'self'` without an inline-script exception.
 */
(function () {
  var root = document.documentElement;
  var theme = null;
  try {
    var stored = window.localStorage.getItem('refactor-ui-theme');
    if (stored === 'light' || stored === 'dark') {
      theme = stored;
    }
  } catch (error) {
    theme = null;
  }
  if (!theme) {
    theme = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches
      ? 'light'
      : 'dark';
  }
  root.classList.toggle('dark', theme === 'dark');
  root.style.colorScheme = theme;
})();
