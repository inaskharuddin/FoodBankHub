(() => {
  const shell = document.querySelector(".provider-shell");
  const sidebar = document.querySelector("#provider-sidebar");
  const toggle = document.querySelector("[data-sidebar-toggle]");
  const scrim = document.querySelector("[data-sidebar-close]");
  if (!shell || !sidebar || !toggle || !scrim) return;
  const mobileQuery = window.matchMedia("(max-width: 760px)");

  const updateExpanded = () => {
    const expanded = mobileQuery.matches
      ? sidebar.classList.contains("is-open")
      : !shell.classList.contains("is-collapsed");
    toggle.setAttribute("aria-expanded", String(expanded));
    toggle.setAttribute("aria-label", expanded ? "Close navigation" : "Open navigation");
    toggle.setAttribute("title", expanded ? "Close navigation" : "Open navigation");
  };

  const setMobileOpen = (open) => {
    sidebar.classList.toggle("is-open", open);
    scrim.classList.toggle("is-open", open);
    document.body.classList.toggle("sidebar-open", open);
    updateExpanded();
  };

  const setDesktopCollapsed = (collapsed) => {
    shell.classList.toggle("is-collapsed", collapsed);
    try { localStorage.setItem("foodbankhub-provider-sidebar-collapsed", String(collapsed)); } catch (_) {}
    updateExpanded();
  };

  const syncForViewport = () => {
    if (mobileQuery.matches) {
      shell.classList.remove("is-collapsed");
      setMobileOpen(false);
    } else {
      setMobileOpen(false);
      let collapsed = false;
      try { collapsed = localStorage.getItem("foodbankhub-provider-sidebar-collapsed") === "true"; } catch (_) {}
      shell.classList.toggle("is-collapsed", collapsed);
      updateExpanded();
    }
  };

  toggle.addEventListener("click", () => {
    if (mobileQuery.matches) {
      setMobileOpen(!sidebar.classList.contains("is-open"));
    } else {
      setDesktopCollapsed(!shell.classList.contains("is-collapsed"));
    }
  });
  scrim.addEventListener("click", () => setMobileOpen(false));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (mobileQuery.matches) setMobileOpen(false);
      else if (!shell.classList.contains("is-collapsed")) setDesktopCollapsed(true);
    }
  });
  if (mobileQuery.addEventListener) mobileQuery.addEventListener("change", syncForViewport);
  else mobileQuery.addListener(syncForViewport);
  syncForViewport();
})();
