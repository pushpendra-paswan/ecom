// Builds one product card (a link to the product page) for the product lists.
function buildProductCard(product) {
  // The whole card is one link to the product page
  const card = document.createElement("a");
  card.className = "product-card";
  card.href = "/product.html?id=" + encodeURIComponent(product.id);

  // The image: square, lazy loaded, alt text is the product name
  const image = document.createElement("img");
  image.className = "product-card-image";
  image.alt = product.name;
  image.loading = "lazy";
  if (product.image_url) {
    image.src = product.image_url;
  } else {
    image.src = "/static/images/placeholder.svg";
  }

  // If the image fails to load, swap in the placeholder once (clear the handler so it cannot loop)
  image.onerror = function () {
    image.onerror = null;
    image.src = "/static/images/placeholder.svg";
  };

  // The name (CSS limits it to 2 lines)
  const name = document.createElement("div");
  name.className = "product-card-name";
  name.textContent = product.name;

  // The price: the API gives paise, the page shows rupees
  const price = document.createElement("div");
  price.className = "product-card-price";
  price.textContent = "₹" + (product.price / 100).toLocaleString("en-IN", { minimumFractionDigits: product.price % 100 === 0 ? 0 : 2, maximumFractionDigits: 2 });

  // Put the parts together
  card.append(image, name, price);

  // Show a label when the product is sold out
  if (product.stock === 0) {
    const outOfStockLabel = document.createElement("div");
    outOfStockLabel.className = "product-card-out-of-stock";
    outOfStockLabel.textContent = "Out of stock";
    card.append(outOfStockLabel);
  }

  return card;
}
