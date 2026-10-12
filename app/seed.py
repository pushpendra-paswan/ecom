# Fills the database with demo data. Run with: python -m app.seed
import re

import bcrypt

from app.db import SessionLocal
from app.models import Address, Category, Product, User

# Dev password used by every demo account
DEV_PASSWORD = "Password@123"

# (email, full name, role)
USERS = [
    ("admin@example.com", "Aarav Admin", "admin"),
    ("seller1@example.com", "Sanjay Sharma", "seller"),
    ("seller2@example.com", "Meera Iyer", "seller"),
    ("customer1@example.com", "Rohan Gupta", "customer"),
    ("customer2@example.com", "Priya Nair", "customer"),
]

# (name, slug, description)
CATEGORIES = [
    ("Electronics", "electronics", "Phones, laptops, audio and other gadgets."),
    ("Books", "books", "Fiction, non-fiction and study books."),
    ("Clothing", "clothing", "Everyday clothes for men, women and kids."),
    ("Home & Kitchen", "home-kitchen", "Cookware, appliances and home essentials."),
    ("Sports", "sports", "Equipment and gear for indoor and outdoor sports."),
    ("Toys", "toys", "Toys and games for all ages."),
    ("Beauty", "beauty", "Skin care, hair care and grooming."),
    ("Grocery", "grocery", "Staples, snacks and beverages."),
    ("Stationery", "stationery", "Pens, notebooks and office supplies."),
    ("Furniture", "furniture", "Furniture for the home and the office."),
]

