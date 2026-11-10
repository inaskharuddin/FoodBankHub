(() => {
  const config = document.querySelector('#provider-tour-config');
  const tooltip = document.querySelector('[data-tour-tooltip]');
  if (!config || !tooltip) return;
  const steps = [
    { title: 'Manage inventory', text: 'Add the food items your bank currently holds and record initial quantities.', url: config.dataset.inventoryUrl, selector: '[data-tour="nav-inventory"]' },
    { title: 'Choose your supplier', text: 'Select one approved supplier. Their catalog and prices will be used for your orders.', url: config.dataset.supplierUrl, selector: '[data-tour="supplier-choice"]' },
    { title: 'Upload existing data', text: 'Choose Historical data here to add the consumption records your food bank already has. You can add only what is available; more complete and accurate history can improve forecast accuracy.', url: config.dataset.forecastUrl, selector: '[data-tour="historical-data-link"]' },
    { title: 'Add available data', text: 'Upload a CSV with the records you have, or enter estimates for only the months you know. Leave unknown months blank and add more history later.', url: config.dataset.historyUrl, selector: '[data-tour="history-upload-form"]' },
    { title: 'View your forecast', text: 'Review the 7-day and 30-day demand forecasts for each food category.', url: config.dataset.forecastChartUrl, selector: '[data-tour="forecast-chart"]' },
    { title: 'Review low-stock alerts', text: 'Open Inventory monitoring from the sidebar to review current stock and forecast shortages.', url: config.dataset.alertsUrl, selector: '[data-tour="nav-alerts"]' },
    { title: 'Create a purchase order', text: 'Open the Create purchase order button. You can order the quantity already paid for by donors, even when funding has not reached the full target.', url: config.dataset.ordersUrl, selector: 'a[data-tour="po-create"]' },
    { title: 'Confirm delivery', text: 'After the food physically arrives, confirm the delivered order here. Stock is added only once after confirmation.', url: config.dataset.deliveryUrl, selector: '[data-tour="delivery-action"]', fallback: '[data-tour="order-history"]' },
    { title: 'Print and display your reporting QR', text: 'Open this QR page, print your food bank’s unique code, and place it somewhere visible inside the food bank. Needy visitors can scan it to report the food they receive.', url: config.dataset.qrUrl, selector: '[data-tour="needy-report-qr"]' }
  ];
  const backdrop = document.querySelector('[data-tour-backdrop]');
  const spotlight = document.querySelector('[data-tour-spotlight]');
  const count = tooltip.querySelector('[data-tour-count]');
  const title = tooltip.querySelector('[data-tour-title]');
  const copy = tooltip.querySelector('[data-tour-copy]');
  const back = tooltip.querySelector('[data-tour-back]');
  const next = tooltip.querySelector('[data-tour-next]');
  let active = false;
  let index = 0;
  const currentPath = `${location.pathname}${location.hash}`;
  const routePath = (url) => { const parsed = new URL(url, location.origin); return `${parsed.pathname}${parsed.hash}`; };
  const csrf = document.querySelector('#provider-tour-csrf [name="csrfmiddlewaretoken"]')?.value || '';
  const saveComplete = () => fetch(config.dataset.completeUrl, { method: 'POST', headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' }).catch(() => {});
  const end = (completed) => {
    active = false;
    sessionStorage.removeItem('providerTourStep');
    backdrop.hidden = true; spotlight.hidden = true; tooltip.hidden = true;
    if (completed) saveComplete();
  };
  const navigateStep = (n) => {
    index = Math.max(0, Math.min(steps.length - 1, n));
    sessionStorage.setItem('providerTourStep', String(index));
    const url = steps[index].url;
    if (routePath(url).split('#')[0] !== location.pathname || (new URL(url, location.origin).hash && location.hash !== new URL(url, location.origin).hash)) {
      location.href = url;
      return;
    }
    showStep();
  };
  const placeTooltip = (rect) => {
    const margin = 14;
    const width = Math.min(410, innerWidth - 28);
    tooltip.style.width = `${width}px`;
    const below = rect.bottom + 18 + 210 < innerHeight;
    const top = below ? rect.bottom + 16 : Math.max(14, rect.top - 225);
    const left = Math.max(14, Math.min(innerWidth - width - 14, rect.left + rect.width / 2 - width / 2));
    tooltip.style.top = `${top}px`; tooltip.style.left = `${left}px`;
  };
  function showStep() {
    active = true;
    const step = steps[index];
    const target = document.querySelector(step.selector) || (step.fallback ? document.querySelector(step.fallback) : null);
    count.textContent = `STEP ${index + 1} OF ${steps.length}`;
    title.textContent = step.title; copy.textContent = step.text;
    back.disabled = index === 0;
    next.textContent = index === steps.length - 1 ? 'Finish' : 'Next';
    backdrop.hidden = false; tooltip.hidden = false;
    if (target) {
      target.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'nearest' });
      const rect = target.getBoundingClientRect();
      const pad = 7;
      spotlight.hidden = false;
      Object.assign(spotlight.style, { top: `${Math.max(4, rect.top - pad)}px`, left: `${Math.max(4, rect.left - pad)}px`, width: `${Math.min(innerWidth - Math.max(4, rect.left - pad), rect.width + pad * 2)}px`, height: `${Math.min(innerHeight - Math.max(4, rect.top - pad), rect.height + pad * 2)}px` });
      placeTooltip(rect);
    } else {
      spotlight.hidden = true;
      tooltip.style.top = '50%'; tooltip.style.left = '50%'; tooltip.style.transform = 'translate(-50%,-50%)';
    }
    tooltip.hidden = false;
    if (target) tooltip.style.transform = '';
  }
  next.addEventListener('click', () => index === steps.length - 1 ? end(true) : navigateStep(index + 1));
  back.addEventListener('click', () => { if (index > 0) navigateStep(index - 1); });
  tooltip.querySelectorAll('[data-tour-skip]').forEach((button) => button.addEventListener('click', () => end(true)));
  window.addEventListener('resize', () => { if (active) showStep(); });
  document.querySelector('[data-tour-restart-form]')?.addEventListener('submit', () => sessionStorage.removeItem('providerTourStep'));
  const saved = sessionStorage.getItem('providerTourStep');
  if (saved !== null) {
    index = Number(saved) || 0;
    if (routePath(steps[index].url).split('#')[0] === location.pathname) showStep();
  } else if (config.dataset.autoStart === 'true' && config.dataset.completed !== 'true') {
    navigateStep(0);
  }
})();
