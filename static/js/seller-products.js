// The seller's product table: all their products (active or not), 20 per page.
async function loadSellerProductsPage() {
  const productsArea = document.getElementById("products-area");
  const paginationArea = document.getElementById("pagination-area");
  const actionMessage = document.getElementById("action-message");

  // Read the page number from the URL (anything below 1 or not a number becomes 1)
  const pageSize = 20;
  let page = parseInt(new URLSearchParams(window.location.search).get("page"), 10);
  if (!Number.isSafeInteger(page) || page < 1) {
    page = 1;
  }

  // Load the page of products
  let result = null;
  try {
    result = await apiRequest("/seller/products?page=" + page + "&page_size=" + pageSize, "GET");
  } catch (error) {
    productsArea.textContent = "";
    const errorBox = document.createElement("div");
    errorBox.className = "state-error";
    const errorText = document.createElement("p");
    if (error.status === 403) {
      errorText.textContent = "This page is for seller accounts.";
      errorBox.append(errorText);
    } else {
      errorText.textContent = "Could not load your products: " + error.message;
      const retryButton = document.createElement("button");
      retryButton.type = "button";
      retryButton.textContent = "Try again";
      retryButton.addEventListener("click", function () {
        window.location.reload();
      });
      errorBox.append(errorText, retryButton);
    }
    productsArea.append(errorBox);
    return;
  }

  // No products (or a page past the last one)
  productsArea.textContent = "";
  if (result.items.length === 0) {
    const emptyBox = document.createElement("div");
    emptyBox.className = "state-empty";
    const emptyText = document.createElement("p");
    emptyText.textContent = result.total === 0 ? "You have no products yet." : "There are no products on this page.";
    emptyBox.append(emptyText);
    productsArea.append(emptyBox);
    if (result.total === 0) {
      return;
    }
  }

  // The table: the scroll container keeps a wide table inside its own box
  const tableWrapper = document.createElement("div");
  tableWrapper.className = "table-wrapper";
  const table = document.createElement("table");
  table.className = "dashboard-table";
  const tableHead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const columnName of ["Image", "Name", "Price", "Stock", "Status", "Actions"]) {
    const headCell = document.createElement("th");
    headCell.textContent = columnName;
    headRow.append(headCell);
  }
  tableHead.append(headRow);
  const tableBody = document.createElement("tbody");

  for (const product of result.items) {
    const row = document.createElement("tr");

    // The small image (with a one-time fallback to the placeholder)
    const imageCell = document.createElement("td");
    const image = document.createElement("img");
    image.className = "dashboard-image";
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
    imageCell.append(image);

    const nameCell = document.createElement("td");
    nameCell.textContent = product.name;

    const priceCell = document.createElement("td");
    priceCell.textContent = "₹" + (product.price / 100).toLocaleString("en-IN", { minimumFractionDigits: product.price % 100 === 0 ? 0 : 2, maximumFractionDigits: 2 });

    // Low stock (5 or fewer) is shown in orange
    const stockCell = document.createElement("td");
    stockCell.textContent = String(product.stock);
    if (product.stock <= 5) {
      stockCell.className = "stock-low";
    }

    const statusCell = document.createElement("td");
    statusCell.textContent = product.is_active ? "Active" : "Inactive";

    // Actions: Edit, and Deactivate or Activate
    const actionsCell = document.createElement("td");
    const actionsBox = document.createElement("div");
    actionsBox.className = "dashboard-actions";
    const editLink = document.createElement("a");
    editLink.className = "button button-secondary";
    editLink.href = "/seller-product-form.html?id=" + encodeURIComponent(product.id);
    editLink.textContent = "Edit";
    const toggleButton = document.createElement("button");
    toggleButton.type = "button";
    toggleButton.className = "button-secondary";
    toggleButton.textContent = product.is_active ? "Deactivate" : "Activate";
    toggleButton.addEventListener("click", async function () {
      toggleButton.disabled = true;
      actionMessage.hidden = true;
      try {
        if (product.is_active) {
          await apiRequest("/products/" + product.id, "DELETE");
        } else {
          await apiRequest("/products/" + product.id, "PATCH", { is_active: true });
        }
        window.location.reload();
      } catch (error) {
        // Show the API message and do not reload
        actionMessage.textContent = error.message;
        actionMessage.hidden = false;
        toggleButton.disabled = false;
      }
    });
    actionsBox.append(editLink, toggleButton);
    actionsCell.append(actionsBox);

    row.append(imageCell, nameCell, priceCell, stockCell, statusCell, actionsCell);
    tableBody.append(row);
  }
  table.append(tableHead, tableBody);
  tableWrapper.append(table);
  productsArea.append(tableWrapper);

  // Pagination is only needed when there is more than one page
  const totalPages = Math.ceil(result.total / pageSize);
  if (totalPages <= 1) {
    return;
  }
  const pagination = document.createElement("nav");
  pagination.className = "pagination";
  pagination.setAttribute("aria-label", "Pagination");

  // Previous: a link, or plain disabled text on the first page
  let previousItem = null;
  if (page > 1) {
    previousItem = document.createElement("a");
    previousItem.setAttribute("href", "/seller-products.html?page=" + (page - 1));
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
    nextItem.setAttribute("href", "/seller-products.html?page=" + (page + 1));
  } else {
    nextItem = document.createElement("span");
    nextItem.className = "disabled";
  }
  nextItem.textContent = "Next";

  pagination.append(previousItem, pageInfo, nextItem);
  paginationArea.append(pagination);
}

loadSellerProductsPage();
