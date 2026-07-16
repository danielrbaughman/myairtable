/* myAirtable - Static Documentation Scripts */

// Theme toggle
document.querySelectorAll(".theme-toggle").forEach(function (btn) {
	function sync(dark) {
		btn.textContent = dark ? "\u2600" : "\u263E";
		btn.setAttribute("aria-pressed", dark ? "true" : "false");
	}
	sync(document.body.classList.contains("dark-mode"));
	btn.addEventListener("click", function () {
		document.body.classList.toggle("dark-mode");
		var dark = document.body.classList.contains("dark-mode");
		localStorage.setItem("theme", dark ? "dark" : "light");
		sync(dark);
	});
});

// Copy-to-clipboard
document.addEventListener("click", function (e) {
	var el = e.target.closest(".copyable");
	if (!el) return;
	if (!navigator.clipboard || !navigator.clipboard.writeText) return;
	navigator.clipboard.writeText(el.getAttribute("data-copy")).then(
		function () {
			el.classList.add("copied");
			setTimeout(function () {
				el.classList.remove("copied");
			}, 1500);
		},
		function () {},
	);
});

// Interactive table: search
document.querySelectorAll(".interactive-search").forEach(function (input) {
	input.addEventListener("input", function () {
		var wrap = document.getElementById(this.dataset.target);
		var term = this.value.toLowerCase();
		wrap.querySelectorAll("tbody tr").forEach(function (tr) {
			var text = tr.textContent.toLowerCase();
			tr.style.display = text.indexOf(term) < 0 ? "none" : "";
		});
	});
});

// Interactive table: filter
document.querySelectorAll(".interactive-filter").forEach(function (sel) {
	sel.addEventListener("change", function () {
		var wrap = document.getElementById(this.dataset.target);
		var col = parseInt(this.dataset.col);
		var val = this.value;
		wrap.querySelectorAll("tbody tr").forEach(function (tr) {
			var cell = tr.children[col];
			if (!val) {
				tr.style.display = "";
				return;
			}
			tr.style.display = cell.getAttribute("data-sort-value") === val ? "" : "none";
		});
		var searchInput = wrap.querySelector(".interactive-search");
		if (searchInput) searchInput.value = "";
	});
});

// Interactive table: sort
document.querySelectorAll("table.interactive thead th").forEach(function (th) {
	th.addEventListener("click", function () {
		var table = this.closest("table");
		var col = parseInt(this.dataset.col);
		var asc = !this.classList.contains("sort-asc");
		table.querySelectorAll("th").forEach(function (h) {
			h.classList.remove("sort-asc", "sort-desc");
		});
		this.classList.add(asc ? "sort-asc" : "sort-desc");
		var tbody = table.querySelector("tbody");
		var rows = Array.from(tbody.querySelectorAll("tr"));
		rows.sort(function (a, b) {
			var av = a.children[col].getAttribute("data-sort-value") || a.children[col].textContent;
			var bv = b.children[col].getAttribute("data-sort-value") || b.children[col].textContent;
			return asc ? av.localeCompare(bv) : bv.localeCompare(av);
		});
		rows.forEach(function (r) {
			tbody.appendChild(r);
		});
	});
});

// Diagram pan/zoom
document.querySelectorAll(".diagram-container").forEach(function (container) {
	var vp = container.querySelector(".diagram-viewport");
	var img = vp.querySelector(".diagram");
	var scale = 1,
		panX = 0,
		panY = 0,
		dragging = false,
		lastX,
		lastY;
	function apply() {
		img.style.transform = "translate(" + panX + "px," + panY + "px) scale(" + scale + ")";
	}
	function reset() {
		scale = 1;
		panX = 0;
		panY = 0;
		apply();
	}
	vp.addEventListener(
		"wheel",
		function (e) {
			e.preventDefault();
			var d = e.deltaY > 0 ? -0.1 : 0.1;
			scale = Math.min(Math.max(0.2, scale + d), 5);
			apply();
		},
		{ passive: false },
	);
	vp.addEventListener("pointerdown", function (e) {
		if (e.button !== 0) return;
		dragging = true;
		lastX = e.clientX;
		lastY = e.clientY;
		vp.setPointerCapture(e.pointerId);
		vp.style.cursor = "grabbing";
		e.preventDefault();
	});
	vp.addEventListener("pointermove", function (e) {
		if (!dragging) return;
		panX += e.clientX - lastX;
		panY += e.clientY - lastY;
		lastX = e.clientX;
		lastY = e.clientY;
		apply();
	});
	vp.addEventListener("pointerup", function (e) {
		if (!dragging) return;
		dragging = false;
		vp.releasePointerCapture(e.pointerId);
		vp.style.cursor = "";
	});
	container.querySelector(".diagram-zoom-in").addEventListener("click", function () {
		scale = Math.min(5, scale + 0.25);
		apply();
	});
	container.querySelector(".diagram-zoom-out").addEventListener("click", function () {
		scale = Math.max(0.2, scale - 0.25);
		apply();
	});
	container.querySelector(".diagram-reset").addEventListener("click", reset);
});

