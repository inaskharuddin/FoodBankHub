(() => {
  document.querySelectorAll('[data-quantity-step]').forEach((button) => {
    button.addEventListener('click', () => {
      const input = button.closest('.quantity-pill')?.querySelector('input[type="number"]');
      if (!input) return;
      const min = Number(input.min || 1), max = Number(input.max || Number.MAX_SAFE_INTEGER);
      input.value = String(Math.max(min, Math.min(max, Number(input.value || min) + Number(button.dataset.quantityStep))));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    });
  });
})();
