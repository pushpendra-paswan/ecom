const registerForm = document.getElementById("register-form");
const errorMessage = document.getElementById("error-message");
const submitButton = document.getElementById("submit-button");

registerForm.addEventListener("submit", async function (event) {
  // Stay on the page instead of letting the browser submit the form
  event.preventDefault();

  // Hide the old error and disable the button while the requests run
  errorMessage.hidden = true;
  submitButton.disabled = true;
  submitButton.textContent = "Creating account...";

  try {
    // Create the account
    const email = document.getElementById("email").value;
    const password = document.getElementById("password").value;
    await apiRequest("/auth/register", "POST", {
      full_name: document.getElementById("full-name").value,
      email: email,
      password: password,
      role: document.getElementById("role").value,
    });

    // Log in with the same details to get a token
    const result = await apiRequest("/auth/login", "POST", {
      email: email,
      password: password,
    });

    // Remember the token and go to the home page
    localStorage.setItem("access_token", result.access_token);
    window.location.href = "/";
  } catch (error) {
    // Show the error and let the user try again
    errorMessage.textContent = error.message;
    errorMessage.hidden = false;
    submitButton.disabled = false;
    submitButton.textContent = "Register";
  }
});
