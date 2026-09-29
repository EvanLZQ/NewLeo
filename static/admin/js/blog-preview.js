/**
 * Dual mobile/desktop live-preview panel for the Blog admin change form.
 *
 * On "Refresh Preview": reads whatever is currently typed into the form
 * (including TinyMCE's in-memory, not-yet-saved content), POSTs it as a
 * draft to /api/blog/preview, then points both iframes at the frontend's
 * hidden preview route for that draft's token. That route renders through
 * the exact same React component the live blog page uses (see
 * UserSite src/pages/BlogPreview.tsx / components/Blog/BlogContents.tsx),
 * so what's shown here is guaranteed to match what publishing will produce
 * — this panel never has its own separate rendering of the content.
 *
 * Manual refresh (not live-as-you-type) on purpose: admin.eyelovewear.com
 * and the frontend are different subdomains, so every update is a real
 * cross-origin round trip — firing one on every keystroke would be janky
 * and easy to race. A button is simple and predictable instead.
 */
(function () {
  "use strict";

  function getCookie(name) {
    var match = document.cookie.match(
      new RegExp("(?:^|; )" + name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1") + "=([^;]*)")
    );
    return match ? decodeURIComponent(match[1]) : null;
  }

  function makeToken() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    // Fallback UUID v4 for older browsers — good enough for an opaque,
    // low-stakes preview token (not used for anything security-sensitive).
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      var v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  function fieldValue(id) {
    var el = document.getElementById(id);
    return el ? el.value : "";
  }

  function getContentHtml() {
    // django-tinymce binds to the `content` textarea; TinyMCE's in-memory
    // value (not yet saved to the textarea/DB) is what we want, so read
    // straight from the editor instance instead of the textarea's .value.
    if (window.tinymce) {
      var editor = tinymce.get("id_content") || tinymce.activeEditor || tinymce.editors[0];
      if (editor) return editor.getContent();
    }
    return fieldValue("id_content");
  }

  function getCurrentImageUrl() {
    // Best-effort: the admin's default ClearableFileInput widget renders
    // the already-uploaded image as a plain "Currently: <a href=...>"
    // link near the file input — there's no fresh-upload preview here
    // (an unsubmitted <input type=file> has no fetchable URL), so a new,
    // not-yet-saved post's preview just won't show a hero image.
    var input = document.getElementById("id_home_page_img");
    if (!input) return "";
    var container = input.closest(".form-row") || input.parentElement;
    var link = container && container.querySelector("a[href]");
    return link ? link.href : "";
  }

  function setStatus(text, state) {
    var el = document.getElementById("blog-preview-status");
    if (!el) return;
    el.textContent = text;
    if (state) {
      el.setAttribute("data-state", state);
    } else {
      el.removeAttribute("data-state");
    }
  }

  function init() {
    var button = document.getElementById("blog-preview-refresh");
    var mobileFrame = document.getElementById("blog-preview-mobile");
    var desktopFrame = document.getElementById("blog-preview-desktop");
    var frontendBase = window.BLOG_PREVIEW_FRONTEND_BASE_URL;
    if (!button || !mobileFrame || !desktopFrame || !frontendBase) return;

    var token = makeToken();

    button.addEventListener("click", function () {
      button.disabled = true;
      setStatus("Refreshing…");

      var payload = {
        token: token,
        title: fieldValue("id_title"),
        category: fieldValue("id_category") || "Other",
        sub_title: fieldValue("id_sub_title"),
        brief: fieldValue("id_brief"),
        content: getContentHtml(),
        home_page_img: getCurrentImageUrl(),
      };

      fetch("/api/blog/preview", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify(payload),
      })
        .then(function (res) {
          if (!res.ok) throw new Error("HTTP " + res.status);
          return res.json();
        })
        .then(function (data) {
          var url = frontendBase.replace(/\/$/, "") + "/blogs/__preview__/" + data.token;
          mobileFrame.src = url;
          desktopFrame.src = url;
          setStatus("Updated " + new Date().toLocaleTimeString(), "ok");
        })
        .catch(function (err) {
          setStatus("Preview failed: " + err.message, "error");
        })
        .finally(function () {
          button.disabled = false;
        });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
