/* =====================================================================
   Small helper for calling the Flask JSON API (api.py).
   - Sends the CSRF token from <meta name="csrf-token"> in a header.
   - Returns the parsed JSON, or throws an Error whose message is the
     server's explanation (e.g. "Only draft estimates can be deleted.").
   Used by estimates.js and invoices.js.
   ===================================================================== */
async function apiRequest(method, url, data) {
  const tokenTag = document.querySelector('meta[name="csrf-token"]');
  const response = await fetch(url, {
    method,
    credentials: "same-origin",
    headers: {
      "Accept": "application/json",
      "Content-Type": "application/json",
      "X-CSRF-Token": tokenTag ? tokenTag.content : "",
    },
    body: data === undefined ? undefined : JSON.stringify(data),
  });

  if (response.status === 204) return null;

  let payload = null;
  try { payload = await response.json(); } catch (_) { /* not JSON */ }

  if (!response.ok) {
    const error = new Error((payload && payload.error) || `Something went wrong (error ${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return payload;
}
