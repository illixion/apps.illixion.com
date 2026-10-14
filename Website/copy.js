document.querySelectorAll("[data-copy]").forEach(function (b) {
  b.addEventListener("click", function () {
    var done = function () { var t = b.textContent; b.textContent = "Copied"; setTimeout(function () { b.textContent = t; }, 1500); };
    if (navigator.clipboard) navigator.clipboard.writeText(b.getAttribute("data-copy")).then(done, function () {});
  });
});

// Umami events for adding a source, by app (apparition, altstore, sidestore, or clipboard for
// the Copy buttons). A plain listener rather than data-umami-event, whose handler holds the
// link's navigation until the beacon returns.
document.addEventListener("click", function (e) {
  if (!window.umami) return;
  var a = e.target.closest('a[href*="://source?url="]');
  var b = a ? null : e.target.closest("[data-copy]");
  var url = a ? new URL(a.href).searchParams.get("url") : b && b.getAttribute("data-copy");
  if (!url) return;
  window.umami.track("add-source", {
    app: a ? a.protocol.slice(0, -1) : "clipboard",
    source: url.split("/").pop()
  });
});
