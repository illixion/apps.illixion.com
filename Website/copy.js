document.querySelectorAll("[data-copy]").forEach(function (b) {
  b.addEventListener("click", function () {
    var done = function () { var t = b.textContent; b.textContent = "Copied"; setTimeout(function () { b.textContent = t; }, 1500); };
    if (navigator.clipboard) navigator.clipboard.writeText(b.getAttribute("data-copy")).then(done, function () {});
  });
});
