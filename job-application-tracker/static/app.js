document.querySelectorAll('[data-confirm-delete]').forEach(form => {
  form.addEventListener('submit', event => {
    if (!window.confirm('Delete this application? This cannot be undone.')) event.preventDefault();
  });
});
