// The one function every page uses to talk to the API.
// It sends JSON, adds the login token, and returns the parsed JSON.
async function apiRequest(path, method, body) {
  // Build the headers. Add the token if the user is logged in.
  const headers = {};
  const token = localStorage.getItem("access_token");
  if (token) {
    headers["Authorization"] = "Bearer " + token;
  }

  // Build the fetch options. Only send a body when there is one.
  const options = { method: method || "GET", headers: headers };
  if (body !== undefined && body !== null) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  // Send the request
  const response = await fetch(path, options);

  // Success: 204 has no body, everything else is JSON
  if (response.ok) {
    if (response.status === 204) {
      return null;
    }
    return await response.json();
  }

  // Error: read the JSON body if there is one
  let errorBody = null;
  try {
    errorBody = await response.json();
  } catch (error) {
    errorBody = null;
  }

  // An expired or invalid token: forget it. Only pages that need a logged-in user
  // (body has data-requires-login="true") are sent to the login page.
  // (A 401 from /auth/login only means a wrong password, so it is shown as a normal error.)
  if (response.status === 401 && path !== "/auth/login") {
    localStorage.removeItem("access_token");
    if (document.body.getAttribute("data-requires-login") === "true") {
      window.location.href = "/login.html";
    }
    throw new Error("Please log in again");
  }

  // Turn the error into one readable message
  let message = "Something went wrong (status " + response.status + ")";
  if (errorBody && typeof errorBody.detail === "string") {
    message = errorBody.detail;
  } else if (errorBody && Array.isArray(errorBody.detail)) {
    // 422: a list of {loc, msg}. Join them into one line like "email: value is not a valid email".
    const parts = [];
    for (const problem of errorBody.detail) {
      const fieldName = problem.loc[problem.loc.length - 1];
      parts.push(fieldName + ": " + problem.msg);
    }
    message = parts.join("; ");
  }
  // Keep the status code on the error so pages can tell a 404 from other problems
  const apiError = new Error(message);
  apiError.status = response.status;
  throw apiError;
}