# Products per category slug: (name, description, price in paise, stock, is_active)
PRODUCTS = {
    "electronics": [
        ("Nova X5 Smartphone 128GB", "A 6.5 inch display phone with a 50MP camera and a two day battery.", 1799900, 60, True),
        ("Zenbook Air 14 Laptop", "A thin 14 inch laptop with 16GB RAM and a 512GB SSD.", 7499900, 25, True),
        ("BassBoom Wireless Earbuds", "True wireless earbuds with noise cancellation and 24 hours of playback.", 249900, 120, True),
        ("PixelView 27 inch Monitor", "A 27 inch full HD IPS monitor with thin bezels.", 1399900, 30, True),
        ("Limited Edition Mechanical Keyboard", "A hand assembled mechanical keyboard with a numbered case.", 899900, 1, True),
        ("PowerMax 20000mAh Power Bank", "A fast charging power bank that can charge two devices at once.", 219900, 150, True),
        ("SoundBar Pro 2.1", "A 2.1 channel soundbar with a wireless subwoofer.", 1099900, 40, True),
        ("SnapCam 4K Action Camera", "A waterproof action camera that records 4K video at 60 fps.", 599900, 35, True),
        ("TabLite 10 Tablet", "A 10 inch tablet with 64GB storage, good for reading and video.", 1299900, 45, True),
        ("SmartFit Band 6", "A fitness band with heart rate and sleep tracking.", 349900, 90, True),
        ("USB-C Fast Charger 65W", "A compact 65W wall charger for phones and laptops.", 149900, 200, True),
        ("Wi-Fi 6 Dual Band Router", "A dual band router with strong coverage for a three bedroom home.", 399900, 55, True),
    ],
    "books": [
        ("The Midnight Library of Jaipur", "A novel about a librarian who finds doors to other lives.", 39900, 100, True),
        ("Atomic Habits for Students", "A practical guide to building small habits that last.", 49900, 150, True),
        ("Signed First Edition Novel", "A signed first edition of a bestselling literary novel.", 299900, 1, True),
        ("Python Programming from Scratch", "A beginner friendly introduction to Python with exercises.", 59900, 80, True),
        ("A Brief History of India", "A clear and short account of Indian history from the Indus Valley to today.", 44900, 70, True),
        ("The Spice Route Cookbook", "Over 100 regional recipes with step by step photos.", 69900, 50, True),
        ("Wings of Dreams: A Biography", "The life story of a scientist who became a president.", 29900, 120, True),
        ("Mathematics for Class 10", "A complete practice workbook with solved examples.", 24900, 200, True),
        ("The Silent Monsoon", "A slow burning mystery set in a small coastal town.", 34900, 90, True),
        ("Personal Finance Made Simple", "How to save, invest and plan your money in simple steps.", 39900, 110, True),
        ("Illustrated World Atlas", "A large atlas with maps, flags and facts for every country.", 89900, 40, True),
        ("Tales from the Panchatantra", "A children's collection of animal stories with morals.", 19900, 160, True),
    ],
    "clothing": [
        ("Men's Cotton Crew Neck T-Shirt", "A soft cotton t-shirt that is comfortable all day.", 49900, 180, True),
        ("Women's Printed Kurti", "A light cotton kurti with a block print design.", 79900, 90, True),
        ("Slim Fit Denim Jeans", "Stretch denim jeans with a slim fit and five pockets.", 149900, 100, True),
        ("Winter Wool Overcoat", "A long wool blend overcoat for cold weather.", 449900, 0, True),
        ("Kids' Cartoon Hoodie", "A warm fleece hoodie with a fun print for kids.", 59900, 70, True),
        ("Formal White Shirt", "A wrinkle resistant full sleeve shirt for office wear.", 99900, 85, True),
        ("Running Shorts with Zip Pocket", "Quick dry shorts with a zip pocket for your keys.", 39900, 120, True),
        ("Silk Blend Saree", "A silk blend saree with a woven border.", 299900, 30, True),
        ("Cotton Track Pants", "Relaxed fit track pants for the gym or home.", 69900, 140, True),
        ("Woollen Winter Cap", "A knitted cap that keeps your ears warm.", 19900, 200, True),
        ("Leather Belt, Brown", "A genuine leather belt with a steel buckle.", 54900, 75, True),
        ("Sports Socks, Pack of 5", "Cushioned cotton socks for running and training.", 24900, 190, True),
    ],
    "home-kitchen": [
        ("Non-Stick Cookware Set, 5 Pieces", "A five piece non-stick set with a fry pan, kadhai and tawa.", 299900, 45, True),
        ("Stainless Steel Pressure Cooker 5L", "A durable 5 litre pressure cooker with a safety valve.", 189900, 60, True),
        ("Mixer Grinder 750W", "A three jar mixer grinder for wet and dry grinding.", 349900, 50, True),
        ("Discontinued Pressure Cooker 3L", "An older 3 litre pressure cooker, no longer sold.", 129900, 20, False),
        ("Glass Water Bottle Set, 4 Pieces", "Four borosilicate glass bottles with steel lids.", 49900, 130, True),
        ("Electric Kettle 1.5L", "A stainless steel kettle with auto shut off.", 99900, 100, True),
        ("Cotton Bedsheet, Double Bed", "A double bed bedsheet with two pillow covers.", 89900, 80, True),
        ("Air Fryer 4L", "An air fryer that cooks with very little oil.", 499900, 35, True),
        ("Vacuum Insulated Lunch Box", "A three container lunch box that keeps food warm.", 79900, 110, True),
        ("Bamboo Chopping Board", "A sturdy bamboo board that is gentle on knives.", 34900, 140, True),
        ("Chef's Knife Set, 3 Pieces", "Three sharp stainless steel knives with a block.", 159900, 55, True),
        ("LED Bulb Pack, 10 Watt x 6", "Six energy saving LED bulbs with warm white light.", 59900, 170, True),
    ],
    "sports": [
        ("Pro Carbon Tennis Racket", "A lightweight carbon racket used by club players.", 899900, 1, True),
        ("Cricket Bat, English Willow", "A grade 2 English willow bat with a cane handle.", 1299900, 20, True),
        ("Yoga Mat 6mm", "A non-slip 6mm yoga mat with a carry strap.", 79900, 150, True),
        ("Adjustable Dumbbell Set 20kg", "A pair of adjustable dumbbells with extra plates.", 349900, 40, True),
        ("Football Size 5", "A machine stitched match football.", 69900, 100, True),
        ("Badminton Racket Pair", "Two graphite badminton rackets with covers.", 149900, 70, True),
        ("Skipping Rope with Counter", "A speed rope with a digital jump counter.", 24900, 180, True),
        ("Running Shoes, Road Series", "Cushioned running shoes for daily road runs.", 249900, 65, True),
        ("Resistance Bands Set", "Five resistance bands of different strengths.", 59900, 120, True),
        ("Cycling Helmet", "A ventilated helmet with an adjustable fit.", 119900, 50, True),
        ("Gym Duffel Bag", "A roomy duffel bag with a separate shoe pocket.", 89900, 85, True),
        ("Table Tennis Table, Foldable", "A foldable indoor table tennis table with a net.", 1999900, 8, True),
    ],
    "toys": [
        ("Building Blocks Set, 500 Pieces", "A colourful set of 500 blocks with a storage box.", 99900, 90, True),
        ("Remote Control Stunt Car", "A rechargeable stunt car that flips and spins.", 149900, 0, True),
        ("Wooden Puzzle, Map of India", "A 100 piece wooden puzzle of the map of India.", 39900, 110, True),
        ("Soft Teddy Bear, 60cm", "A cuddly teddy bear made of soft plush.", 79900, 75, True),
        ("Junior Chess and Ludo Set", "A folding board with chess and ludo pieces.", 29900, 140, True),
        ("Art and Craft Kit", "A kit with paints, brushes, clay and coloured paper.", 69900, 95, True),
        ("Toy Kitchen Playset", "A playset with pots, pans and play food.", 119900, 45, True),
        ("Science Experiment Kit", "Twenty simple experiments for children aged 8 and up.", 89900, 60, True),
        ("Die-Cast Cars, Pack of 10", "Ten small die-cast metal cars.", 49900, 130, True),
        ("Electronic Drum Set for Kids", "A small drum set with lights and sounds.", 129900, 30, True),
        ("Board Game: Trade Empire", "A family board game about buying and trading cities.", 99900, 65, True),
        ("Jumbo Floor Puzzle, Animals", "A large 48 piece floor puzzle for toddlers.", 34900, 85, True),
    ],
    "beauty": [
        ("Vitamin C Face Serum 30ml", "A brightening serum with 10 percent vitamin C.", 59900, 100, True),
        ("Old Formula Face Serum", "The previous version of our face serum, no longer sold.", 49900, 15, False),
        ("Aloe Vera Gel, 250g", "A soothing aloe vera gel for skin and hair.", 19900, 190, True),
        ("Argan Oil Shampoo 400ml", "A sulphate free shampoo with argan oil.", 44900, 120, True),
        ("Matte Lipstick, Ruby Red", "A long lasting matte lipstick.", 34900, 140, True),
        ("Sunscreen SPF 50, 100ml", "A light sunscreen with no white cast.", 39900, 150, True),
        ("Beard Grooming Kit", "A beard oil, comb and balm in a gift box.", 79900, 55, True),
        ("Electric Trimmer, Cordless", "A cordless trimmer with 10 length settings.", 149900, 70, True),
        ("Charcoal Face Wash 100ml", "A deep cleansing face wash for oily skin.", 24900, 160, True),
        ("Perfume, Ocean Breeze 100ml", "A fresh fragrance for daily wear.", 129900, 45, True),
        ("Hair Dryer 1800W", "A foldable hair dryer with cool and hot settings.", 99900, 60, True),
        ("Moisturising Body Lotion 400ml", "A non-greasy lotion for dry skin.", 29900, 175, True),
    ],
    "grocery": [
        ("Basmati Rice, 5kg", "Long grain aged basmati rice.", 69900, 120, True),
        ("Whole Wheat Atta, 10kg", "Stone ground whole wheat flour.", 52900, 140, True),
        ("Cold Pressed Mustard Oil, 1L", "Pure mustard oil in a glass bottle.", 18900, 160, True),
        ("Assam Black Tea, 500g", "Strong and aromatic loose leaf tea.", 22900, 130, True),
        ("Roasted Almonds, 500g", "Lightly salted roasted almonds.", 54900, 90, True),
        ("Toor Dal, 1kg", "Cleaned and polished toor dal.", 17900, 180, True),
        ("Organic Honey, 500g", "Raw honey from forest flowers.", 34900, 100, True),
        ("Masala Chips, Pack of 12", "Twelve small packs of masala flavoured chips.", 24000, 200, True),
        ("Instant Coffee, 200g", "A rich and smooth instant coffee.", 39900, 110, True),
        ("Mixed Fruit Jam, 500g", "Fruit jam with no added colour.", 19900, 95, True),
        ("Turmeric Powder, 200g", "Pure ground turmeric with a deep colour.", 9900, 170, True),
        ("Oats, 1kg", "Rolled oats for a quick healthy breakfast.", 18900, 150, True),
    ],
    "stationery": [
        ("Gel Pens, Pack of 10", "Ten smooth writing gel pens in assorted colours.", 19900, 200, True),
        ("A4 Ruled Notebook, Pack of 6", "Six notebooks with 180 pages each.", 29900, 150, True),
        ("Fountain Pen with Ink Bottle", "A metal body fountain pen and a bottle of blue ink.", 49900, 60, True),
        ("Desk Organiser, Wooden", "A wooden organiser with five compartments.", 69900, 50, True),
        ("Sticky Notes, Pack of 12", "Twelve pads of colourful sticky notes.", 14900, 190, True),
        ("Scientific Calculator", "A calculator with 240 functions for school and college.", 79900, 80, True),
        ("Geometry Box", "A metal box with compass, divider and protractor.", 19900, 170, True),
        ("Spiral Sketchbook A3", "A 100 page sketchbook with thick paper.", 34900, 85, True),
        ("Highlighters, Pack of 6", "Six pastel highlighters with chisel tips.", 17900, 160, True),
        ("Leather Journal with Lock", "A refillable leather journal with a small lock.", 89900, 40, True),
        ("Stapler with 1000 Pins", "A strong stapler that works with up to 25 sheets.", 12900, 140, True),
        ("Whiteboard with Marker Set", "A magnetic whiteboard with four markers and an eraser.", 99900, 35, True),
    ],
    "furniture": [
        ("Ergonomic Office Chair", "A mesh back chair with lumbar support and adjustable arms.", 1299900, 25, True),
        ("Walnut Study Desk", "A solid wood desk with a drawer and a cable hole.", 1599900, 0, True),
        ("Three Seater Fabric Sofa", "A comfortable three seater sofa with removable covers.", 3499900, 10, True),
        ("Queen Size Bed with Storage", "A queen size engineered wood bed with box storage.", 2899900, 12, True),
        ("Five Shelf Bookcase", "A tall bookcase with five open shelves.", 649900, 30, True),
        ("Folding Dining Table, 4 Seater", "A space saving folding table with four chairs.", 1199900, 18, True),
        ("TV Unit with Drawers", "A TV unit for screens up to 55 inches.", 899900, 22, True),
        ("Shoe Rack, 4 Tier", "A metal shoe rack that holds 12 pairs.", 149900, 70, True),
        ("Bedside Table with Drawer", "A small bedside table with a soft close drawer.", 299900, 40, True),
        ("Recliner Armchair", "A single seater recliner with a footrest.", 1899900, 8, True),
        ("Study Lamp, LED Rechargeable", "A foldable LED lamp with three brightness levels.", 99900, 100, True),
        ("Wall Mounted Floating Shelf Set", "A set of three floating shelves with fixings.", 119900, 65, True),
    ],
}

