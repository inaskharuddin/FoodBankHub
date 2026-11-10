(() => {
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
  document.querySelectorAll("form[data-confirm-supplier]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const selector = form.querySelector("select[name='supplier_id']");
      if (!selector || selector.value === form.dataset.currentSupplier) return;
      const supplierName = selector.selectedOptions[0]?.textContent.trim() || "the selected supplier";
      if (!window.confirm(`Change your supplier to ${supplierName}? Inventory prices and donor need targets will follow its catalog.`)) {
        event.preventDefault();
      }
    });
  });
  document.querySelector("[data-print-month]")?.addEventListener("click", () => window.print());

  document.querySelectorAll("[data-forecast-carousel]").forEach((carousel) => {
    const track = carousel.querySelector("[data-forecast-track]");
    const slides = Array.from(track?.children || []);
    const previous = carousel.querySelector("[data-forecast-previous]");
    const next = carousel.querySelector("[data-forecast-next]");
    const counter = carousel.querySelector("[data-forecast-counter]");
    if (!track || slides.length < 2 || !previous || !next) return;

    let activeIndex = 0;
    let scheduled = false;
    const findActiveIndex = () => {
      const trackCenter = track.getBoundingClientRect().left + track.clientLeft + track.clientWidth / 2;
      return slides.reduce((closest, slide, index) => {
        const rect = slide.getBoundingClientRect();
        const distance = Math.abs(rect.left + rect.width / 2 - trackCenter);
        return distance < closest.distance ? { index, distance } : closest;
      }, { index: 0, distance: Infinity }).index;
    };
    const updateControls = () => {
      scheduled = false;
      activeIndex = findActiveIndex();
      previous.disabled = activeIndex === 0;
      next.disabled = activeIndex === slides.length - 1;
      if (counter) counter.textContent = `${activeIndex + 1} of ${slides.length}`;
    };
    const scheduleUpdate = () => {
      if (!scheduled) {
        scheduled = true;
        window.requestAnimationFrame(updateControls);
      }
    };
    const showSlide = (index) => {
      const target = slides[Math.max(0, Math.min(index, slides.length - 1))];
      const offset = target.getBoundingClientRect().left - track.getBoundingClientRect().left - track.clientLeft;
      track.scrollTo({ left: track.scrollLeft + offset, behavior: "smooth" });
    };

    previous.addEventListener("click", () => showSlide(findActiveIndex() - 1));
    next.addEventListener("click", () => showSlide(findActiveIndex() + 1));
    track.addEventListener("scroll", scheduleUpdate, { passive: true });
    track.addEventListener("keydown", (event) => {
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        showSlide(findActiveIndex() + (event.key === "ArrowRight" ? 1 : -1));
      }
    });
    window.addEventListener("resize", scheduleUpdate);
    updateControls();
  });

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
