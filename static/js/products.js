// Loads the product listing page: category links, heading, product cards and pagination.
async function loadProductsPage() {
  // Find the areas on the page
  const categoryLinksArea = document.getElementById("category-links-area");
  const pageHeading = document.getElementById("page-heading");
  const productCount = document.getElementById("product-count");
  const productsArea = document.getElementById("products-area");
  const paginationArea = document.getElementById("pagination-area");

  // Read the category slug and the page number from the URL
  const pageSize = 20;
  const urlParameters = new URLSearchParams(window.location.search);
  const categorySlug = urlParameters.get("category");
  let page = parseInt(urlParameters.get("page"), 10);
  if (!Number.isSafeInteger(page) || page < 1) {
    page = 1;
  }

  // Load the categories (needed for the links and for the heading)
  let categories = [];
  try {
    categories = await apiRequest("/categories", "GET");
  } catch (error) {
    // Show the problem and a button that reloads the page
    categoryLinksArea.textContent = "";
    productsArea.textContent = "";
    const errorBox = document.createElement("div");
    errorBox.className = "state-error";
    const errorText = document.createElement("p");
    errorText.textContent = "Could not load the categories: " + error.message;
    const retryButton = document.createElement("button");
    retryButton.type = "button";
    retryButton.textContent = "Try again";
    retryButton.addEventListener("click", function () {
      window.location.reload();
    });
    errorBox.append(errorText, retryButton);
    productsArea.append(errorBox);
    return;
  }

  // Build the row of category links: "All" first, then every category
  categoryLinksArea.textContent = "";
  const categoryLinks = document.createElement("nav");
  categoryLinks.className = "category-links";
  categoryLinks.setAttribute("aria-label", "Categories");

  const allLink = document.createElement("a");
  allLink.href = "/products.html";
  allLink.textContent = "All";
  if (!categorySlug) {
    allLink.className = "active";
    allLink.setAttribute("aria-current", "page");
  }
  categoryLinks.append(allLink);

  // Remember the current category while looping, to use its name in the heading
  let currentCategory = null;
  for (const category of categories) {
    const categoryLink = document.createElement("a");
    categoryLink.href = "/products.html?category=" + encodeURIComponent(category.slug);
    categoryLink.textContent = category.name;
    if (category.slug === categorySlug) {
      categoryLink.className = "active";
      categoryLink.setAttribute("aria-current", "page");
      currentCategory = category;
    }
    categoryLinks.append(categoryLink);
  }
  categoryLinksArea.append(categoryLinks);

  // A category in the URL that does not exist: say so and do not ask for products
  if (categorySlug && currentCategory === null) {
    pageHeading.textContent = "Category not found";
    productsArea.textContent = "";
    const notFoundBox = document.createElement("div");
    notFoundBox.className = "state-empty";
    const notFoundLink = document.createElement("a");
    notFoundLink.href = "/products.html";
    notFoundLink.textContent = "Back to all products";
    notFoundBox.append(notFoundLink);
    productsArea.append(notFoundBox);
    return;
  }

  // Set the heading: the category name, or "All products"
  if (currentCategory !== null) {
    pageHeading.textContent = currentCategory.name;
  } else {
    pageHeading.textContent = "All products";
  }

  // Load this page of products
  let result = null;
  try {
    let productsPath = "/products?page=" + page + "&page_size=" + pageSize;
    if (categorySlug) {
      productsPath = productsPath + "&category=" + encodeURIComponent(categorySlug);
    }
    result = await apiRequest(productsPath, "GET");
  } catch (error) {
    // Show the problem and a button that reloads the page
    productsArea.textContent = "";
    const errorBox = document.createElement("div");
    errorBox.className = "state-error";
    const errorText = document.createElement("p");
    errorText.textContent = "Could not load the products: " + error.message;
    const retryButton = document.createElement("button");
    retryButton.type = "button";
    retryButton.textContent = "Try again";
    retryButton.addEventListener("click", function () {
      window.location.reload();
    });
    errorBox.append(errorText, retryButton);
    productsArea.append(errorBox);
    return;
  }

  // Show the total count
  productCount.textContent = result.total + (result.total === 1 ? " product" : " products");

  // Nothing on this page (empty category, or a page number past the last page)
  productsArea.textContent = "";
  if (result.items.length === 0) {
    const emptyBox = document.createElement("div");
    emptyBox.className = "state-empty";
    const emptyText = document.createElement("p");
    emptyText.textContent = "No products found.";
    const allProductsLink = document.createElement("a");
    allProductsLink.href = "/products.html";
    allProductsLink.textContent = "Back to all products";
    emptyBox.append(emptyText, allProductsLink);
    productsArea.append(emptyBox);
    return;
  }

  // Show a card for each product
  const productGrid = document.createElement("div");
  productGrid.className = "product-grid";
  for (const product of result.items) {
    productGrid.append(buildProductCard(product));
  }
  productsArea.append(productGrid);

  // Pagination is only needed when there is more than one page
  const totalPages = Math.ceil(result.total / pageSize);
  if (totalPages <= 1) {
    return;
  }

  // Previous and Next are normal links, so the browser's back button works
  let pageLinkStart = "/products.html?";
  if (categorySlug) {
    pageLinkStart = pageLinkStart + "category=" + encodeURIComponent(categorySlug) + "&";
  }

  const pagination = document.createElement("nav");
  pagination.className = "pagination";
  pagination.setAttribute("aria-label", "Pagination");

  // Previous: a link, or plain disabled text on the first page
  let previousItem = null;
  if (page > 1) {
    previousItem = document.createElement("a");
    previousItem.href = pageLinkStart + "page=" + (page - 1);
  } else {
    previousItem = document.createElement("span");
    previousItem.className = "disabled";
  }
  previousItem.textContent = "Previous";

  const pageInfo = document.createElement("span");
  pageInfo.textContent = "Page " + page + " of " + totalPages;

  // Next: a link, or plain disabled text on the last page
  let nextItem = null;
  if (page < totalPages) {
    nextItem = document.createElement("a");
    nextItem.href = pageLinkStart + "page=" + (page + 1);
  } else {
    nextItem = document.createElement("span");
    nextItem.className = "disabled";
  }
  nextItem.textContent = "Next";

  pagination.append(previousItem, pageInfo, nextItem);
  paginationArea.append(pagination);
}

loadProductsPage();
