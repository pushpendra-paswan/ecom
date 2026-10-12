def test_frontend_files_are_served(client):
    # Every page, script, stylesheet and image the storefront needs
    paths = [
        "/",
        "/products.html",
        "/product.html",
        "/login.html",
        "/register.html",
        "/static/css/style.css",
        "/static/js/api.js",
        "/static/js/layout.js",
        "/static/js/product-card.js",
        "/static/js/home.js",
        "/static/js/products.js",
        "/static/js/product.js",
        "/static/images/placeholder.svg",
    ]

    # Each one should answer 200 (this catches broken mounts and typos in file names)
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path