# Open one session. Everything below is saved in a single transaction.
db = SessionLocal()
try:
    # Stop if the database was already seeded
    existing_category = db.query(Category).first()
    if existing_category is not None:
        print("Categories already exist. The database is already seeded, nothing was changed.")
        raise SystemExit(0)

    # Hash the dev password once with bcrypt
    password_hash = bcrypt.hashpw(DEV_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Create the users
    users_by_email = {}
    for email, full_name, role in USERS:
        user = User(email=email, password_hash=password_hash, full_name=full_name, role=role)
        db.add(user)
        users_by_email[email] = user

    # Give each customer one default address
    db.flush()
    db.add(Address(
        user_id=users_by_email["customer1@example.com"].id,
        full_name="Rohan Gupta",
        phone="9876500001",
        line1="12 MG Road",
        line2="Near City Mall",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560001",
        is_default=True,
    ))
    db.add(Address(
        user_id=users_by_email["customer2@example.com"].id,
        full_name="Priya Nair",
        phone="9876500002",
        line1="45 Marine Drive",
        city="Mumbai",
        state="Maharashtra",
        postal_code="400020",
        is_default=True,
    ))

    # Create the categories
    categories_by_slug = {}
    for name, slug, description in CATEGORIES:
        category = Category(name=name, slug=slug, description=description)
        db.add(category)
        categories_by_slug[slug] = category
    db.flush()

    # Create the products, alternating between the two sellers
    sellers = [users_by_email["seller1@example.com"], users_by_email["seller2@example.com"]]
    product_number = 0
    for category_slug, product_rows in PRODUCTS.items():
        for name, description, price, stock, is_active in product_rows:
            product_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            db.add(Product(
                seller_id=sellers[product_number % 2].id,
                category_id=categories_by_slug[category_slug].id,
                name=name,
                description=description,
                price=price,
                stock=stock,
                image_url=f"https://picsum.photos/seed/{product_slug}/400/400",
                is_active=is_active,
            ))
            product_number += 1

    # Save everything
    db.commit()
    print(f"Seeded {len(USERS)} users, {len(CATEGORIES)} categories and {product_number} products.")
except Exception:
    db.rollback()
    raise
finally:
    db.close()