// Anchor link copy
document.addEventListener("click", function (e) {
	var a = e.target.closest(".anchor-link");
	if (!a) return;
	e.preventDefault();
	var url = location.href.split("#")[0] + a.getAttribute("href");
	if (!navigator.clipboard || !navigator.clipboard.writeText) return;
	navigator.clipboard.writeText(url).then(
		function () {
			a.textContent = "Copied!";
			setTimeout(function () {
				a.textContent = "#";
			}, 1500);
		},
		function () {},
	);
});

// Keyboard shortcut: / to focus search
document.addEventListener("keydown", function (e) {
	if (
		e.key === "/" &&
		!e.ctrlKey &&
		!e.metaKey &&
		!["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)
	) {
		e.preventDefault();
		var input = document.querySelector(".global-search-input");
		if (input) input.focus();
	}
});

// Global search autocomplete
document.querySelectorAll(".global-search").forEach(function (wrap) {
	var input = wrap.querySelector(".global-search-input");
	var results = wrap.querySelector(".global-search-results");
	var root = wrap.dataset.root;
	var sel = -1;
	function render(items) {
		sel = -1;
		results.replaceChildren();
		if (!items.length) {
			results.style.display = "none";
			return;
		}
		items.forEach(function (it, i) {
			var item = document.createElement("div");
			item.className = "search-item";
			item.dataset.idx = i;
			item.appendChild(document.createTextNode(it.name + " "));
			var hint = document.createElement("span");
			hint.className = "search-hint";
			hint.textContent = it.table ? it.table + " \u00B7 " + it.kind : it.kind;
			item.appendChild(hint);
			results.appendChild(item);
		});
		results.style.display = "block";
		results._items = items;
	}
	input.addEventListener("input", function () {
		var q = this.value.toLowerCase().trim();
		if (!q) {
			render([]);
			return;
		}
		var tokens = q.split(/\s+/);
		var matches = SEARCH_INDEX.filter(function (it) {
			var text = (it.name + " " + (it.table || "") + " " + it.kind + " " + (it.desc || "")).toLowerCase();
			return tokens.every(function (t) {
				return text.indexOf(t) >= 0;
			});
		}).slice(0, 15);
		render(matches);
	});
	input.addEventListener("keydown", function (e) {
		var items = results.querySelectorAll(".search-item");
		if (!items.length) return;
		if (e.key === "ArrowDown") {
			e.preventDefault();
			sel = Math.min(sel + 1, items.length - 1);
		} else if (e.key === "ArrowUp") {
			e.preventDefault();
			sel = Math.max(sel - 1, 0);
		} else if (e.key === "Enter" && sel >= 0) {
			e.preventDefault();
			items[sel].click();
			return;
		} else if (e.key === "Escape") {
			render([]);
			return;
		} else return;
		items.forEach(function (el, i) {
			el.classList.toggle("active", i === sel);
		});
	});
	results.addEventListener("click", function (e) {
		var item = e.target.closest(".search-item");
		if (!item) return;
		var idx = parseInt(item.dataset.idx);
		var entry = results._items[idx];
		window.location.href = root + entry.url;
	});
	document.addEventListener("click", function (e) {
		if (!wrap.contains(e.target)) render([]);
	});
});
