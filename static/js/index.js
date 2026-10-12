const userBar = document.getElementById("user-bar");

async function showUserBar() {
  // Not logged in: show the Login and Register links
  if (!localStorage.getItem("access_token")) {
    userBar.innerHTML = '<a href="/login.html">Login</a> <a href="/register.html">Register</a>';
    return;
  }

  try {
    // Logged in: ask the API who we are
    const user = await apiRequest("/users/me", "GET");

    // Show the name and role (textContent keeps the name safe from HTML injection)
    userBar.textContent = "Hi, " + user.full_name + " (" + user.role + ") ";
    const logoutButton = document.createElement("button");
    logoutButton.textContent = "Logout";
    logoutButton.addEventListener("click", function () {
      localStorage.removeItem("access_token");
      window.location.reload();
    });
    userBar.appendChild(logoutButton);
  } catch (error) {
    // A 401 already redirected to the login page, so this is some other error
    userBar.textContent = "Could not load your account: " + error.message;
  }
}

showUserBar();
