// Loads the product listing page: sidebar (categories and filters), heading, cards and pagination.
// The page URL holds prices in RUPEES. The API takes PAISE, so they are converted before the call.
async function loadProductsPage() {
  // Find the areas on the page
  const categoryLinksArea = document.getElementById("category-links-area");
  const filterForm = document.getElementById("filter-form");
  const filterQuery = document.getElementById("filter-q");
  const filterCategory = document.getElementById("filter-category");
  const filterMinPrice = document.getElementById("filter-min-price");
  const filterMaxPrice = document.getElementById("filter-max-price");
  const filterInStock = document.getElementById("filter-in-stock");
  const filterSort = document.getElementById("filter-sort");
  const clearFiltersLink = document.getElementById("clear-filters-link");
  const pageHeading = document.getElementById("page-heading");
  const productCount = document.getElementById("product-count");
  const filterMessageArea = document.getElementById("filter-message-area");
  const productsArea = document.getElementById("products-area");
  const paginationArea = document.getElementById("pagination-area");

  // Read every parameter from the URL (prices are in rupees here)
  const pageSize = 20;
  const urlParameters = new URLSearchParams(window.location.search);
  const searchText = (urlParameters.get("q") || "").trim();
  const categorySlug = urlParameters.get("category");
  const minPriceText = (urlParameters.get("min_price") || "").trim();
  const maxPriceText = (urlParameters.get("max_price") || "").trim();
  const inStockOnly = urlParameters.get("in_stock") === "1";
  let page = parseInt(urlParameters.get("page"), 10);
  if (!Number.isSafeInteger(page) || page < 1) {
    page = 1;
  }

  // Pick the sort. An unknown value is ignored. Relevance needs a search text.
  const sortFromUrl = urlParameters.get("sort");
  const allowedSorts = ["relevance", "newest", "price_asc", "price_desc", "name_asc"];
  let sort = searchText ? "relevance" : "newest";
  if (allowedSorts.includes(sortFromUrl)) {
    sort = sortFromUrl;
  }
  if (sort === "relevance" && !searchText) {
    sort = "newest";
  }

  // Fill the filter form from the URL (value and checked properties, never innerHTML).
  // The hidden inputs are switched off when empty, so they are not sent.
  filterQuery.value = searchText;
  filterQuery.disabled = !searchText;
  filterCategory.value = categorySlug || "";
  filterCategory.disabled = !categorySlug;
  filterMinPrice.value = minPriceText;
  filterMaxPrice.value = maxPriceText;
  filterInStock.checked = inStockOnly;

  // Build the sort dropdown. Relevance is only offered when there is a search text.
  const sortChoices = [
    ["relevance", "Relevance"],
    ["newest", "Newest"],
    ["price_asc", "Price: Low to High"],
    ["price_desc", "Price: High to Low"],
    ["name_asc", "Name: A to Z"],
  ];
  for (const sortChoice of sortChoices) {
    if (sortChoice[0] === "relevance" && !searchText) {
      continue;
    }
    const sortOption = document.createElement("option");
    sortOption.value = sortChoice[0];
    sortOption.textContent = sortChoice[1];
    sortOption.selected = sortChoice[0] === sort;
    filterSort.append(sortOption);
  }

  // Choosing a sort sends the form straight away
  filterSort.addEventListener("change", function () {
    filterForm.requestSubmit();
  });

  // "Clear filters" keeps only the search text and the category
  const clearParameters = new URLSearchParams();
  if (searchText) {
    clearParameters.set("q", searchText);
  }
  if (categorySlug) {
    clearParameters.set("category", categorySlug);
  }
  let clearFiltersHref = "/products.html";
  if (clearParameters.toString() !== "") {
    clearFiltersHref = clearFiltersHref + "?" + clearParameters.toString();
  }
  clearFiltersLink.setAttribute("href", clearFiltersHref);

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

  // Build the category links: "All" first, then every category.
  // Every link keeps the search, the price filters, in stock and the sort, but not the page.
  categoryLinksArea.textContent = "";
  const categoryLinks = document.createElement("nav");
  categoryLinks.className = "category-links";
  categoryLinks.setAttribute("aria-label", "Categories");

  const allLinkParameters = new URLSearchParams();
  if (searchText) {
    allLinkParameters.set("q", searchText);
  }
  if (minPriceText) {
    allLinkParameters.set("min_price", minPriceText);
  }
  if (maxPriceText) {
    allLinkParameters.set("max_price", maxPriceText);
  }
  if (inStockOnly) {
    allLinkParameters.set("in_stock", "1");
  }
  if (sortFromUrl) {
    allLinkParameters.set("sort", sort);
  }
  let allLinkHref = "/products.html";
  if (allLinkParameters.toString() !== "") {
    allLinkHref = allLinkHref + "?" + allLinkParameters.toString();
  }
  const allLink = document.createElement("a");
  allLink.setAttribute("href", allLinkHref);
  allLink.textContent = "All";
  if (!categorySlug) {
    allLink.className = "active";
    allLink.setAttribute("aria-current", "page");
  }
  categoryLinks.append(allLink);

  // Remember the current category while looping, to use its name in the heading
  let currentCategory = null;
  for (const category of categories) {
    const categoryLinkParameters = new URLSearchParams();
    categoryLinkParameters.set("category", category.slug);
    if (searchText) {
      categoryLinkParameters.set("q", searchText);
    }
    if (minPriceText) {
      categoryLinkParameters.set("min_price", minPriceText);
    }
    if (maxPriceText) {
      categoryLinkParameters.set("max_price", maxPriceText);
    }
    if (inStockOnly) {
      categoryLinkParameters.set("in_stock", "1");
    }
    if (sortFromUrl) {
      categoryLinkParameters.set("sort", sort);
    }
    const categoryLink = document.createElement("a");
    categoryLink.setAttribute("href", "/products.html?" + categoryLinkParameters.toString());
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

  // Set the heading. The search text is user input, so it only goes in with textContent.
  if (searchText) {
    let headingText = 'Results for "' + searchText + '"';
    if (currentCategory !== null) {
      headingText = headingText + " in " + currentCategory.name;
    }
    pageHeading.textContent = headingText;
  } else if (currentCategory !== null) {
    pageHeading.textContent = currentCategory.name;
  } else {
    pageHeading.textContent = "All products";
  }

  // Check the price filters before calling the API. Rupees from the URL become paise.
  let minPrice = null;
  let maxPrice = null;
  let priceProblem = "";
  const largestPaise = 1000000000;
  if (minPriceText !== "") {
    const minRupees = Number(minPriceText);
    if (!Number.isFinite(minRupees)) {
      priceProblem = "The minimum price must be a number.";
    } else if (minRupees < 0) {
      priceProblem = "The minimum price cannot be negative.";
    } else if (Math.round(minRupees * 100) > largestPaise) {
      priceProblem = "The minimum price is too large.";
    } else {
      minPrice = Math.round(minRupees * 100);
    }
  }
  if (priceProblem === "" && maxPriceText !== "") {
    const maxRupees = Number(maxPriceText);
    if (!Number.isFinite(maxRupees)) {
      priceProblem = "The maximum price must be a number.";
    } else if (maxRupees < 0) {
      priceProblem = "The maximum price cannot be negative.";
    } else if (Math.round(maxRupees * 100) > largestPaise) {
      priceProblem = "The maximum price is too large.";
    } else {
      maxPrice = Math.round(maxRupees * 100);
    }
  }
  if (priceProblem === "" && minPrice !== null && maxPrice !== null && minPrice > maxPrice) {
    priceProblem = "The minimum price cannot be higher than the maximum price.";
  }

  // A price problem: show it and do not call the API
  if (priceProblem !== "") {
    filterMessageArea.textContent = "";
    const priceMessage = document.createElement("p");
    priceMessage.className = "error-message";
    priceMessage.setAttribute("role", "alert");
    priceMessage.textContent = priceProblem;
    filterMessageArea.append(priceMessage);
    productsArea.textContent = "";
    return;
  }

  // Load this page of products (everything is encoded by URLSearchParams)
  let result = null;
  try {
    const apiParameters = new URLSearchParams();
    apiParameters.set("page", page);
    apiParameters.set("page_size", pageSize);
    apiParameters.set("sort", sort);
    if (searchText) {
      apiParameters.set("q", searchText);
    }
    if (categorySlug) {
      apiParameters.set("category", categorySlug);
    }
    if (minPrice !== null) {
      apiParameters.set("min_price", minPrice);
    }
    if (maxPrice !== null) {
      apiParameters.set("max_price", maxPrice);
    }
    if (inStockOnly) {
      apiParameters.set("in_stock", "true");
    }
    result = await apiRequest("/products?" + apiParameters.toString(), "GET");
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
  productCount.textContent = result.total + (result.total === 1 ? " result" : " results");

  // Nothing on this page (no match, or a page number past the last page)
  productsArea.textContent = "";
  if (result.items.length === 0) {
    const emptyBox = document.createElement("div");
    emptyBox.className = "state-empty";
    const emptyText = document.createElement("p");
    emptyText.textContent = "No products found.";
    const emptyLink = document.createElement("a");
    if (minPriceText || maxPriceText || inStockOnly) {
      // Filters are set: offer to remove them (the search and the category stay)
      emptyLink.setAttribute("href", clearFiltersHref);
      emptyLink.textContent = "Clear filters";
    } else {
      emptyLink.href = "/products.html";
      emptyLink.textContent = "Back to all products";
    }
    emptyBox.append(emptyText, emptyLink);
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

  const pagination = document.createElement("nav");
  pagination.className = "pagination";
  pagination.setAttribute("aria-label", "Pagination");

  // Previous: a link that keeps every parameter, or plain disabled text on the first page
  let previousItem = null;
  if (page > 1) {
    const previousParameters = new URLSearchParams();
    if (searchText) {
      previousParameters.set("q", searchText);
    }
    if (categorySlug) {
      previousParameters.set("category", categorySlug);
    }
    if (minPriceText) {
      previousParameters.set("min_price", minPriceText);
    }
    if (maxPriceText) {
      previousParameters.set("max_price", maxPriceText);
    }
    if (inStockOnly) {
      previousParameters.set("in_stock", "1");
    }
    if (sortFromUrl) {
      previousParameters.set("sort", sort);
    }
    previousParameters.set("page", page - 1);
    previousItem = document.createElement("a");
    previousItem.setAttribute("href", "/products.html?" + previousParameters.toString());
  } else {
    previousItem = document.createElement("span");
    previousItem.className = "disabled";
  }
  previousItem.textContent = "Previous";

  const pageInfo = document.createElement("span");
  pageInfo.textContent = "Page " + page + " of " + totalPages;

  // Next: a link that keeps every parameter, or plain disabled text on the last page
  let nextItem = null;
  if (page < totalPages) {
    const nextParameters = new URLSearchParams();
    if (searchText) {
      nextParameters.set("q", searchText);
    }
    if (categorySlug) {
      nextParameters.set("category", categorySlug);
    }
    if (minPriceText) {
      nextParameters.set("min_price", minPriceText);
    }
    if (maxPriceText) {
      nextParameters.set("max_price", maxPriceText);
    }
    if (inStockOnly) {
      nextParameters.set("in_stock", "1");
    }
    if (sortFromUrl) {
      nextParameters.set("sort", sort);
    }
    nextParameters.set("page", page + 1);
    nextItem = document.createElement("a");
    nextItem.setAttribute("href", "/products.html?" + nextParameters.toString());
  } else {
    nextItem = document.createElement("span");
    nextItem.className = "disabled";
  }
  nextItem.textContent = "Next";

  pagination.append(previousItem, pageInfo, nextItem);
  paginationArea.append(pagination);
}

loadProductsPage();
