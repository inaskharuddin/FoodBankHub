(() => {
  const fileInput = document.querySelector('[data-csv-input]');
  const dropZone = document.querySelector('[data-drop-zone]');
  const fileName = document.querySelector('[data-file-name]');
  const updateFile = (file) => { if (fileName) fileName.textContent = file ? file.name : ''; };
  fileInput?.addEventListener('change', () => updateFile(fileInput.files?.[0]));
  if (dropZone && fileInput) {
    ['dragenter', 'dragover'].forEach((eventName) => dropZone.addEventListener(eventName, (event) => {
      event.preventDefault(); dropZone.classList.add('is-dragover');
    }));
    ['dragleave', 'drop'].forEach((eventName) => dropZone.addEventListener(eventName, (event) => {
      event.preventDefault(); dropZone.classList.remove('is-dragover');
    }));
    dropZone.addEventListener('drop', (event) => {
      const [file] = event.dataTransfer?.files || [];
      if (file && file.name.toLowerCase().endsWith('.csv')) {
        const transfer = new DataTransfer(); transfer.items.add(file); fileInput.files = transfer.files; updateFile(file);
      }
    });
    dropZone.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); fileInput.click(); } });
  }

  document.querySelectorAll('[data-product-image-form]').forEach((form) => {
    const input = form.querySelector('[data-product-image]');
    const error = form.querySelector('[data-image-error]');
    if (!input || !error) return;
    input.addEventListener('invalid', () => { error.hidden = false; input.setAttribute('aria-invalid', 'true'); });
    input.addEventListener('change', () => {
      const file = input.files?.[0];
      if (!file && !input.required) { error.hidden = true; input.removeAttribute('aria-invalid'); return; }
      const validTypes = ['image/jpeg', 'image/png', 'image/webp'];
      const valid = file && validTypes.includes(file.type) && file.size <= 5 * 1024 * 1024;
      input.setCustomValidity(valid || (!file && !input.required) ? '' : 'Choose a JPG, PNG, or WEBP image up to 5 MB.');
      error.textContent = !file ? 'Product image is required for donors to see.' : 'Choose a JPG, PNG, or WEBP image up to 5 MB.';
      error.hidden = !!valid;
      if (valid) input.removeAttribute('aria-invalid'); else input.setAttribute('aria-invalid', 'true');
    });
  });

  const salesNode = document.getElementById('supplier-sales-data');
  const canvas = document.querySelector('[data-sales-chart]');
  if (salesNode && canvas) {
    const data = JSON.parse(salesNode.textContent);
    const drawSales = () => {
      const box = canvas.getBoundingClientRect();
      if (!box.width) return;
      const ratio = window.devicePixelRatio || 1;
      const width = box.width, height = 270;
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      const ctx = canvas.getContext('2d'); ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, width, height);
      const pad = { left: 48, right: 43, top: 18, bottom: 35 };
      const plotW = width - pad.left - pad.right, plotH = height - pad.top - pad.bottom;
      const revenueMax = Math.max(1, ...data.map((d) => Number(d.revenue)));
      const unitsMax = Math.max(1, ...data.map((d) => Number(d.units)));
      ctx.font = '11px DM Sans, Arial, sans-serif'; ctx.lineWidth = 1;
      for (let line = 0; line <= 4; line += 1) {
        const y = pad.top + plotH * line / 4;
        ctx.strokeStyle = '#e8eeea'; ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
        ctx.fillStyle = '#76847c'; ctx.textAlign = 'right';
        ctx.fillText(`RM ${Math.round(revenueMax * (4 - line) / 4)}`, pad.left - 7, y + 4);
        ctx.textAlign = 'left'; ctx.fillText(String(Math.round(unitsMax * (4 - line) / 4)), width - pad.right + 8, y + 4);
      }
      const point = (value, max, i) => ({ x: pad.left + (data.length < 2 ? plotW / 2 : plotW * i / (data.length - 1)), y: pad.top + plotH * (1 - Number(value) / max) });
      const lines = [
        { key: 'revenue', max: revenueMax, color: '#0b5038' },
        { key: 'units', max: unitsMax, color: '#d5a638' },
      ];
      lines.forEach(({ key, max, color }) => {
        ctx.strokeStyle = color; ctx.lineWidth = 2.5; ctx.lineJoin = 'round'; ctx.lineCap = 'round'; ctx.beginPath();
        data.forEach((entry, i) => { const p = point(entry[key], max, i); if (!i) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y); }); ctx.stroke();
        data.forEach((entry, i) => { const p = point(entry[key], max, i); ctx.fillStyle = '#fff'; ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(p.x, p.y, 4, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); });
      });
      ctx.fillStyle = '#64746b'; ctx.textAlign = 'center';
      data.forEach((entry, i) => ctx.fillText(entry.label, point(0, 1, i).x, height - 10));
    };
    new ResizeObserver(drawSales).observe(canvas); drawSales();
  }

  const productsNode = document.getElementById('supplier-top-products-data');
  const bars = document.querySelector('[data-top-products-chart]');
  if (productsNode && bars) {
    const products = JSON.parse(productsNode.textContent);
    const max = Math.max(1, ...products.map((row) => Number(row.quantity)));
    products.forEach((row) => {
      const line = document.createElement('div'); line.className = 'top-product-row';
      const heading = document.createElement('div'); heading.className = 'top-product-heading';
      const name = document.createElement('strong'); name.textContent = row['product__item__name'];
      const count = document.createElement('span'); count.textContent = `${row.quantity} ${row['product__item__unit']}`;
      heading.append(name, count);
      const track = document.createElement('div'); track.className = 'top-product-track';
      const fill = document.createElement('span'); fill.style.width = `${Number(row.quantity) / max * 100}%`; track.append(fill);
      line.append(heading, track); bars.append(line);
    });
  }

  if (window.location.hash) {
    const target = document.getElementById(decodeURIComponent(window.location.hash.slice(1)));
    if (target instanceof HTMLDetailsElement) target.open = true;
  }
})();

