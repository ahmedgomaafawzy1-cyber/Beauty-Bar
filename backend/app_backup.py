from flask import Flask, jsonify, request, send_from_directory, session
from flask_cors import CORS
from werkzeug.utils import secure_filename
import sqlite3
import os

app = Flask(__name__)

# Session security
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "beauty-bar-local-secret-change-before-production"
)

CORS(
    app,
    supports_credentials=True
)

DATABASE = "data/beauty_bar.db"

UPLOAD_FOLDER = "data/products"

ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "webp"
}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

os.makedirs("data", exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# =========================
# DATABASE
# =========================

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
            category TEXT NOT NULL,
            stock_status TEXT NOT NULL DEFAULT 'Available'
        )
    """)

    columns = connection.execute(
        "PRAGMA table_info(products)"
    ).fetchall()

    column_names = [
        column["name"]
        for column in columns
    ]

    if "stock_status" not in column_names:

        connection.execute("""
            ALTER TABLE products
            ADD COLUMN stock_status
            TEXT NOT NULL DEFAULT 'Available'
        """)

    connection.commit()

    connection.close()


# =========================
# HELPERS
# =========================

def allowed_file(filename):

    return (
        "." in filename
        and
        filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


def product_to_dict(product):

    item = dict(product)

    if item["image"]:

        item["image"] = (
            "http://127.0.0.1:5000/"
            + item["image"].replace("\\", "/")
        )

    return item


def admin_required():

    return "admin_logged_in" in session


# =========================
# BASIC ROUTES
# =========================

@app.route("/")
def home():

    return jsonify({
        "message":
            "Beauty Bar Backend is running!"
    })


@app.route("/api/services")
def services():

    return jsonify({

        "services": [

            "Facial Care",

            "Acne Care",

            "Skin Hydration",

            "Skin Cleansing",

            "Sun Protection"

        ]

    })


# =========================
# ADMIN LOGIN
# =========================

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "beautyadmin"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "beautybar123"
)


@app.route(
    "/api/admin/login",
    methods=["POST"]
)
def admin_login():

    data = request.get_json()

    if not data:

        return jsonify({
            "error": "No login data provided"
        }), 400

    username = data.get(
        "username",
        ""
    ).strip()

    password = data.get(
        "password",
        ""
    )


    if (
        username == ADMIN_USERNAME
        and
        password == ADMIN_PASSWORD
    ):

        session["admin_logged_in"] = True

        return jsonify({
            "message": "Login successful"
        })


    return jsonify({
        "error": "Invalid username or password"
    }), 401


@app.route(
    "/api/admin/logout",
    methods=["POST"]
)
def admin_logout():

    session.pop(
        "admin_logged_in",
        None
    )

    return jsonify({
        "message": "Logged out successfully"
    })


@app.route(
    "/api/admin/me",
    methods=["GET"]
)
def admin_me():

    if admin_required():

        return jsonify({
            "logged_in": True
        })

    return jsonify({
        "logged_in": False
    })


# =========================
# GET PRODUCTS
# =========================

@app.route(
    "/api/products",
    methods=["GET"]
)
def get_products():

    connection = get_db_connection()

    products = connection.execute(
        """
        SELECT *
        FROM products
        ORDER BY id DESC
        """
    ).fetchall()

    connection.close()

    return jsonify([
        product_to_dict(product)
        for product in products
    ])


# =========================
# ADD PRODUCT
# =========================

@app.route(
    "/api/products",
    methods=["POST"]
)
def add_product():

    if not admin_required():

        return jsonify({
            "error": "Owner login required"
        }), 401


    name = request.form.get(
        "name",
        ""
    ).strip()

    price = request.form.get(
        "price"
    )

    description = request.form.get(
        "description",
        ""
    ).strip()

    category = request.form.get(
        "category",
        ""
    ).strip()

    stock_status = request.form.get(
        "stock_status",
        "Available"
    ).strip()

    image = request.files.get(
        "image"
    )


    if (
        not name
        or
        not price
        or
        not category
    ):

        return jsonify({
            "error":
                "Name, price, and category are required"
        }), 400


    if stock_status not in [
        "Available",
        "Out of Stock"
    ]:

        return jsonify({
            "error": "Invalid stock status"
        }), 400


    try:

        price = float(price)

        if price < 0:

            raise ValueError

    except ValueError:

        return jsonify({
            "error":
                "Price must be a valid number"
        }), 400


    image_path = ""


    if image and image.filename:

        if not allowed_file(
            image.filename
        ):

            return jsonify({
                "error":
                    "Only PNG, JPG, JPEG, and WEBP images are allowed"
            }), 400


        filename = secure_filename(
            image.filename
        )


        base, extension = os.path.splitext(
            filename
        )


        counter = 1

        final_filename = filename


        while os.path.exists(
            os.path.join(
                UPLOAD_FOLDER,
                final_filename
            )
        ):

            final_filename = (
                f"{base}_{counter}{extension}"
            )

            counter += 1


        image.save(
            os.path.join(
                UPLOAD_FOLDER,
                final_filename
            )
        )


        image_path = (
            f"uploads/{final_filename}"
        )


    connection = get_db_connection()


    cursor = connection.execute(
        """
        INSERT INTO products
        (
            name,
            price,
            description,
            image,
            category,
            stock_status
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            price,
            description,
            image_path,
            category,
            stock_status
        )
    )


    connection.commit()

    product_id = cursor.lastrowid

    connection.close()


    return jsonify({
        "message":
            "Product added successfully",
        "product_id":
            product_id
    }), 201


