(() => {
  const forms = Array.from(document.querySelectorAll('form:not([data-skip-validation])'));
  const submitControls = (form) => Array.from(form.querySelectorAll('button:not([type]), button[type="submit"], input[type="submit"]'));

  function errorFor(control) {
    if (!control.id) control.id = `form-control-${Math.random().toString(36).slice(2, 10)}`;
    let note = control.parentElement.querySelector(`.field-validation-message[data-for="${control.id}"]`);
    if (!note) {
      note = document.createElement('span');
      note.className = 'field-validation-message';
      note.dataset.for = control.id;
      note.setAttribute('aria-live', 'polite');
      control.insertAdjacentElement('afterend', note);
    }
    note.textContent = `⚠ ${control.validationMessage || 'Please check this field.'}`;
    control.classList.add('field-invalid');
    control.setAttribute('aria-invalid', 'true');
  }

  function clearError(control) {
    control.classList.remove('field-invalid');
    control.removeAttribute('aria-invalid');
    const note = control.parentElement?.querySelector(`.field-validation-message[data-for="${control.id}"]`);
    if (note) note.remove();
  }

  forms.forEach((form) => {
    const controls = Array.from(form.querySelectorAll('input, select, textarea')).filter((control) => !['hidden', 'submit', 'button', 'reset'].includes(control.type));
    const buttons = submitControls(form);
    const lockUntilValid = form.matches('.account-register-form, .login-form');
    const managedButtons = buttons.filter((button) => !button.disabled);
    const hint = document.createElement('div');
    hint.className = 'form-validation-summary';
    hint.setAttribute('role', 'status');
    hint.setAttribute('aria-live', 'polite');
    if (lockUntilValid && managedButtons.length) form.insertBefore(hint, managedButtons[0]);
    const updateButtons = () => {
      const valid = controls.every((control) => control.validity.valid);
      if (lockUntilValid && managedButtons.length) {
        hint.hidden = valid;
        hint.textContent = valid ? '' : '⚠ Please check the highlighted fields. Complete all required fields to continue.';
      }
      if (lockUntilValid) managedButtons.forEach((button) => {
          button.disabled = !valid;
          button.setAttribute('aria-disabled', String(!valid));
        });
    };

    controls.forEach((control) => {
      control.addEventListener('invalid', () => errorFor(control), true);
      control.addEventListener('blur', () => {
        if (control.value || control.required) {
          if (control.validity.valid) clearError(control);
          else errorFor(control);
        }
      });
      control.addEventListener('input', () => {
        if (control.validity.valid) clearError(control);
        else if (control.classList.contains('field-invalid')) errorFor(control);
        updateButtons();
      });
      control.addEventListener('change', () => {
        if (control.validity.valid) clearError(control);
        updateButtons();
      });
    });

    form.addEventListener('submit', (event) => {
      if (!form.checkValidity()) {
        event.preventDefault();
        form.reportValidity();
        return;
      }
      if (lockUntilValid) managedButtons.forEach((button) => {
          button.disabled = true;
          button.setAttribute('aria-disabled', 'true');
        });
    });
    updateButtons();
  });
})();
