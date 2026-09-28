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
      if (e.target.tagName === "A") links.classList.remove("open");
    });
  }

  // Copy buttons: data-copy points at element id with the text
  document.querySelectorAll(".copy-btn").forEach(function (btn) {
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
  });

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
    { name: "typescript", scope: "G", installed: "5.9.2", latest: "5.9.2",  size: "68MB",   outdated: false },
    { name: "vite",      scope: "L", installed: "6.0.0",  latest: "6.0.0",  size: "24MB",   outdated: false },
    { name: "eslint",    scope: "L", installed: "9.12.0", latest: "9.12.0", size: "18MB",   outdated: false }
  ];
  var queue = rows
    .map(function (r, i) { return r.outdated ? i : -1; })
    .filter(function (i) { return i >= 0; });
  var total = queue.length || 1;

  var table = document.getElementById("termTable");
  var barText = document.getElementById("termBarText");
  var barFill = document.getElementById("termBarFill");
  var status = document.getElementById("termStatus");
  var nextEl = document.getElementById("termNext");
  var step = 0;

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
  }

  function render() {
    if (!table) return;
    table.innerHTML = "";
    var currentIdx = queue[Math.min(step, queue.length - 1)];
    rows.forEach(function (r, i) {
      var div = document.createElement("div");
      var isCurrent = i === currentIdx;
      var qpos = queue.indexOf(i);
      var isDone = r.outdated && qpos >= 0 && qpos < step;
      div.className = "term-row" + (isCurrent ? " active" : "") + (isDone ? " done" : "");
      var mark, cls;
      if (!r.outdated) { mark = "[ok]"; cls = "st-ok"; }
      else if (isDone && r.fails) { mark = "[x]"; cls = "st-err"; }
      else if (isDone) { mark = "[ok]"; cls = "st-ok"; }
      else if (isCurrent) { mark = "[&gt;]"; cls = "st-up"; }
      else { mark = "[update]"; cls = "st-up"; }
      var ver = r.outdated
        ? esc(r.installed) + "→" + esc(r.latest)
        : esc(r.installed);
      div.innerHTML =
        '<span class="n">' + (i + 1) + '</span>' +
        '<span class="scope">[' + r.scope + ']</span>' +
        "<span class='name'>" + esc(r.name) + "</span>" +
        "<span class='ver'>" + ver + "</span>" +
        "<span class='size'>" + esc(r.size) + "</span>" +
        "<span class='" + cls + "'>" + mark + "</span>";
      table.appendChild(div);
    });
    var doneCount = Math.min(step + 1, total);
    var pct = Math.round((doneCount / total) * 100);
    var filled = Math.round((doneCount / total) * 12);
    if (barText) barText.textContent = "[" + "█".repeat(filled) + "░".repeat(12 - filled) + "] " + doneCount + "/" + total + " (" + pct + "%)";
    if (barFill) barFill.style.width = pct + "%";
    if (status && currentIdx != null) {
      var cur = rows[currentIdx];
      status.textContent = "Updating package: [" + cur.scope + "] " + cur.name + " " + cur.installed + " → " + cur.latest;
    }
    if (nextEl) {
      var nxt = rows[queue[Math.min(step + 1, queue.length - 1)]];
      if (step + 1 < queue.length && nxt) {
        nextEl.textContent = "Next: [" + nxt.scope + "] " + nxt.name + "  ·  locals first, then globals";
      } else {
        nextEl.textContent = "·  finishing… refreshing table";
      }
    }
  }

  if (table) {
    render();
    var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reduceMotion) {
      setInterval(function () {
        step = (step + 1) % total;
        render();
      }, 1600);
    } else {
      step = 2;
      render();
    }
  }

  // Reveal on scroll
  var io = null;
  if ("IntersectionObserver" in window) {
    io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          en.target.classList.add("visible");
          io.unobserve(en.target);
        }
      });
    }, { threshold: 0.12 });
    document.querySelectorAll(".card, .step, .panel").forEach(function (el) {
      el.classList.add("reveal");
      io.observe(el);
    });
  }
})();
