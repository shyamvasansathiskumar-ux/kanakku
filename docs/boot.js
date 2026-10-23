// Runs first, before anything renders. Kept out of the HTML so the CSP can forbid inline scripts.
// 1) Marks JS as available, so the loader and motion styles apply.
// 2) Refuses to be shown inside someone else's frame. GitHub Pages can't send a frame-ancestors
//    header, so if this page finds itself framed it hides itself and offers a link out instead.
document.documentElement.classList.add("js");
try {
  if (window.top !== window.self) {
    document.documentElement.classList.add("framed");
    document.addEventListener("DOMContentLoaded", () => {
      const a = document.createElement("a");
      a.href = location.href; a.target = "_top"; a.rel = "noopener noreferrer";
      a.className = "framed-note"; a.textContent = "This page doesn't run inside other sites. Open it on its own →";
      document.body.prepend(a);
    });
  }
} catch (e) {
  document.documentElement.classList.add("framed");
}