# =========================
# EDIT PRODUCT
# =========================

@app.route(
    "/api/products/<int:product_id>",
    methods=["PUT"]
)
def edit_product(product_id):

    if not admin_required():

        return jsonify({
            "error": "Owner login required"
        }), 401


    name = request.form.get(
        "name",
        ""
    ).strip()

    price = request.form.get(
        "price"
    )

    description = request.form.get(
        "description",
        ""
    ).strip()

    category = request.form.get(
        "category",
        ""
    ).strip()

    stock_status = request.form.get(
        "stock_status",
        "Available"
    ).strip()

    image = request.files.get(
        "image"
    )


    if (
        not name
        or
        not price
        or
        not category
    ):

        return jsonify({
            "error":
                "Name, price, and category are required"
        }), 400


    if stock_status not in [
        "Available",
        "Out of Stock"
    ]:

        return jsonify({
            "error": "Invalid stock status"
        }), 400


    try:

        price = float(price)

        if price < 0:

            raise ValueError

    except ValueError:

        return jsonify({
            "error":
                "Price must be a valid number"
        }), 400


    connection = get_db_connection()


    old_product = connection.execute(
        """
        SELECT *
        FROM products
        WHERE id = ?
        """,
        (product_id,)
    ).fetchone()


    if not old_product:

        connection.close()

        return jsonify({
            "error": "Product not found"
        }), 404


    old_image = old_product["image"]

    image_path = old_image


    if image and image.filename:

        if not allowed_file(
            image.filename
        ):

            connection.close()

            return jsonify({
                "error":
                    "Only PNG, JPG, JPEG, and WEBP images are allowed"
            }), 400


        filename = secure_filename(
            image.filename
        )


        base, extension = os.path.splitext(
            filename
        )


        counter = 1

        final_filename = filename


        while os.path.exists(
            os.path.join(
                UPLOAD_FOLDER,
                final_filename
            )
        ):

            final_filename = (
                f"{base}_{counter}{extension}"
            )

            counter += 1


        image.save(
            os.path.join(
                UPLOAD_FOLDER,
                final_filename
            )
        )


        image_path = (
            f"uploads/{final_filename}"
        )


        if old_image:

            old_filename = os.path.basename(
                old_image
            )

            old_file_path = os.path.join(
                UPLOAD_FOLDER,
                old_filename
            )

            if os.path.exists(
                old_file_path
            ):

                os.remove(
                    old_file_path
                )


    connection.execute(
        """
        UPDATE products

        SET
            name = ?,
            price = ?,
            description = ?,
            image = ?,
            category = ?,
            stock_status = ?

        WHERE id = ?
        """,
        (
            name,
            price,
            description,
            image_path,
            category,
            stock_status,
            product_id
        )
    )


    connection.commit()

    connection.close()


    return jsonify({
        "message":
            "Product updated successfully"
    })


# =========================
# DELETE PRODUCT
# =========================

@app.route(
    "/api/products/<int:product_id>",
    methods=["DELETE"]
)
def delete_product(product_id):

    if not admin_required():

        return jsonify({
            "error": "Owner login required"
        }), 401


    connection = get_db_connection()


    product = connection.execute(
        """
        SELECT *
        FROM products
        WHERE id = ?
        """,
        (product_id,)
    ).fetchone()


    if not product:

        connection.close()

        return jsonify({
            "error":
                "Product not found"
        }), 404


    image_path = product["image"]


    connection.execute(
        """
        DELETE FROM products
        WHERE id = ?
        """,
        (product_id,)
    )


    connection.commit()

    connection.close()


    if image_path:

        filename = os.path.basename(
            image_path
        )

        file_path = os.path.join(
            UPLOAD_FOLDER,
            filename
        )

        if os.path.exists(
            file_path
        ):

            os.remove(
                file_path
            )


    return jsonify({
        "message":
            "Product deleted successfully"
    })


# =========================
# UPDATE STOCK
# =========================

@app.route(
    "/api/products/<int:product_id>/stock",
    methods=["PUT"]
)
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


    stock_status = data.get(
        "stock_status"
    )


    if stock_status not in [
        "Available",
        "Out of Stock"
    ]:

        return jsonify({
            "error":
                "Invalid stock status"
        }), 400


    connection = get_db_connection()


    cursor = connection.execute(
        """
        UPDATE products

        SET stock_status = ?

        WHERE id = ?
        """,
        (
            stock_status,
            product_id
        )
    )


    connection.commit()

    updated = cursor.rowcount

    connection.close()


    if updated == 0:

        return jsonify({
            "error":
                "Product not found"
        }), 404


    return jsonify({
        "message":
            "Stock status updated successfully"
    })


# =========================
# SERVE PRODUCT IMAGES
# =========================

@app.route(
    "/uploads/<filename>"
)
def uploaded_file(filename):

    return send_from_directory(
        UPLOAD_FOLDER,
        filename
    )


# =========================
# RUN
# =========================

if __name__ == "__main__":

    create_database()

    app.run(
        debug=True
    )