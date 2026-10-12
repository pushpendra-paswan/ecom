// Loads one product for the product detail page.
async function loadProductPage() {
  // Find the area on the page
  const productArea = document.getElementById("product-area");

  // Read the id from the URL. It must be a positive whole number that fits the
  // database integer column (at most 2147483647), otherwise show "Product not found"
  // without calling the API.
  const urlParameters = new URLSearchParams(window.location.search);
  const idText = urlParameters.get("id");
  let product = null;
  if (idText !== null && /^[1-9][0-9]*$/.test(idText) && Number(idText) <= 2147483647) {
    try {
      // Load the product
      product = await apiRequest("/products/" + idText, "GET");
    } catch (error) {
      if (error.status !== 404) {
        // Some other problem: show it and a button that reloads the page
        productArea.textContent = "";
        const errorBox = document.createElement("div");
        errorBox.className = "state-error";
        const errorText = document.createElement("p");
        errorText.textContent = "Could not load the product: " + error.message;
        const retryButton = document.createElement("button");
        retryButton.type = "button";
        retryButton.textContent = "Try again";
        retryButton.addEventListener("click", function () {
          window.location.reload();
        });
        errorBox.append(errorText, retryButton);
        productArea.append(errorBox);
        return;
      }
    }
  }

  // A bad id, a missing product or an inactive product
  if (product === null) {
    document.title = "Product not found";
    productArea.textContent = "";
    const notFoundBox = document.createElement("div");
    notFoundBox.className = "state-empty";
    const notFoundText = document.createElement("p");
    notFoundText.textContent = "Product not found";
    const allProductsLink = document.createElement("a");
    allProductsLink.href = "/products.html";
    allProductsLink.textContent = "Back to all products";
    notFoundBox.append(notFoundText, allProductsLink);
    productArea.append(notFoundBox);
    return;
  }

  // The browser tab shows the product name
  document.title = product.name;

  // The image (with a one-time fallback to the placeholder)
  const image = document.createElement("img");
  image.className = "product-detail-image";
  image.alt = product.name;
  if (product.image_url) {
    image.src = product.image_url;
  } else {
    image.src = "/static/images/placeholder.svg";
  }
  image.onerror = function () {
    image.onerror = null;
    image.src = "/static/images/placeholder.svg";
  };

  // The name
  const name = document.createElement("h1");
  name.textContent = product.name;

  // The category, linking to the listing page for that category
  const categoryLine = document.createElement("p");
  categoryLine.className = "product-detail-meta";
  const categoryLink = document.createElement("a");
  categoryLink.href = "/products.html?category=" + encodeURIComponent(product.category.slug);
  categoryLink.textContent = product.category.name;
  categoryLine.append("Category: ", categoryLink);

  // The seller
  const sellerLine = document.createElement("p");
  sellerLine.className = "product-detail-meta";
  sellerLine.textContent = "Sold by " + product.seller.full_name;

  // The price: the API gives paise, the page shows rupees
  const price = document.createElement("p");
  price.className = "product-detail-price";
  price.textContent = "₹" + (product.price / 100).toLocaleString("en-IN", { minimumFractionDigits: product.price % 100 === 0 ? 0 : 2, maximumFractionDigits: 2 });

  // The stock status: red at 0, orange at 1 to 5, green above 5
  const stockStatus = document.createElement("p");
  if (product.stock === 0) {
    stockStatus.className = "stock-status stock-out";
    stockStatus.textContent = "Out of stock";
  } else if (product.stock <= 5) {
    stockStatus.className = "stock-status stock-low";
    stockStatus.textContent = "Only " + product.stock + " left in stock";
  } else {
    stockStatus.className = "stock-status stock-in";
    stockStatus.textContent = "In stock";
  }

  // The description (CSS keeps the line breaks)
  const description = document.createElement("div");
  description.className = "product-description";
  description.textContent = product.description;

  // Put everything on the page
  const info = document.createElement("div");
  info.className = "product-detail-info";
  info.append(name, categoryLine, sellerLine, price, stockStatus, description);

  const detail = document.createElement("div");
  detail.className = "product-detail";
  detail.append(image, info);

  productArea.textContent = "";
  productArea.append(detail);
}

loadProductPage();
