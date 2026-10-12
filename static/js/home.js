// Loads the category cards and the newest products for the home page.
async function loadHomePage() {
  // Find the two areas on the page
  const categoriesArea = document.getElementById("categories-area");
  const productsArea = document.getElementById("products-area");

  // Load the categories and show one card for each
  try {
    const categories = await apiRequest("/categories", "GET");
    categoriesArea.textContent = "";

    if (categories.length === 0) {
      const emptyMessage = document.createElement("p");
      emptyMessage.className = "state-empty";
      emptyMessage.textContent = "No categories yet.";
      categoriesArea.append(emptyMessage);
    }

    const categoryGrid = document.createElement("div");
    categoryGrid.className = "category-grid";
    for (const category of categories) {
      // Each card links to the listing page for that category
      const categoryCard = document.createElement("a");
      categoryCard.className = "category-card";
      categoryCard.href = "/products.html?category=" + encodeURIComponent(category.slug);

      const categoryName = document.createElement("div");
      categoryName.className = "category-card-name";
      categoryName.textContent = category.name;

      const categoryCount = document.createElement("div");
      categoryCount.className = "category-card-count";
      categoryCount.textContent = category.product_count + (category.product_count === 1 ? " product" : " products");

      categoryCard.append(categoryName, categoryCount);
      categoryGrid.append(categoryCard);
    }
    categoriesArea.append(categoryGrid);
  } catch (error) {
    // Show the problem and a button that reloads the page
    categoriesArea.textContent = "";
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
    categoriesArea.append(errorBox);
  }

  // Load the 8 newest products and show a card for each
  try {
    const result = await apiRequest("/products?page=1&page_size=8", "GET");
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

    const productGrid = document.createElement("div");
    productGrid.className = "product-grid";
    for (const product of result.items) {
      productGrid.append(buildProductCard(product));
    }
    productsArea.append(productGrid);
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
  }
}

loadHomePage();
