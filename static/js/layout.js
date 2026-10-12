// The site name is defined once, here.
const SITE_NAME = "ShopEasy";

// Fills the header and footer that every page has.
async function showLayout() {
  // Find the two containers on the page
  const siteHeader = document.getElementById("site-header");
  const siteFooter = document.getElementById("site-footer");

  // Build the navbar: site name, links, and an empty place for the user area
  const navbar = document.createElement("div");
  navbar.className = "navbar container";

  const brandLink = document.createElement("a");
  brandLink.className = "navbar-brand";
  brandLink.href = "/";
  brandLink.textContent = SITE_NAME;

  const navLinks = document.createElement("nav");
  navLinks.className = "navbar-links";
  const homeLink = document.createElement("a");
  homeLink.href = "/";
  homeLink.textContent = "Home";
  const productsLink = document.createElement("a");
  productsLink.href = "/products.html";
  productsLink.textContent = "All Products";
  navLinks.append(homeLink, productsLink);

  // The search form: a plain GET form to the products page. It only sends q, so a new
  // search never keeps the category or the filters.
  const searchForm = document.createElement("form");
  searchForm.className = "navbar-search";
  searchForm.method = "get";
  searchForm.action = "/products.html";
  searchForm.setAttribute("role", "search");
  const searchInput = document.createElement("input");
  searchInput.type = "search";
  searchInput.name = "q";
  searchInput.maxLength = 100;
  searchInput.placeholder = "Search products";
  searchInput.setAttribute("aria-label", "Search products");
  const searchButton = document.createElement("button");
  searchButton.type = "submit";
  searchButton.textContent = "Search";
  searchForm.append(searchInput, searchButton);

  // Show the current search text in the input (the value property, never innerHTML)
  const currentQuery = new URLSearchParams(window.location.search).get("q");
  if (currentQuery !== null) {
    searchInput.value = currentQuery;
  }

  const userArea = document.createElement("div");
  userArea.className = "navbar-user";

  navbar.append(brandLink, navLinks, searchForm, userArea);
  siteHeader.append(navbar);

  // Build the footer: site name, current year and a link to Home
  const footerContent = document.createElement("div");
  footerContent.className = "footer-content container";
  const footerText = document.createElement("span");
  footerText.textContent = "© " + new Date().getFullYear() + " " + SITE_NAME;
  const footerHomeLink = document.createElement("a");
  footerHomeLink.href = "/";
  footerHomeLink.textContent = "Home";
  footerContent.append(footerText, footerHomeLink);
  siteFooter.append(footerContent);

  // Ask the API who is logged in, but only if there is a token
  let user = null;
  if (localStorage.getItem("access_token")) {
    try {
      user = await apiRequest("/users/me", "GET");
    } catch (error) {
      // A stale or invalid token (apiRequest already removed it) or a failed request:
      // fall back to the logged-out navbar
      user = null;
    }
  }

  // Logged out: show Login and Register
  if (user === null) {
    const loginLink = document.createElement("a");
    loginLink.href = "/login.html";
    loginLink.textContent = "Login";
    const registerLink = document.createElement("a");
    registerLink.href = "/register.html";
    registerLink.textContent = "Register";
    userArea.append(loginLink, registerLink);
    return;
  }

  // Logged in: show the name and a Logout button (textContent keeps the name safe)
  const greeting = document.createElement("span");
  greeting.textContent = "Hi, " + user.full_name;
  const logoutButton = document.createElement("button");
  logoutButton.type = "button";
  logoutButton.textContent = "Logout";
  logoutButton.addEventListener("click", function () {
    localStorage.removeItem("access_token");
    window.location.reload();
  });
  userArea.append(greeting, logoutButton);
}

showLayout();
