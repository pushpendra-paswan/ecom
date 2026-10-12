// The product form: creates a product, or edits one when the URL has ?id=
async function loadProductFormPage() {
  const formHeading = document.getElementById("form-heading");
  const formStatus = document.getElementById("form-status");
  const productForm = document.getElementById("product-form");
  const nameInput = document.getElementById("product-name");
  const descriptionInput = document.getElementById("product-description");
  const priceInput = document.getElementById("product-price");
  const stockInput = document.getElementById("product-stock");
  const categorySelect = document.getElementById("product-category");
  const imageUrlInput = document.getElementById("product-image-url");
  const isActiveInput = document.getElementById("product-is-active");
  const formError = document.getElementById("form-error");
  const submitButton = document.getElementById("product-submit-button");

  // With ?id= the form edits that product. The id must be a positive whole number that fits
  // the database integer, otherwise the page says "Product not found" without calling the API.
  const idText = new URLSearchParams(window.location.search).get("id");
  const isEditing = idText !== null;
  if (isEditing && !(/^[1-9][0-9]*$/.test(idText) && Number(idText) <= 2147483647)) {
    document.title = "Product not found";
    formHeading.textContent = "Product not found";
    formStatus.textContent = "";
    const notFoundBox = document.createElement("div");
    notFoundBox.className = "state-empty";
    const notFoundText = document.createElement("p");
    notFoundText.textContent = "Product not found";
    const backLink = document.createElement("a");
    backLink.href = "/seller-products.html";
    backLink.textContent = "My Products";
    notFoundBox.append(notFoundText, backLink);
    formStatus.append(notFoundBox);
    return;
  }

  // Load the categories for the dropdown, and the product when editing
  let categories = null;
  let product = null;
  try {
    categories = await apiRequest("/categories", "GET");
    if (isEditing) {
      product = await apiRequest("/seller/products/" + idText, "GET");
    } else {
      // Creating a product has no API call that can answer 403 yet, so ask who is logged in
      const me = await apiRequest("/users/me", "GET");
      if (me.role !== "seller") {
        const notSellerError = new Error("Seller access required");
        notSellerError.status = 403;
        throw notSellerError;
      }
    }
  } catch (error) {
    formStatus.textContent = "";
    const errorBox = document.createElement("div");
    errorBox.className = "state-error";
    const errorText = document.createElement("p");
    if (error.status === 403) {
      errorText.textContent = "This page is for seller accounts.";
      errorBox.append(errorText);
    } else if (error.status === 404) {
      document.title = "Product not found";
      formHeading.textContent = "Product not found";
      errorText.textContent = "Product not found";
      const backLink = document.createElement("a");
      backLink.href = "/seller-products.html";
      backLink.textContent = "My Products";
      errorBox.className = "state-empty";
      errorBox.append(errorText, backLink);
    } else {
      errorText.textContent = "Could not load the form: " + error.message;
      const retryButton = document.createElement("button");
      retryButton.type = "button";
      retryButton.textContent = "Try again";
      retryButton.addEventListener("click", function () {
        window.location.reload();
      });
      errorBox.append(errorText, retryButton);
    }
    formStatus.append(errorBox);
    return;
  }

  // Fill the category dropdown (textContent only, the names come from admins)
  const chooseOption = document.createElement("option");
  chooseOption.value = "";
  chooseOption.textContent = "Choose a category";
  categorySelect.append(chooseOption);
  for (const category of categories) {
    const option = document.createElement("option");
    option.value = String(category.id);
    option.textContent = category.name;
    categorySelect.append(option);
  }

  // When editing, put the product into the form (the price is shown in rupees)
  if (product !== null) {
    document.title = "Edit " + product.name;
    formHeading.textContent = "Edit product";
    nameInput.value = product.name;
    descriptionInput.value = product.description;
    priceInput.value = String(product.price / 100);
    stockInput.value = String(product.stock);
    categorySelect.value = String(product.category.id);
    imageUrlInput.value = product.image_url || "";
    isActiveInput.checked = product.is_active;
  } else {
    document.title = "Add product";
  }
  formStatus.textContent = "";
  productForm.hidden = false;

  // Check the form in the browser first, then send it
  productForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    formError.hidden = true;

    const name = nameInput.value.trim();
    const description = descriptionInput.value.trim();
    const priceText = priceInput.value.trim();
    const stockText = stockInput.value.trim();
    const price = Math.round(Number(priceText) * 100);
    let problem = "";
    if (name === "") {
      problem = "Please enter a name.";
    } else if (description === "") {
      problem = "Please enter a description.";
    } else if (priceText === "" || !Number.isFinite(Number(priceText)) || Number(priceText) <= 0 || price < 1 || price > 2147483647) {
      problem = "The price must be a number above 0.";
    } else if (!/^[0-9]+$/.test(stockText) || Number(stockText) > 2147483647) {
      problem = "The stock must be a whole number of 0 or more.";
    } else if (categorySelect.value === "") {
      problem = "Please choose a category.";
    }
    if (problem !== "") {
      formError.textContent = problem;
      formError.hidden = false;
      return;
    }

    // The values to send. An empty image URL means no image.
    const values = {
      name: name,
      description: description,
      price: price,
      stock: Number(stockText),
      category_id: Number(categorySelect.value),
      image_url: imageUrlInput.value.trim() === "" ? null : imageUrlInput.value.trim(),
      is_active: isActiveInput.checked,
    };

    submitButton.disabled = true;
    try {
      if (isEditing) {
        await apiRequest("/products/" + idText, "PATCH", values);
      } else {
        await apiRequest("/products", "POST", values);
      }
      window.location.href = "/seller-products.html";
    } catch (error) {
      // Show the API message (for example a rejected image URL) and stay on the form
      formError.textContent = error.message;
      formError.hidden = false;
      submitButton.disabled = false;
    }
  });
}

loadProductFormPage();