(() => {
  const config = document.querySelector('#supplier-tour-config');
  const tooltip = document.querySelector('[data-tour-tooltip]');
  if (!config || !tooltip) return;
  const steps = [
    { title: 'Dashboard overview', text: 'Your dashboard shows the latest sales and payout trend, best-selling items, and provider activity.', url: config.dataset.dashboardUrl, selector: '[data-tour="supplier-performance"]' },
    { title: 'Product catalogue', text: 'Open Products to add items, update prices and stock, or hide items that are unavailable.', url: config.dataset.productsUrl, selector: '[data-tour="supplier-nav-products"]' },
    { title: 'Add a catalog item', text: 'Use Add product to enter a food name, price, and stock. Each item needs a clear photo before it can be shown to donors.', url: config.dataset.productsUrl, selector: '[data-tour="supplier-add-entry"]' },
    { title: 'Add a product photo', text: 'Each catalog item needs a clear food photo. Donors see this exact image when browsing a provider’s needs.', url: config.dataset.addProductUrl, selector: '[data-tour="supplier-image-field"]' },
    { title: 'Bulk upload products', text: 'Choose Upload CSV to add several catalog items at once. Every row needs a working Image_URL.', url: config.dataset.productsUrl, selector: '[data-tour="supplier-csv-entry"]' },
    { title: 'Add images with CSV', text: 'Upload a CSV with the Image_URL column. Rows with missing or invalid images are reported and not added.', url: config.dataset.uploadUrl, selector: '[data-drop-zone]' },
    { title: 'Purchase orders', text: 'Review provider requests here. Open an order to accept it or reject it with a reason, then update shipping and delivery.', url: config.dataset.ordersUrl, selector: '[data-tour="supplier-order-filters"]' },
    { title: 'Payouts and invoices', text: 'Track confirmed deliveries waiting for payment, review payout history, and download order invoices.', url: config.dataset.payoutsUrl, selector: '.tabs' },
    { title: 'Provider panel', text: 'See the food banks that selected your supplier catalog and can place purchase orders.', url: config.dataset.panelUrl, selector: '[data-tour="supplier-panel-content"]' },
    { title: 'Profile and help', text: 'Manage editable business contact details here. Use Restart dashboard guide whenever you want to replay this tour.', url: config.dataset.profileUrl, selector: '.supplier-profile-form' },
  ];
  const backdrop = document.querySelector('[data-tour-backdrop]');
  const spotlight = document.querySelector('[data-tour-spotlight]');
  const count = tooltip.querySelector('[data-tour-count]');
  const title = tooltip.querySelector('[data-tour-title]');
  const copy = tooltip.querySelector('[data-tour-copy]');
  const back = tooltip.querySelector('[data-tour-back]');
  const next = tooltip.querySelector('[data-tour-next]');
  const csrf = document.querySelector('#supplier-tour-csrf [name="csrfmiddlewaretoken"]')?.value || '';
  const stepKey = 'supplierTourStep';
  const startedKey = 'supplierTourStarted';
  let index = 0;
  let active = false;
  const route = (url) => new URL(url, location.origin);
  const saveComplete = () => fetch(config.dataset.completeUrl, { method: 'POST', headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' }).catch(() => {});
  const end = () => { active = false; sessionStorage.removeItem(stepKey); sessionStorage.removeItem(startedKey); backdrop.hidden = true; spotlight.hidden = true; tooltip.hidden = true; saveComplete(); };
  const show = () => {
    active = true;
    const step = steps[index];
    const target = document.querySelector(step.selector);
    count.textContent = `STEP ${index + 1} OF ${steps.length}`;
    title.textContent = step.title; copy.textContent = step.text;
    back.disabled = index === 0;
    next.textContent = index === steps.length - 1 ? 'Finish' : 'Next';
    backdrop.hidden = false; tooltip.hidden = false; tooltip.style.transform = '';
    if (!target) { spotlight.hidden = true; tooltip.style.top = '50%'; tooltip.style.left = '50%'; tooltip.style.transform = 'translate(-50%,-50%)'; return; }
    target.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'nearest' });
    const rect = target.getBoundingClientRect(), pad = 7;
    spotlight.hidden = false;
    Object.assign(spotlight.style, { top: `${Math.max(4, rect.top - pad)}px`, left: `${Math.max(4, rect.left - pad)}px`, width: `${Math.min(innerWidth - Math.max(4, rect.left - pad), rect.width + pad * 2)}px`, height: `${Math.min(innerHeight - Math.max(4, rect.top - pad), rect.height + pad * 2)}px` });
    const width = Math.min(410, innerWidth - 28); tooltip.style.width = `${width}px`;
    const top = rect.bottom + 235 < innerHeight ? rect.bottom + 16 : Math.max(12, rect.top - 235);
    tooltip.style.top = `${top}px`;
    tooltip.style.left = `${Math.max(14, Math.min(innerWidth - width - 14, rect.left + rect.width / 2 - width / 2))}px`;
  };
  const navigate = (stepIndex) => {
    index = Math.max(0, Math.min(steps.length - 1, stepIndex));
    sessionStorage.setItem(stepKey, String(index));
    sessionStorage.setItem(startedKey, 'true');
    const target = route(steps[index].url);
    if (target.pathname !== location.pathname) { location.href = target.href; return; }
    show();
  };
  next.addEventListener('click', () => index === steps.length - 1 ? end() : navigate(index + 1));
  back.addEventListener('click', () => { if (index > 0) navigate(index - 1); });
  tooltip.querySelectorAll('[data-tour-skip]').forEach((button) => button.addEventListener('click', end));
  window.addEventListener('resize', () => { if (active) show(); });
  document.querySelector('[data-tour-restart-form]')?.addEventListener('submit', () => { sessionStorage.removeItem(stepKey); sessionStorage.removeItem(startedKey); });
  const saved = sessionStorage.getItem(stepKey);
  if (saved !== null && sessionStorage.getItem(startedKey) === 'true') navigate(Number(saved) || 0);
  else if (config.dataset.autoStart === 'true' && config.dataset.completed !== 'true') navigate(0);
})();
