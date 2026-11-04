// Upload one track, wait for the analysis, then draw the reading with renderReading().
// No progress figures or time estimates: the server sends nothing to base them on.
(function () {
  const MAX_BYTES = 200 * 1024 * 1024;
  const ALLOWED = [".mp3", ".wav", ".aif", ".aiff", ".flac", ".m4a"];

  const form = document.getElementById("upload");
  const fields = document.getElementById("fields");
  const fileInput = document.getElementById("audio");
  const fileError = document.getElementById("audio-error");
  const chosen = document.getElementById("audio-chosen");
  const titleInput = document.getElementById("title");
  const status = document.getElementById("status");
  const errorBox = document.getElementById("error");
  const notice = document.getElementById("notice");
  const page = document.getElementById("page");

  function setFieldError(message) {
    fileError.textContent = message || "";
    fileError.hidden = !message;
    fileInput.setAttribute("aria-invalid", message ? "true" : "false");
    fileInput.closest(".file-well").classList.toggle("invalid", !!message);   // the drawn outline turns coral
  }

  function checkFile() {
    const f = fileInput.files[0];
    if (!f) return "Choose an audio file first.";
    const ext = f.name.slice(f.name.lastIndexOf(".")).toLowerCase();
    if (!ALLOWED.includes(ext)) return `“${f.name}” isn't a file type the analysis can read. Choose an MP3, WAV, AIFF, FLAC or M4A file.`;
    if (f.size === 0) return `“${f.name}” is empty. Choose the file again.`;
    if (f.size > MAX_BYTES) return `“${f.name}” is larger than 200 MB. Export a shorter or compressed version.`;
    return null;
  }

  function showError(err) {
    errorBox.replaceChildren();
    const strong = document.createElement("strong");
    strong.textContent = err.message;
    const action = document.createElement("p");
    action.textContent = err.action;
    errorBox.append(strong, action);
    if (err.details && err.details.length) {
      const ul = document.createElement("ul");
      for (const d of err.details) { const li = document.createElement("li"); li.textContent = d; ul.append(li); }
      errorBox.append(ul);
    }
    errorBox.hidden = false;
    errorBox.focus();
  }

  function setBusy(on) {
    fields.disabled = on;  // stops a second submission while one is running
    status.hidden = !on;
    form.setAttribute("aria-busy", on ? "true" : "false");
  }

  function showChosen() {
    const f = fileInput.files[0];
    chosen.hidden = !f;
    chosen.textContent = f ? `Selected: ${f.name} (${(f.size / 1048576).toFixed(1)} MB)` : "";
  }

  // hovering the file input highlights the drawn Choose File outline (CSS can't reach it from the pseudo-button)
  const well = fileInput.closest(".file-well");
  fileInput.addEventListener("mouseenter", () => well.classList.add("choose-hover"));
  fileInput.addEventListener("mouseleave", () => well.classList.remove("choose-hover"));

  fileInput.addEventListener("change", () => {
    showChosen();
    setFieldError(fileInput.files[0] ? checkFile() : null);
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (fields.disabled) return;
    errorBox.hidden = true;
    const invalid = checkFile();
    setFieldError(invalid);
    if (invalid) { fileInput.focus(); return; }

    const body = new FormData(form);  // read before disabling: disabled fields aren't submitted
    setBusy(true);
    notice.hidden = true;
    page.replaceChildren();
    try {
      const response = await fetch("/analyze", { method: "POST", body });
      let payload = null;
      try { payload = await response.json(); } catch (_) { /* not JSON: handled below */ }
      if (!response.ok || !payload || payload.error) {
        showError(payload && payload.error ? payload.error : {
          message: `The app answered with an error (${response.status}).`,
          action: "Try again. If it keeps happening, check the terminal running the app." });
        return;
      }
      if (payload.existing) {
        notice.textContent = `This file was already in your vault as ${payload.code}, so it was analysed again ` +
          "under that code. Its stored title and artist were kept.";
        notice.hidden = false;
      }
      renderReading(payload.data, payload.identity, page);
      page.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (_) {
      showError({ message: "The app didn't respond.",
                  action: "Check that the terminal running it is still open, then try again." });
    } finally {
      setBusy(false);
    }
  });

  // Session page (/reading/<code>): the track was analysed beforehand, so the reading is shown at
  // once and the upload moves after it. The artist reads the content first; the interface, if it is
  // tested at all, comes last, and nothing has to run live before they see their song.
  const session = location.pathname.match(/^\/reading\/(p\d{2,})\/?$/);
  if (session) {
    const head = document.querySelector(".app-head");
    const wordmark = head.querySelector(".wordmark");
    document.body.classList.add("session");
    head.before(wordmark, page);   // wordmark, then the reading, then the upload view as before
    fetch(`/results/${session[1]}`)
      .then(r => r.json().catch(() => null).then(payload => ({ ok: r.ok, status: r.status, payload })))
      .then(({ ok, status, payload }) => {
        if (!ok || !payload || payload.error) {
          const err = payload && payload.error ? payload.error :
            { message: `The app answered with an error (${status}).`, action: "Check the terminal running the app." };
          const box = document.createElement("div");
          box.className = "error-banner";
          box.setAttribute("role", "alert");
          page.replaceChildren(box);
          const strong = document.createElement("strong");
          strong.textContent = err.message;
          const action = document.createElement("p");
          action.textContent = err.action;
          box.append(strong, action);
          for (const d of err.details || []) { const p = document.createElement("p"); p.textContent = d; box.append(p); }
          return;
        }
        renderReading(payload.data, payload.identity, page);
      })
      .catch(() => {
        page.textContent = "The app didn't respond. Check that the terminal running it is still open, then reload.";
      });
  }
})();
