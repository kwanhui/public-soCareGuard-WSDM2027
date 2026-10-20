(function () {
  // The sign-in redirects to /supervisor?signin=1; once signed in, the flag is dropped from the address.
  if (document.getElementById("sup-who") && /[?&]signin=1/.test(window.location.search)) {
    const u = new URL(window.location.href);
    u.searchParams.delete("signin");
    try { window.history.replaceState(null, "", u.pathname + u.search + u.hash); } catch (e) { /* keep the address */ }
  }
  // Review links: each "Review and release" or "Open read-only" button asks the server for a
  // 30-minute review token (written to the ledger as review_opened) and opens the review page in
  // place of this view. The supervisor cookie goes with the request, so no key is held in this
  // script. The review opens in the same tab whether or not the app is shown in another site's
  // frame (the Hugging Face Space page): a new tab out of that frame is a top-level page on this
  // site, where the cookie that the frame holds (partitioned under the framing site) is absent,
  // so the same tab is the one behaviour that works on both addresses.
  document.querySelectorAll("button.review-open").forEach((b) => b.addEventListener("click", async () => {
    const status = b.parentElement.querySelector(".review-status");
    b.disabled = true;
    if (status) status.textContent = "";
    try {
      const r = await fetch(`/v1/sessions/${encodeURIComponent(b.dataset.session)}/review-token`, {method: "POST", credentials: "same-origin"});
      const data = await r.json();
      if (!r.ok) throw new Error((data.error && data.error.message) || data.detail || r.statusText);
      window.location.assign(data.url);
    } catch (e) {
      if (status) status.textContent = " Refused: " + e.message;
      b.disabled = false;
    }
  }));
  // Back from a review page (the browser may restore this page from its cache): the buttons work again.
  window.addEventListener("pageshow", () => {
    document.querySelectorAll("button.review-open").forEach((b) => { b.disabled = false; });
  });
})();
