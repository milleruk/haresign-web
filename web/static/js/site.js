/* ==========================================================================
   site.js — the small amount of behaviour this site actually needs.

   No framework and no jQuery. Everything below is progressive enhancement: with
   JavaScript disabled the page is fully readable and every link works. The one
   control that depends on JS (the nav toggle) is a <button> that is only
   *needed* below 992px, where the panel it opens is the nav.
   ========================================================================== */
(function () {
  'use strict';

  /* --- Mobile navigation ------------------------------------------------
     aria-expanded on the button is the source of truth for both the open
     state and the CSS that draws the bars as a cross, so the accessible
     state and the visual state cannot drift apart. */
  function initNav() {
    var toggle = document.getElementById('hs-nav-toggle');
    var nav = document.getElementById('hs-nav');
    if (!toggle || !nav) { return; }

    function setOpen(open) {
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      nav.classList.toggle('is-open', open);
    }

    toggle.addEventListener('click', function () {
      setOpen(toggle.getAttribute('aria-expanded') !== 'true');
    });

    // An in-page jump (#platforms) would otherwise leave the panel covering
    // the very thing it scrolled to.
    nav.addEventListener('click', function (event) {
      if (event.target.closest('a')) { setOpen(false); }
    });

    // Escape closes it and returns focus to the control that opened it —
    // without this a keyboard user is left inside a panel with no way out.
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
        setOpen(false);
        toggle.focus();
      }
    });

    // Resizing past the breakpoint leaves the panel open but the toggle
    // hidden, so the state must be reset rather than stranded.
    var desktop = window.matchMedia('(min-width: 992px)');
    var onChange = function (event) { if (event.matches) { setOpen(false); } };
    if (desktop.addEventListener) { desktop.addEventListener('change', onChange); }
    else if (desktop.addListener) { desktop.addListener(onChange); }
  }

  /* --- Footer year -------------------------------------------------------
     The template renders the server's year, so this only corrects a page left
     open across New Year. It is not what makes the year appear. */
  function initYear() {
    var nodes = document.querySelectorAll('[data-hs-year]');
    var year = String(new Date().getFullYear());
    for (var i = 0; i < nodes.length; i++) { nodes[i].textContent = year; }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { initNav(); initYear(); });
  } else {
    initNav();
    initYear();
  }
})();
