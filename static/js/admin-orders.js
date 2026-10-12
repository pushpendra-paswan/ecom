// The admin's list of all orders: a status filter and a table, 20 per page.
async function loadAdminOrdersPage() {
  const ordersArea = document.getElementById("orders-area");
  const paginationArea = document.getElementById("pagination-area");
  const statusFilter = document.getElementById("status-filter");

  // The labels for the order statuses
  const statusLabels = {
    pending_payment: "Awaiting payment",
    paid: "Paid",
    shipped: "Shipped",
    delivered: "Delivered",
    cancelled: "Cancelled",
  };

  // Read the filter and the page number from the URL. A status that is not one of the five is ignored.
  const pageSize = 20;
  const urlParameters = new URLSearchParams(window.location.search);
  let status = urlParameters.get("status");
  if (status === null || statusLabels[status] === undefined) {
    status = "";
  }
  statusFilter.value = status;
  let page = parseInt(urlParameters.get("page"), 10);
  if (!Number.isSafeInteger(page) || page < 1) {
    page = 1;
  }

  // Load the page of orders
  let apiPath = "/admin/orders?page=" + page + "&page_size=" + pageSize;
  if (status !== "") {
    apiPath = apiPath + "&status=" + encodeURIComponent(status);
  }
  let result = null;
  try {
    result = await apiRequest(apiPath, "GET");
  } catch (error) {
    ordersArea.textContent = "";
    const errorBox = document.createElement("div");
    errorBox.className = "state-error";
    const errorText = document.createElement("p");
    if (error.status === 403) {
      errorText.textContent = "This page is for admin accounts.";
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
    emptyText.textContent = result.total === 0 ? "No orders found." : "There are no orders on this page.";
    emptyBox.append(emptyText);
    ordersArea.append(emptyBox);
    if (result.total === 0) {
      return;
    }
  }

  // The table: order id (a link), date, customer email, shipping name, items, total, status
  const tableWrapper = document.createElement("div");
  tableWrapper.className = "table-wrapper";
  const table = document.createElement("table");
  table.className = "dashboard-table";
  const tableHead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const columnName of ["Order", "Date", "Customer", "Ship to", "Items", "Total", "Status"]) {
    const headCell = document.createElement("th");
    headCell.textContent = columnName;
    headRow.append(headCell);
  }
  tableHead.append(headRow);
  const tableBody = document.createElement("tbody");
  for (const order of result.items) {
    const row = document.createElement("tr");

    const idCell = document.createElement("td");
    const idLink = document.createElement("a");
    idLink.href = "/admin-order.html?id=" + encodeURIComponent(order.id);
    idLink.textContent = "#" + order.id;
    idCell.append(idLink);

    const dateCell = document.createElement("td");
    dateCell.textContent = new Date(order.created_at).toLocaleString("en-IN");

    const emailCell = document.createElement("td");
    emailCell.textContent = order.customer_email;

    const shipToCell = document.createElement("td");
    shipToCell.textContent = order.shipping_full_name;

    const itemsCell = document.createElement("td");
    itemsCell.textContent = String(order.item_count);

    const totalCell = document.createElement("td");
    totalCell.textContent = "₹" + (order.total_amount / 100).toLocaleString("en-IN", { minimumFractionDigits: order.total_amount % 100 === 0 ? 0 : 2, maximumFractionDigits: 2 });

    const statusCell = document.createElement("td");
    const statusBadge = document.createElement("span");
    statusBadge.className = "badge badge-" + order.status.replace("_", "-");
    statusBadge.textContent = statusLabels[order.status] || order.status;
    statusCell.append(statusBadge);

    row.append(idCell, dateCell, emailCell, shipToCell, itemsCell, totalCell, statusCell);
    tableBody.append(row);
  }
  table.append(tableHead, tableBody);
  tableWrapper.append(table);
  ordersArea.append(tableWrapper);

  // Pagination is only needed when there is more than one page. The links keep the filter.
  const totalPages = Math.ceil(result.total / pageSize);
  if (totalPages <= 1) {
    return;
  }
  let filterPart = "";
  if (status !== "") {
    filterPart = "status=" + encodeURIComponent(status) + "&";
  }
  const pagination = document.createElement("nav");
  pagination.className = "pagination";
  pagination.setAttribute("aria-label", "Pagination");

  // Previous: a link, or plain disabled text on the first page
  let previousItem = null;
  if (page > 1) {
    previousItem = document.createElement("a");
    previousItem.setAttribute("href", "/admin-orders.html?" + filterPart + "page=" + (page - 1));
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
    nextItem.setAttribute("href", "/admin-orders.html?" + filterPart + "page=" + (page + 1));
  } else {
    nextItem = document.createElement("span");
    nextItem.className = "disabled";
  }
  nextItem.textContent = "Next";

  pagination.append(previousItem, pageInfo, nextItem);
  paginationArea.append(pagination);
}

loadAdminOrdersPage();
