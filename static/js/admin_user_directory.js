document.addEventListener("submit", (event) => {
  const deleteForm = event.target.closest("[data-user-delete-form]");
  if (deleteForm) {
    const row = deleteForm.closest("[data-user-row]");
    const name = row.dataset.accountName;
    if (!window.confirm(`Delete ${name}'s account? This may also permanently delete linked profiles, orders, reports, and donations. This action cannot be undone.`)) {
      event.preventDefault();
    }
  }
});
