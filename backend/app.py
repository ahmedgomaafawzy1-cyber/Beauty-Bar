from flask import Flask, jsonify, request, send_from_directory, session
from flask_cors import CORS
from werkzeug.utils import secure_filename
import sqlite3
import os
from datetime import datetime

app = Flask("beauty_bar")

app.secret_key = os.environ.get("SECRET_KEY", "beauty-bar-local-secret")
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("RENDER") == "true"
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

CORS(app, supports_credentials=True)

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BACKEND_DIR)
FRONTEND_DIR = os.path.join(PROJECT_DIR, "frontend")

DATABASE = os.environ.get(
    "DATABASE_PATH",
    os.path.join(BACKEND_DIR, "data", "beauty_bar.db")
)

UPLOAD_FOLDER = os.environ.get(
    "UPLOAD_FOLDER",
    os.path.join(BACKEND_DIR, "data", "products")
)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

os.makedirs(os.path.dirname(os.path.abspath(DATABASE)), exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# =====================================

# DATABASE

# =====================================

def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection

def create_database():
    connection = get_db_connection()
    connection.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price REAL NOT NULL,
        description TEXT,
        image TEXT,
        stock INTEGER NOT NULL DEFAULT 0,
        stock_status TEXT NOT NULL DEFAULT 'Out of Stock'
    )
""")

    columns = connection.execute(
        "PRAGMA table_info(products)"
    ).fetchall()

    column_names = [column["name"] for column in columns]

    if "stock" not in column_names:
        connection.execute("""
            ALTER TABLE products
            ADD COLUMN stock INTEGER NOT NULL DEFAULT 0
        """)

    if "stock_status" not in column_names:
        connection.execute("""
            ALTER TABLE products
            ADD COLUMN stock_status TEXT NOT NULL DEFAULT 'Out of Stock'
        """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            city TEXT NOT NULL,
            address TEXT NOT NULL,
            notes TEXT,
            total REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TEXT NOT NULL
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER,
            product_name TEXT NOT NULL,
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id)
        )
    """)

    connection.commit()

    count = connection.execute(
        "SELECT COUNT(*) AS count FROM products"
    ).fetchone()["count"]

    connection.close()

    print("Database full path:", DATABASE)

    print("Products found in database:", count)

create_database()


# =====================================

# HELPERS

# =====================================

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )

def product_to_dict(product):
    item = dict(product)

    if item.get("image"):
        item["image"] = "/" + item["image"].replace("\\", "/").lstrip("/")

    return item


def admin_required():
    return "admin_logged_in" in session

# =====================================

# HOME

# =====================================

@app.route("/", methods=["GET"])
def home():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "message": "Beauty Bar Backend is running!"
    })

# =====================================

# ADMIN LOGIN

# =====================================

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "beautyadmin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "beautybar123")

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json()

    if not data:
        return jsonify({
            "error": "No login data provided"
        }), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session["admin_logged_in"] = True

        return jsonify({
            "message": "Login successful"
        })

    return jsonify({
        "error": "Invalid username or password"
    }), 401

# =====================================
# ADMIN LOGOUT
# =====================================

@app.route("/api/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin_logged_in", None)
    return jsonify({
        "message": "Logged out successfully"
    })


# =====================================
# ADMIN ME
# =====================================

@app.route("/api/admin/me", methods=["GET"])
def admin_me():
    return jsonify({
        "logged_in": admin_required()
    })


# =====================================

# GET PRODUCTS

# =====================================

@app.route("/api/products", methods=["GET"])
def get_products():
    connection = get_db_connection()

    products = connection.execute("""
        SELECT *
        FROM products
        ORDER BY id DESC
    """).fetchall()

    connection.close()

    return jsonify([
        product_to_dict(product)
        for product in products
    ])


# =====================================
# ADD PRODUCT
# =====================================

