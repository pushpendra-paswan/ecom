// The seller's orders: one card per order that contains their products, 10 per page.
async function loadSellerOrdersPage() {
  const ordersArea = document.getElementById("orders-area");
  const paginationArea = document.getElementById("pagination-area");

  // The labels for the order statuses
  const statusLabels = {
    pending_payment: "Awaiting payment",
    paid: "Paid",
    shipped: "Shipped",
    delivered: "Delivered",
    cancelled: "Cancelled",
  };

  // Read the page number from the URL (anything below 1 or not a number becomes 1)
  const pageSize = 10;
  let page = parseInt(new URLSearchParams(window.location.search).get("page"), 10);
  if (!Number.isSafeInteger(page) || page < 1) {
    page = 1;
  }

  // Load the page of orders
  let result = null;
  try {
    result = await apiRequest("/seller/orders?page=" + page + "&page_size=" + pageSize, "GET");
  } catch (error) {
    ordersArea.textContent = "";
    const errorBox = document.createElement("div");
    errorBox.className = "state-error";
    const errorText = document.createElement("p");
    if (error.status === 403) {
      errorText.textContent = "This page is for seller accounts.";
      errorBox.append(errorText);
    } else {
      errorText.textContent = "Could not load the orders: " + error.message;
      const retryButton = document.createElement("button");
      retryButton.type = "button";
      retryButton.textContent = "Try again";
      retryButton.addEventListener("click", function () {
        window.location.reload();
      });
      errorBox.append(errorText, retryButton);
    }
    ordersArea.append(errorBox);
    return;
  }

  // No orders (or a page past the last one)
  ordersArea.textContent = "";
  if (result.items.length === 0) {
    const emptyBox = document.createElement("div");
    emptyBox.className = "state-empty";
    const emptyText = document.createElement("p");
    emptyText.textContent = result.total === 0 ? "No orders yet." : "There are no orders on this page.";
    emptyBox.append(emptyText);
    ordersArea.append(emptyBox);
    if (result.total === 0) {
      return;
    }
  }

  // One card for every order
  for (const order of result.items) {
    const card = document.createElement("article");
    card.className = "order-card";

    // Top row: the order number with the date and time, and the status label
    const cardHeader = document.createElement("div");
    cardHeader.className = "order-card-header";
    const titleBox = document.createElement("div");
    const title = document.createElement("div");
    title.className = "order-card-title";
    title.textContent = "Order #" + order.id;
    const date = document.createElement("div");
    date.className = "order-card-date";
    date.textContent = new Date(order.created_at).toLocaleString("en-IN");
    titleBox.append(title, date);
    const statusBadge = document.createElement("span");
    statusBadge.className = "badge badge-" + order.status.replace("_", "-");
    statusBadge.textContent = statusLabels[order.status] || order.status;
    cardHeader.append(titleBox, statusBadge);

    // This seller's own lines only
    const itemList = document.createElement("ul");
    itemList.className = "order-card-items";
    for (const item of order.items) {
      const itemLine = document.createElement("li");
      itemLine.textContent = item.product_name + " x " + item.quantity;
      itemList.append(itemLine);
    }

    // Bottom row: the seller's subtotal, the "other sellers" label and the link to the details
    const cardFooter = document.createElement("div");
    cardFooter.className = "order-card-footer";
    const totalBox = document.createElement("div");
    const total = document.createElement("div");
    total.className = "order-card-total";
    total.textContent = "Your items total: ₹" + (order.seller_subtotal / 100).toLocaleString("en-IN", { minimumFractionDigits: order.seller_subtotal % 100 === 0 ? 0 : 2, maximumFractionDigits: 2 });
    totalBox.append(total);
    if (order.has_other_sellers) {
      const otherSellers = document.createElement("div");
      otherSellers.className = "order-card-date";
      otherSellers.textContent = "Includes other sellers' products";
      totalBox.append(otherSellers);
    }
    const detailLink = document.createElement("a");
    detailLink.href = "/seller-order.html?id=" + encodeURIComponent(order.id);
    detailLink.textContent = "View details";
    cardFooter.append(totalBox, detailLink);

    card.append(cardHeader, itemList, cardFooter);
    ordersArea.append(card);
  }

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
    previousItem.setAttribute("href", "/seller-orders.html?page=" + (page - 1));
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
    nextItem.setAttribute("href", "/seller-orders.html?page=" + (page + 1));
  } else {
    nextItem = document.createElement("span");
    nextItem.className = "disabled";
  }
  nextItem.textContent = "Next";

  pagination.append(previousItem, pageInfo, nextItem);
  paginationArea.append(pagination);
}

loadSellerOrdersPage();
