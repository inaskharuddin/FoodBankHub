(() => {
  const toggle = document.querySelector('[data-sidebar-toggle]');
  const closeArea = document.querySelector('[data-sidebar-close]');
  const setSidebar = (open) => {
    document.body.classList.toggle('sidebar-open', open);
    if (toggle) {
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
    }
  };
  toggle?.addEventListener('click', () => setSidebar(!document.body.classList.contains('sidebar-open')));
  closeArea?.addEventListener('click', () => setSidebar(false));
  document.querySelectorAll('.side-nav a').forEach((link) => link.addEventListener('click', () => setSidebar(false)));

  const date = document.querySelector('[data-today]');
  if (date) date.textContent = new Intl.DateTimeFormat(undefined, { weekday: 'short', month: 'short', day: 'numeric' }).format(new Date());

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

  document.querySelectorAll('[data-confirm]').forEach((form) => form.addEventListener('submit', (event) => {
    const question = form.getAttribute('data-confirm');
    if (question && !window.confirm(question)) event.preventDefault();
  }));

  if (window.location.hash) {
    const target = document.getElementById(decodeURIComponent(window.location.hash.slice(1)));
    if (target instanceof HTMLDetailsElement) target.open = true;
  }
})();