@app.route("/api/products", methods=["POST"])
def add_product():
    if not admin_required():
        return jsonify({
            "error": "Owner login required"
        }), 401

    name = request.form.get("name", "").strip()
    price_value = request.form.get("price", "").strip()
    description = request.form.get("description", "").strip()
    stock_value = request.form.get("stock", "0").strip()
    image = request.files.get("image")

    if not name or not price_value:
        return jsonify({
            "error": "Name and price are required"
        }), 400

    try:
        price = float(price_value)
        stock = int(stock_value)

        if price < 0 or stock < 0:
            raise ValueError

    except (ValueError, TypeError):
        return jsonify({
            "error": "Price and stock must be valid numbers"
        }), 400

    stock_status = "Available" if stock > 0 else "Out of Stock"

    image_path = ""

    if image and image.filename:
        if not allowed_file(image.filename):
            return jsonify({
                "error": "Only PNG, JPG, JPEG, and WEBP images are allowed"
            }), 400

        filename = secure_filename(image.filename)

        base, extension = os.path.splitext(filename)

        counter = 1
        final_filename = filename

        while os.path.exists(
            os.path.join(UPLOAD_FOLDER, final_filename)
        ):
            final_filename = f"{base}_{counter}{extension}"
            counter += 1

        image.save(
            os.path.join(
                UPLOAD_FOLDER,
                final_filename
            )
        )

        image_path = f"uploads/{final_filename}"

    connection = get_db_connection()

    cursor = connection.execute("""
        INSERT INTO products (
            name,
            price,
            description,
            image,
            stock,
            stock_status
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        name,
        price,
        description,
        image_path,
        stock,
        stock_status
    ))

    connection.commit()

    product_id = cursor.lastrowid

    connection.close()

    return jsonify({
        "message": "Product added successfully",
        "product_id": product_id
    }), 201


# =====================================
# EDIT PRODUCT
# =====================================

@app.route("/api/products/<int:product_id>", methods=["PUT"])
def edit_product(product_id):
    if not admin_required():
        return jsonify({
            "error": "Owner login required"
        }), 401

    name = request.form.get("name", "").strip()
    price_value = request.form.get("price", "").strip()
    description = request.form.get("description", "").strip()
    image = request.files.get("image")

    if not name or not price_value:
        return jsonify({
            "error": "Name and price are required"
        }), 400

    try:
        price = float(price_value)

        if price < 0:
            raise ValueError

    except (ValueError, TypeError):
        return jsonify({
            "error": "Price must be a valid number"
        }), 400

    connection = get_db_connection()

    product = connection.execute("""
        SELECT *
        FROM products
        WHERE id = ?
    """, (product_id,)).fetchone()

    if not product:
        connection.close()

        return jsonify({
            "error": "Product not found"
        }), 404

    image_path = product["image"]

    if image and image.filename:
        if not allowed_file(image.filename):
            connection.close()

            return jsonify({
                "error": "Only PNG, JPG, JPEG, and WEBP images are allowed"
            }), 400

        filename = secure_filename(image.filename)

        base, extension = os.path.splitext(filename)

        counter = 1
        final_filename = filename

        while os.path.exists(
            os.path.join(UPLOAD_FOLDER, final_filename)
        ):
            final_filename = f"{base}_{counter}{extension}"
            counter += 1

        image.save(
            os.path.join(
                UPLOAD_FOLDER,
                final_filename
            )
        )

        image_path = f"uploads/{final_filename}"

        if product["image"]:
            old_filename = os.path.basename(
                product["image"]
            )

            old_path = os.path.join(
                UPLOAD_FOLDER,
                old_filename
            )

            if os.path.exists(old_path):
                os.remove(old_path)

    connection.execute("""
        UPDATE products
        SET
            name = ?,
            price = ?,
            description = ?,
            image = ?
        WHERE id = ?
    """, (
        name,
        price,
        description,
        image_path,
        product_id
    ))

    connection.commit()

    connection.close()

    return jsonify({
        "message": "Product updated successfully"
    })

    image_path = product["image"]

    connection.execute("""
        DELETE FROM products
        WHERE id = ?
    """, (product_id,))

    connection.commit()
    connection.close()

    if image_path:
        filename = os.path.basename(image_path)

        file_path = os.path.join(
            UPLOAD_FOLDER,
            filename
        )

        if os.path.exists(file_path):
            os.remove(file_path)

    return jsonify({
        "message": "Product deleted successfully"
    })

# =====================================

# DELETE PRODUCT

# =====================================

@app.route("/api/products/<int:product_id>", methods=["DELETE"])
def delete_product(product_id):
    if not admin_required():
        return jsonify({
            "error": "Owner login required"
        }), 401

    connection = get_db_connection()

    product = connection.execute(
        "SELECT * FROM products WHERE id = ?",
        (product_id,)
    ).fetchone()

    if not product:
        connection.close()
        return jsonify({
            "error": "Product not found"
        }), 404

    connection.execute(
        "DELETE FROM products WHERE id = ?",
        (product_id,)
    )

    connection.commit()
    connection.close()

    return jsonify({
        "message": "Product deleted successfully"
    }), 200

# =====================================

# UPDATE STOCK

# =====================================

@app.route("/api/products/<int:product_id>/stock", methods=["PUT"])
def update_stock(product_id):
    if not admin_required():
        return jsonify({
            "error": "Owner login required"
        }), 401

    data = request.get_json()

    if not data:
        return jsonify({
            "error": "No data provided"
        }), 400

    try:
        stock = int(data.get("stock"))

        if stock < 0:
            raise ValueError

    except (ValueError, TypeError):
        return jsonify({
            "error": "Stock must be a valid non-negative number"
        }), 400
    stock_status = "Available" if stock > 0 else "Out of Stock"

    connection = get_db_connection()

    cursor = connection.execute("""
        UPDATE products
        SET
            stock = ?,
            stock_status = ?
        WHERE id = ?
    """, (
        stock,
        stock_status,
        product_id
    ))

    connection.commit()

    updated = cursor.rowcount

    connection.close()

    if updated == 0:
        return jsonify({
            "error": "Product not found"
        }), 404

    return jsonify({
        "message": "Stock updated successfully",
        "stock": stock,
        "stock_status": stock_status
    })

# =====================================

# CREATE ORDER

# =====================================

@app.route("/api/orders", methods=["POST"])
def create_order():
    connection = None

    try:
        data = request.get_json()

        if not data:
            return jsonify({
                "error": "No order data provided"
            }), 400

        customer = data.get("customer", {})

        name = customer.get("name", "").strip()
        phone = customer.get("phone", "").strip()
        city = customer.get("city", "").strip()
        address = customer.get("address", "").strip()
        notes = customer.get("notes", "").strip()

        products = data.get("products", [])

        if not name:
            return jsonify({
                "error": "Customer name is required"
            }), 400

        if not phone:
            return jsonify({
                "error": "Customer phone is required"
            }), 400

        if not city:
            return jsonify({
                "error": "City is required"
            }), 400

        if not address:
            return jsonify({
                "error": "Address is required"
            }), 400

        if not products:
            return jsonify({
                "error": "Order must contain products"
            }), 400

        connection = get_db_connection()
        total = 0
        validated_products = []

        for product in products:
            try:
                product_id = int(product.get("id"))
                quantity = int(product.get("quantity", 0))

            except (ValueError, TypeError):
                return jsonify({
                    "error": "Invalid product data"
                }), 400

            if quantity <= 0:
                return jsonify({
                    "error": "Invalid product quantity"
                }), 400
        db_product = connection.execute("""
            SELECT
                id,
                name,
                price,
                stock
            FROM products
            WHERE id = ?
        """, (product_id,)).fetchone()

        if not db_product:
            return jsonify({
                "error": f"Product {product_id} not found"
            }), 404

        if db_product["stock"] < quantity:
            return jsonify({
                "error":
                    f"Not enough stock for {db_product['name']}. "
                    f"Available: {db_product['stock']}"
            }), 400

        real_price = float(db_product["price"])

        total += real_price * quantity

        validated_products.append({
            "id": db_product["id"],
            "name": db_product["name"],
            "price": real_price,
            "quantity": quantity,
            "stock": db_product["stock"]
        })

        created_at = datetime.now().isoformat()

        cursor = connection.execute("""
            INSERT INTO orders (
                customer_name,
                phone,
                city,
                address,
                notes,
                total,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name,
            phone,
            city,
            address,
            notes,
            total,
            "Pending",
            created_at
        ))

        order_id = cursor.lastrowid

        for product in validated_products:
            connection.execute("""
                INSERT INTO order_items (
                    order_id,
                    product_id,
                    product_name,
                    price,
                    quantity
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                order_id,
                product["id"],
                product["name"],
                product["price"],
                product["quantity"]
            ))
            for product in validated_products:
                 new_stock = (
                product["stock"]
                - product["quantity"]
            )

            new_status = (
                "Available"
                if new_stock > 0
                else "Out of Stock"
            )

            connection.execute("""
                UPDATE products
                SET
                    stock = ?,
                    stock_status = ?
                WHERE id = ?
            """, (
                new_stock,
                new_status,
                product["id"]
            ))

            connection.commit()

        connection.close()

        return jsonify({
            "message": "Order created successfully",
            "order_id": order_id,
            "total": total
        }), 201
    except Exception as error:
        print("ORDER CREATION ERROR:", error)

        if connection:
            connection.rollback()
            connection.close()

        return jsonify({
            "error": f"Could not create order: {error}"
        }), 500


# =====================================

# GET ORDERS

# =====================================

@app.route("/api/orders", methods=["GET"])
def get_orders():
    if not admin_required():
        return jsonify({
            "error": "Unauthorized"
        }), 401

    connection = get_db_connection()

    orders = connection.execute("""
        SELECT *
        FROM orders
        ORDER BY id DESC
    """).fetchall()

    result = []

    for order in orders:
        items = connection.execute("""
            SELECT
                product_id,
                product_name,
                price,
                quantity
            FROM order_items
            WHERE order_id = ?
        """, (order["id"],)).fetchall()

        order_data = dict(order)

        order_data["items"] = [
            dict(item)
            for item in items
        ]

        result.append(order_data)

    connection.close()

    return jsonify({
        "orders": result
    })

# =====================================

# UPDATE ORDER STATUS

# =====================================

@app.route("/api/orders/<int:order_id>/status", methods=["PUT"])
def update_order_status(order_id):
    if not admin_required():
        return jsonify({
            "error": "Unauthorized"
        }), 401

    data = request.get_json() or {}

    status = data.get("status", "").strip()

    allowed_statuses = {
        "Pending",
        "Confirmed",
        "Shipped",
        "Delivered",
        "Cancelled"
    }

    if status not in allowed_statuses:
        return jsonify({
            "error": "Invalid order status"
        }), 400

    connection = get_db_connection()

    cursor = connection.execute("""
        UPDATE orders
        SET status = ?
        WHERE id = ?
    """, (
        status,
        order_id
    ))

    connection.commit()

    updated = cursor.rowcount

    connection.close()

    if updated == 0:
        return jsonify({
            "error": "Order not found"
        }), 404

    return jsonify({
        "message": "Order status updated successfully"
    })

    return jsonify({
        "message": "Order status updated successfully"
    })


# =====================================

# PRODUCT IMAGES

# =====================================

@app.route("/uploads/<filename>", methods=["GET"])
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/<path:filename>", methods=["GET"])
def frontend_file(filename):
    return send_from_directory(FRONTEND_DIR, filename)


# =====================================

# RUN

# =====================================

if __name__ == "__main__":
    print("=====================================")
    print("BEAUTY BAR BACKEND")
    print("Database:", DATABASE)
    print("Order route: POST /api/orders")
    print("=====================================")

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
