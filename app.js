// homepage interactions: nav, copy buttons, terminal demo, reveal on scroll.
(function () {
  "use strict";

  var yearEl = document.getElementById("year");
  if (yearEl) yearEl.textContent = String(new Date().getFullYear());

  // Mobile nav
  var toggle = document.getElementById("navToggle");
  var links = document.getElementById("navLinks");
  if (toggle && links) {
    toggle.addEventListener("click", function () {
      var open = links.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    links.addEventListener("click", function (e) {
      if (e.target && e.target.tagName === "A") links.classList.remove("open");
    });
  }

  // Copy buttons: data-copy points at element id with the text
  var copyBtns = document.querySelectorAll(".copy-btn");
  for (var b = 0; b < copyBtns.length; b++) {
    (function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-copy");
        var src = id ? document.getElementById(id) : null;
        var text = src ? src.textContent : "";
        function done() {
          var old = btn.textContent;
          btn.textContent = "Copied";
          setTimeout(function () { btn.textContent = old; }, 1200);
        }
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text.trim()).then(done, done);
        } else {
          var ta = document.createElement("textarea");
          ta.value = text.trim();
          document.body.appendChild(ta);
          ta.select();
          try { document.execCommand("copy"); } catch (e) { /* noop */ }
          document.body.removeChild(ta);
          done();
        }
      });
    })(copyBtns[b]);
  }

  // Animated terminal preview — popular packages + one failing left-pad.
  // 10 rows: 5 update ok, 1 fails [x], 4 ok. Header "10 · 6 to update · 4 ok".
  var rows = [
    { name: "chalk",     scope: "G", installed: "4.1.2",  latest: "5.4.1",  size: "312KB",  outdated: true },
    { name: "commander", scope: "G", installed: "11.1.0", latest: "14.0.2", size: "890KB",  outdated: true },
    { name: "axios",     scope: "L", installed: "1.6.7",  latest: "1.20.0", size: "1.8MB",  outdated: true },
    { name: "express",   scope: "L", installed: "4.19.2", latest: "5.1.0",  size: "2.4MB",  outdated: true },
    { name: "lodash",    scope: "L", installed: "4.17.20", latest: "4.17.21", size: "1.2MB", outdated: true },
    { name: "left-pad",  scope: "L", installed: "1.3.0",  latest: "1.3.1",  size: "8KB",    outdated: true, fails: true },
    { name: "react",     scope: "L", installed: "19.2.0", latest: "19.2.0", size: "12.6MB", outdated: false },
    { name: "typescript", scope: "G", installed: "5.9.2",  latest: "5.9.2",  size: "68MB",   outdated: false },
    { name: "vite",      scope: "L", installed: "6.0.0",  latest: "6.0.0",  size: "24MB",   outdated: false },
    { name: "eslint",    scope: "L", installed: "9.12.0", latest: "9.12.0", size: "18MB",   outdated: false }
  ];

  var table = document.getElementById("termTable");
  var barText = document.getElementById("termBarText");
  var barFill = document.getElementById("termBarFill");
  var status = document.getElementById("termStatus");
  var nextEl = document.getElementById("termNext");
  var replay = document.getElementById("termReplay");

  if (table && barText && barFill && status && nextEl) {
    var queue = [];
    for (var q = 0; q < rows.length; q++) {
      if (rows[q].outdated) queue.push(q);
    }
    var total = queue.length || 1;
    var phases = total + 1; // last phase = finished state with [x] visible
    var step = 0;
    var timer = null;

    function esc(s) {
      return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    }

    function render() {
      var finished = step >= total;
      var currentIdx = finished ? -1 : queue[step];
      table.innerHTML = "";
      for (var i = 0; i < rows.length; i++) {
        var r = rows[i];
        var isCurrent = i === currentIdx;
        var qpos = queue.indexOf(i);
        var isDone = r.outdated && (finished || qpos < step);
        var div = document.createElement("div");
        div.className = "term-row" + (isCurrent ? " active" : "") + (isDone ? " done" : "");
        var mark, cls;
        if (!r.outdated) { mark = "[ok]"; cls = "st-ok"; }
        else if (isDone && r.fails) { mark = "[x]"; cls = "st-err"; }
        else if (isDone) { mark = "[ok]"; cls = "st-ok"; }
        else if (isCurrent) { mark = "[&gt;]"; cls = "st-up"; }
        else { mark = "[update]"; cls = "st-up"; }
        var ver = r.outdated ? esc(r.installed) + "→" + esc(r.latest) : esc(r.installed);
        div.innerHTML =
          '<span class="n">' + (i + 1) + '</span>' +
          '<span class="scope">[' + r.scope + ']</span>' +
          "<span class='name'>" + esc(r.name) + "</span>" +
          "<span class='ver'>" + ver + "</span>" +
          "<span class='size'>" + esc(r.size) + "</span>" +
          "<span class='" + cls + "'>" + mark + "</span>";
        table.appendChild(div);
      }
      var doneCount = finished ? total : step + 1;
      var pct = Math.round((doneCount / total) * 100);
      var filled = Math.round((doneCount / total) * 12);
      var bar = "";
      for (var f = 0; f < 12; f++) bar += f < filled ? "█" : "░";
      barText.textContent = "[" + bar + "] " + doneCount + "/" + total + " (" + pct + "%)";
      barFill.style.width = pct + "%";
      if (finished) {
        status.textContent = "Done: 5 updated, 1 failed (left-pad) — refreshing table";
        nextEl.textContent = "·  failures listed by name, nothing hidden";
      } else {
        var cur = rows[currentIdx];
        status.textContent = "Updating package: [" + cur.scope + "] " + cur.name + " " + cur.installed + " → " + cur.latest;
        if (step + 1 < queue.length) {
          var nxt = rows[queue[step + 1]];
          nextEl.textContent = "Next: [" + nxt.scope + "] " + nxt.name;
        } else {
          nextEl.textContent = "·  finishing…";
        }
      }
    }

    function reducedMotion() {
      try {
        return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
      } catch (e) { return false; }
    }

    function start() {
      if (timer) { clearInterval(timer); timer = null; }
      if (reducedMotion()) {
        step = total; // static finished state, replay still available
        render();
        return;
      }
      timer = setInterval(function () {
        step = (step + 1) % phases;
        render();
      }, 1600);
    }

    render();
    start();
    if (replay) {
      replay.addEventListener("click", function () {
        step = 0;
        render();
        start();
      });
    }
  }

  // Reveal on scroll
  try {
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (en.isIntersecting) {
            en.target.classList.add("visible");
            io.unobserve(en.target);
          }
        });
      }, { threshold: 0.12 });
      var revealEls = document.querySelectorAll(".card, .step, .panel");
      for (var k = 0; k < revealEls.length; k++) {
        revealEls[k].classList.add("reveal");
        io.observe(revealEls[k]);
      }
    }
  } catch (e) { /* noop: content stays visible without JS enhancement */ }
})();
