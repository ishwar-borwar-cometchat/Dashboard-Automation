/**
 * Paste this into Chrome DevTools -> Console while on the logged-in
 * CometChat Dashboard tab (https://app.cometchat.com/app/.../overview).
 *
 * It copies a JSON blob to your clipboard containing localStorage,
 * sessionStorage and any non-httpOnly cookies. Save it as storage.json
 * and feed it to utils/make_storage_state.py.
 *
 * NOTE: httpOnly session cookies are invisible to JavaScript by design.
 * If the dashboard authenticates with an httpOnly cookie, you ALSO need the
 * "Copy as cURL (bash)" export described in the README.
 */
(() => {
  const dump = (store) => {
    const out = {};
    for (let i = 0; i < store.length; i++) {
      const k = store.key(i);
      out[k] = store.getItem(k);
    }
    return out;
  };

  const cookies = document.cookie
    .split(";")
    .map((c) => c.trim())
    .filter(Boolean)
    .map((c) => {
      const idx = c.indexOf("=");
      return {
        name: c.slice(0, idx),
        value: c.slice(idx + 1),
        domain: "." + location.hostname.split(".").slice(-2).join("."),
        path: "/",
      };
    });

  const blob = {
    origin: location.origin,
    url: location.href,
    localStorage: dump(window.localStorage),
    sessionStorage: dump(window.sessionStorage),
    cookies,
  };

  const text = JSON.stringify(blob, null, 2);
  copy(text); // DevTools console helper
  console.log(
    "%cCopied to clipboard.%c Save as storage.json",
    "color:#3fb950;font-weight:bold",
    "color:inherit"
  );
  console.log(blob);
  return blob;
})();
