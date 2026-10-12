const loginForm = document.getElementById("login-form");
const errorMessage = document.getElementById("error-message");
const submitButton = document.getElementById("submit-button");

loginForm.addEventListener("submit", async function (event) {
  // Stay on the page instead of letting the browser submit the form
  event.preventDefault();

  // Hide the old error and disable the button while the request runs
  errorMessage.hidden = true;
  submitButton.disabled = true;
  submitButton.textContent = "Logging in...";

  try {
    // Ask the API for a token
    const result = await apiRequest("/auth/login", "POST", {
      email: document.getElementById("email").value,
      password: document.getElementById("password").value,
    });

    // Remember the token and go to the home page
    localStorage.setItem("access_token", result.access_token);
    window.location.href = "/";
  } catch (error) {
    // Show the error and let the user try again
    errorMessage.textContent = error.message;
    errorMessage.hidden = false;
    submitButton.disabled = false;
    submitButton.textContent = "Log in";
  }
});
