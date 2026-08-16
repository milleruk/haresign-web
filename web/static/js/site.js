/* ==========================================================================
   site.js — the small amount of behaviour this site actually needs.

   No framework and no jQuery. Everything below is progressive enhancement: with
   JavaScript disabled the page is fully readable and every link works. The nav
   toggle is a <button> that is only *needed* below 1200px, where the panel it
   opens is the nav; the homepage banner renders as three stacked frames and
   only becomes a carousel once this file has run, so nothing on it is behind
   the script.
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
    var desktop = window.matchMedia('(min-width: 1200px)');
    var onChange = function (event) { if (event.matches) { setOpen(false); } };
    if (desktop.addEventListener) { desktop.addEventListener('change', onChange); }
    else if (desktop.addListener) { desktop.addListener(onChange); }
  }

  /* --- Overlay header ----------------------------------------------------
     On the homepage the header floats transparently over the banner. Once the
     page has moved at all, the navy ground comes back — without it the links
     would be white type on whatever the next section happens to be.

     Only the overlay variant is touched: every other page has a solid bar that
     needs no state. The listener is passive and does its work in a frame, so
     scrolling is never blocked by a class toggle. */
  function initHeader() {
    var header = document.getElementById('hs-header');
    if (!header || !header.classList.contains('hs-header--overlay')) { return; }

    var pending = false;
    function apply() {
      pending = false;
      header.classList.toggle('is-stuck', window.pageYOffset > 24);
    }
    window.addEventListener('scroll', function () {
      if (!pending) { pending = true; window.requestAnimationFrame(apply); }
    }, { passive: true });
    apply();  // A reload part-way down the page starts in the right state.
  }

  /* --- Homepage banner ---------------------------------------------------
     Three frames over photography, rotating.

     Progressive enhancement in the strict sense: the markup renders as three
     stacked banners with no controls, and this function is what turns it into a
     carousel. `hs-hero--live` is the switch, so the styling of the two states
     lives in CSS rather than in inline styles set from here.

     Rotation is suspended while the pointer is over the banner or focus is
     inside it — nobody wants the thing they are reading or the button they are
     about to press to be replaced underneath them — and the Pause control stops
     it for good (WCAG 2.2.2). Under prefers-reduced-motion it never starts:
     the controls are there and everything else works. */
  function initHero() {
    var hero = document.querySelector('[data-hs-carousel]');
    if (!hero) { return; }

    var slides = hero.querySelectorAll('[data-hs-slide]');
    var dots = hero.querySelectorAll('[data-hs-dot]');
    if (slides.length < 2) { return; }

    var INTERVAL = 7000;
    var index = 0;
    var timer = null;
    var stopped = false;   // the Pause control: a decision, not a hover
    var motionOk = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    hero.classList.add('hs-hero--live');

    function show(next) {
      index = (next + slides.length) % slides.length;
      for (var i = 0; i < slides.length; i++) {
        var active = i === index;
        slides[i].classList.toggle('is-active', active);
        // Removed from the accessibility tree rather than merely invisible, so
        // a screen reader is given one frame instead of all three.
        if (active) { slides[i].removeAttribute('aria-hidden'); }
        else { slides[i].setAttribute('aria-hidden', 'true'); }
      }
      for (var j = 0; j < dots.length; j++) {
        var current = j === index;
        dots[j].classList.toggle('is-active', current);
        if (current) { dots[j].setAttribute('aria-current', 'true'); }
        else { dots[j].removeAttribute('aria-current'); }
      }
    }

    function start() {
      if (timer || stopped || !motionOk) { return; }
      timer = window.setInterval(function () { show(index + 1); }, INTERVAL);
    }
    function halt() {
      if (timer) { window.clearInterval(timer); timer = null; }
    }
    // A manual move restarts the clock, so the next frame is a full interval
    // away rather than however much was left of the one interrupted.
    function go(next) { show(next); halt(); start(); }

    var prev = hero.querySelector('[data-hs-prev]');
    var next = hero.querySelector('[data-hs-next]');
    if (prev) { prev.addEventListener('click', function () { go(index - 1); }); }
    if (next) { next.addEventListener('click', function () { go(index + 1); }); }
    for (var k = 0; k < dots.length; k++) {
      (function (target) {
        dots[target].addEventListener('click', function () { go(target); });
      })(k);
    }

    // The Pause control is built here rather than in the template: with no
    // JavaScript nothing rotates, and a Pause button for a banner that is not
    // moving is a control that does nothing.
    var controls = hero.querySelector('.hs-hero__controls');
    if (controls && motionOk) {
      var pause = document.createElement('button');
      pause.type = 'button';
      pause.className = 'hs-hero__pause';
      pause.textContent = 'Pause';
      pause.setAttribute('aria-label', 'Pause the banner');
      pause.addEventListener('click', function () {
        stopped = !stopped;
        if (stopped) { halt(); } else { start(); }
        pause.textContent = stopped ? 'Play' : 'Pause';
        pause.setAttribute('aria-label', stopped ? 'Play the banner' : 'Pause the banner');
      });
      controls.appendChild(pause);
    }

    hero.addEventListener('mouseenter', halt);
    hero.addEventListener('mouseleave', start);
    hero.addEventListener('focusin', halt);
    hero.addEventListener('focusout', function (event) {
      if (!hero.contains(event.relatedTarget)) { start(); }
    });

    show(0);
    // A frame later, so the first paint of the carousel is a still frame and
    // the crossfade only ever runs between two slides — see `is-ready` in
    // pages/home.css.
    window.requestAnimationFrame(function () { hero.classList.add('is-ready'); });
    start();
  }

  /* --- Footer year -------------------------------------------------------
     The template renders the server's year, so this only corrects a page left
     open across New Year. It is not what makes the year appear. */
  function initYear() {
    var nodes = document.querySelectorAll('[data-hs-year]');
    var year = String(new Date().getFullYear());
    for (var i = 0; i < nodes.length; i++) { nodes[i].textContent = year; }
  }

  function init() {
    initNav();
    initHeader();
    initHero();
    initYear();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
