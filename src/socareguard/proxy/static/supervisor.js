(function () {
  // Framed (the Hugging Face Space page shows the app in a frame from another site): show the
  // line with the new-tab link, since some browsers block the sign-in cookie in a frame.
  let framed = false;
  try { framed = window.top !== window.self; } catch (e) { framed = true; }
  if (framed) document.querySelectorAll(".framed-only").forEach((el) => { el.hidden = false; });
  // The sign-in redirects to /supervisor?signin=1; once signed in, the flag is dropped from the address.
  if (document.getElementById("sup-who") && /[?&]signin=1/.test(window.location.search)) {
    const u = new URL(window.location.href);
    u.searchParams.delete("signin");
    try { window.history.replaceState(null, "", u.pathname + u.search + u.hash); } catch (e) { /* keep the address */ }
  }
  // Review links: each "Open read-only" button asks the server for a 30-minute review token
  // (written to the ledger as review_opened) and opens the panel in read-only mode in a new tab.
  // The supervisor cookie goes with the request, so no key is held in this script.
  document.querySelectorAll("button.review-open").forEach((b) => b.addEventListener("click", async () => {
    const status = b.parentElement.querySelector(".review-status");
    b.disabled = true;
    if (status) status.textContent = "";
    try {
      const r = await fetch(`/v1/sessions/${encodeURIComponent(b.dataset.session)}/review-token`, {method: "POST", credentials: "same-origin"});
      const data = await r.json();
      if (!r.ok) throw new Error((data.error && data.error.message) || data.detail || r.statusText);
      b.dataset.url = data.url;
      // In a frame the review opens in the same frame: a new tab is a top-level page on this
      // site, where the cookie that the frame holds (partitioned under the framing site) is absent.
      if (framed) { window.location.assign(data.url); return; }
      window.open(data.url, "_blank", "noopener");
      if (status) {
        status.textContent = " ";
        const a = document.createElement("a");
        a.className = "review-link"; a.href = data.url; a.target = "_blank"; a.rel = "noopener";
        a.textContent = "Review link (read-only, 30 minutes)";
        status.appendChild(a);
      }
    } catch (e) {
      if (status) status.textContent = " Refused: " + e.message;
    } finally { b.disabled = false; }
  }));
})();
