(() => {
  const form = document.querySelector('form.form-page');
  const next = form.elements.new_password;
  const confirmation = form.elements.confirm_password;
  function validateConfirmation() {
    confirmation.setCustomValidity(confirmation.value && confirmation.value !== next.value
      ? 'The new passwords do not match.' : '');
  }
  next.addEventListener('input', validateConfirmation);
  confirmation.addEventListener('input', validateConfirmation);
  const toggle = document.getElementById('show-passwords');
  toggle.addEventListener('click', () => {
    const show = toggle.getAttribute('aria-pressed') !== 'true';
    for (const field of [form.elements.current_password, next, confirmation]) {
      field.type = show ? 'text' : 'password';
    }
    toggle.setAttribute('aria-pressed', String(show));
    toggle.textContent = show ? 'Hide Passwords' : 'Show Passwords';
  });
})();
