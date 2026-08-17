/**
 * CometChat Dashboard — Users page DOM scan.
 *
 * HOW TO RUN
 *   1. Open  https://app.cometchat.com/app/<APP_ID>/users  (logged in)
 *   2. DevTools (F12) -> Console
 *   3. Paste this whole file, press Enter
 *   4. It copies a JSON blob to your clipboard — paste it back in the chat
 *
 * It reads structure only: tag names, class names, placeholders, counts.
 * It does NOT read user data, tokens, or any credential values.
 */
(() => {
  const txt = (e) => ((e && e.textContent) || "").trim().replace(/\s+/g, " ");
  const cls = (e) => (e && e.className ? e.className.toString().slice(0, 70) : "");
  const modCls = (e) =>
    // CSS-module class names minus their hash suffix, e.g. style_userRow__ab12 -> style_userRow
    [...(e ? e.classList : [])]
      .map((c) => c.replace(/__[A-Za-z0-9+\-]{4,}$/, ""))
      .join(" ");

  const out = { url: location.pathname, scannedAt: new Date().toISOString() };

  // ---- 1. Page chrome -----------------------------------------------------
  out.headings = [...document.querySelectorAll("h1,h2,h3,[class*=Head],[class*=title i]")]
    .map((e) => txt(e))
    .filter((t) => t && t.length < 60)
    .slice(0, 12);

  out.buttons = [...document.querySelectorAll("button")]
    .map((b) => ({ t: txt(b).slice(0, 30), cls: cls(b), disabled: b.disabled }))
    .filter((b) => b.t || /ant-btn/.test(b.cls))
    .slice(0, 30);

  out.tabs = [...document.querySelectorAll('[role=tab], .ant-tabs-tab, [class*=tab i]')]
    .map((e) => ({ t: txt(e).slice(0, 30), cls: cls(e), active: /active|selected/i.test(cls(e)) }))
    .slice(0, 12);

  out.inputs = [...document.querySelectorAll("input, textarea")].map((i) => ({
    tag: i.tagName,
    type: i.type,
    placeholder: i.placeholder,
    name: i.name,
    cls: cls(i),
  }));

  // ---- 2. Table -----------------------------------------------------------
  const table = document.querySelector(".ant-table, table, [class*=table i]");
  if (table) {
    out.table = {
      isAntTable: !!document.querySelector(".ant-table"),
      cls: cls(table),
      headers: [...table.querySelectorAll("th")].map((th) => ({
        t: txt(th),
        sortable: !!th.querySelector("[class*=sorter]") || /sort/i.test(cls(th)),
        cls: cls(th),
      })),
      rowCount: table.querySelectorAll("tbody tr").length,
    };

    const row = table.querySelector("tbody tr");
    if (row) {
      out.firstRow = {
        cls: cls(row),
        modCls: modCls(row),
        cellCount: row.querySelectorAll("td").length,
        cells: [...row.querySelectorAll("td")].map((td) => ({
          // length only for the text — no user data echoed back
          len: txt(td).length,
          cls: cls(td),
          imgs: td.querySelectorAll("img").length,
          svgs: td.querySelectorAll("svg").length,
          buttons: td.querySelectorAll("button, [role=button]").length,
          links: td.querySelectorAll("a").length,
        })),
        actionControls: [...row.querySelectorAll("td:last-child button, td:last-child [role=button], td:last-child svg, td:last-child img")].map(
          (b) => ({
            tag: b.tagName,
            cls: cls(b),
            aria: b.getAttribute("aria-label"),
            title: b.getAttribute("title"),
            alt: b.getAttribute("alt"),
            src: (b.getAttribute("src") || "").split("/").pop(),
          })
        ),
      };
    }
  } else {
    out.table = null;
    out.emptyStateText = txt(document.querySelector("main")).slice(0, 200);
  }

  // ---- 3. Pagination ------------------------------------------------------
  const pag = document.querySelector(".ant-pagination, [class*=pagination i]");
  out.pagination = pag
    ? {
        cls: cls(pag),
        text: txt(pag).slice(0, 80),
        hasSizeChanger: !!pag.querySelector(".ant-pagination-options, [class*=size]"),
        items: pag.querySelectorAll("li").length,
      }
    : null;

  // ---- 4. Distinct CSS-module class names in the main region --------------
  const main = document.querySelector("main") || document.body;
  out.moduleClasses = [
    ...new Set(
      [...main.querySelectorAll("*")]
        .flatMap((e) => [...e.classList])
        .filter((c) => /^style_/.test(c))
        .map((c) => c.replace(/__[A-Za-z0-9+\-]{4,}$/, ""))
    ),
  ].slice(0, 80);

  // ---- 5. Anything that looks like a filter/search control ----------------
  out.filterish = [...main.querySelectorAll("[class*=filter i], [class*=search i], .ant-select, .ant-picker")]
    .map((e) => ({ tag: e.tagName, cls: cls(e), t: txt(e).slice(0, 30) }))
    .slice(0, 20);

  const blob = JSON.stringify(out, null, 1);
  try {
    copy(blob);
    console.log("%c✓ Copied to clipboard — paste it back in the chat", "color:#3fb950;font-weight:bold");
  } catch (e) {
    console.log("Select and copy the object below:");
  }
  console.log(out);
  return out;
})();
