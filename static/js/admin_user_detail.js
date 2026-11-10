document.addEventListener("submit", (event) => {
  const saveForm = event.target.closest("[data-admin-save-confirm]");
  if (saveForm && !window.confirm("Save these changes to the user account? Please verify the details before continuing.")) {
    event.preventDefault();
    return;
  }

  const actionForm = event.target.closest("[data-admin-action-confirm]");
  if (actionForm && !window.confirm(actionForm.dataset.adminActionConfirm)) {
    event.preventDefault();
  }
});
